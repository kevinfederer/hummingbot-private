from decimal import Decimal
from typing import List

from pydantic import Field

from hummingbot.core.data_type.common import TradeType
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerBase,
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig


class ISAMMMM2Config(MarketMakingControllerConfigBase):
    """
    ISAMM V2 Controller Configuration

    Avellaneda-Stoikov Market Making implementation with:
    - risk_lambda: Risk aversion parameter
    - gamma_impact: Price impact coefficient
    - kappa: Order book imbalance coefficient
    - spread_bps: Base spread (as ratio, e.g., 0.001 = 0.1% = 10bps)
    - lambda_inv: Inventory skew coefficient
    - max_inventory: Maximum inventory target
    """
    controller_name: str = "isamm_mm_v2"
    candles_config: List[CandlesConfig] = Field(default=[])

    # ISAMM parameters
    risk_lambda: Decimal = Field(
        default=Decimal("0.10"),
        json_schema_extra={"is_updatable": True}
    )
    gamma_impact: Decimal = Field(
        default=Decimal("0.00"),
        json_schema_extra={"is_updatable": True}
    )
    kappa: Decimal = Field(
        default=Decimal("0.00"),
        json_schema_extra={"is_updatable": True}
    )
    spread_bps: Decimal = Field(
        default=Decimal("0.001"),
        json_schema_extra={"is_updatable": True}
    )
    lambda_inv: Decimal = Field(
        default=Decimal("0.00"),
        json_schema_extra={"is_updatable": True}
    )
    max_inventory: Decimal = Field(
        default=Decimal("50"),
        json_schema_extra={"is_updatable": True}
    )

    # Cost / slippage floor (percentages as decimals, e.g., 0.002 = 0.2%)
    maker_fee_pct: Decimal = Field(
        default=Decimal("0"),
        json_schema_extra={"is_updatable": True}
    )
    taker_fee_pct: Decimal = Field(
        default=Decimal("0"),
        json_schema_extra={"is_updatable": True}
    )
    slippage_pct: Decimal = Field(
        default=Decimal("0"),
        json_schema_extra={"is_updatable": True}
    )
    min_profitability_pct: Decimal = Field(
        default=Decimal("0"),
        json_schema_extra={"is_updatable": True}
    )


class ISAMMMM2Controller(MarketMakingControllerBase):
    """
    Avellaneda-Stoikov Market Making Controller.

    This controller implements the AS model which adjusts the optimal bid/ask
    quotes based on inventory risk and market conditions.

    Reference price calculation:
        expected_mid = mid_price + kappa * order_book_imbalance
        skew_price = lambda_inv * inventory
        reference_price = expected_mid - skew_price

    Spread calculation:
        spread_multiplier = spread_bps (base spread as ratio)
    """

    def __init__(self, config: ISAMMMM2Config, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

    def _net_inventory_base(self) -> Decimal:
        """
        Calculate net inventory in base asset.

        BUY positions: +amount
        SELL positions: -amount

        Only includes positions matching the configured connector and trading pair.
        """
        inv = Decimal("0")
        for position in self.positions_held:
            if (position.connector_name == self.config.connector_name and
                position.trading_pair == self.config.trading_pair):
                if position.side.name == "BUY":
                    inv += position.amount
                else:  # SELL
                    inv -= position.amount
        return inv

    def _min_spread_pct(self) -> Decimal:
        """
        Compute the minimum half-spread (distance from reference price) required
        to cover expected round-trip costs.

        Assumptions:
        - Entry is maker
        - Exit is taker if taker_fee_pct > 0, otherwise maker
        - slippage_pct is a one-way estimate (applied once on exit)
        """
        maker_fee = max(self.config.maker_fee_pct, Decimal("0"))
        taker_fee = max(self.config.taker_fee_pct, Decimal("0"))
        slippage = max(self.config.slippage_pct, Decimal("0"))
        min_profit = max(self.config.min_profitability_pct, Decimal("0"))

        if maker_fee == taker_fee == slippage == min_profit == Decimal("0"):
            return Decimal("0")

        exit_fee = taker_fee if taker_fee > 0 else maker_fee
        round_trip_cost = maker_fee + exit_fee + slippage + min_profit
        return round_trip_cost / Decimal("2")

    async def update_processed_data(self):
        """
        Update processed data with ISAMM calculations.

        Sets:
        - reference_price: Optimal mid price adjusted for inventory and OBI
        - spread_multiplier: Base spread ratio
        """
        from hummingbot.core.data_type.common import PriceType

        # Get current mid price
        mid_price = Decimal(
            str(
                self.market_data_provider.get_price_by_type(
                    self.config.connector_name,
                    self.config.trading_pair,
                    PriceType.MidPrice
                )
            )
        )

        # Get current inventory
        inventory = self._net_inventory_base()

        # Order Book Imbalance (placeholder - can be implemented with real OBI data)
        obi = Decimal("0")

        # Calculate expected mid price adjusted for order book imbalance
        expected_mid = mid_price + self.config.kappa * obi

        # Calculate inventory skew
        skew_price = self.config.lambda_inv * inventory

        # Calculate reference price (optimal quoting price)
        reference_price = expected_mid - skew_price

        # Spread multiplier (as ratio, e.g., 0.001 = 0.1%)
        spread_multiplier = self.config.spread_bps
        min_spread_pct = self._min_spread_pct()

        self.processed_data = {
            "mid_price": mid_price,
            "inventory_base": inventory,
            "obi": obi,
            "expected_mid": expected_mid,
            "skew_price": skew_price,
            "reference_price": reference_price,
            "spread_multiplier": spread_multiplier,
            "min_spread_pct": min_spread_pct,
        }

    def get_price_and_amount(self, level_id: str):
        """
        Get the price and amount for a given level, applying a minimum cost floor
        for the half-spread if configured.
        """
        level = self.get_level_from_level_id(level_id)
        trade_type = self.get_trade_type_from_level_id(level_id)
        spreads, amounts_quote = self.config.get_spreads_and_amounts_in_quote(trade_type)
        reference_price = Decimal(self.processed_data["reference_price"])
        spread_in_pct = Decimal(spreads[int(level)]) * Decimal(self.processed_data["spread_multiplier"])

        min_spread_pct = Decimal(self.processed_data.get("min_spread_pct", "0"))
        if min_spread_pct > Decimal("0") and spread_in_pct < min_spread_pct:
            spread_in_pct = min_spread_pct

        side_multiplier = Decimal("-1") if trade_type == TradeType.BUY else Decimal("1")
        order_price = reference_price * (1 + side_multiplier * spread_in_pct)
        return order_price, Decimal(amounts_quote[int(level)]) / order_price

    def get_executor_config(self, level_id: str, price: Decimal, amount: Decimal):
        """
        Generate executor configuration for a given level.

        Args:
            level_id: The level identifier (e.g., "buy_0", "sell_0")
            price: The order price
            amount: The order amount in base asset

        Returns:
            PositionExecutorConfig for the order level
        """
        trade_type = self.get_trade_type_from_level_id(level_id)

        return PositionExecutorConfig(
            timestamp=self.market_data_provider.time(),
            level_id=level_id,
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            entry_price=price,
            amount=amount,
            triple_barrier_config=self.config.triple_barrier_config,
            leverage=self.config.leverage,
            side=trade_type,
        )
