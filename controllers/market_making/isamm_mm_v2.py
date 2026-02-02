from decimal import Decimal
from typing import List

from pydantic import Field

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

        self.processed_data = {
            "mid_price": mid_price,
            "inventory_base": inventory,
            "obi": obi,
            "expected_mid": expected_mid,
            "skew_price": skew_price,
            "reference_price": reference_price,
            "spread_multiplier": spread_multiplier,
        }

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