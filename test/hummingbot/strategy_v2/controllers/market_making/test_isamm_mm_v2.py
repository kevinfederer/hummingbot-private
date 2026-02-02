import asyncio
from decimal import Decimal
from test.isolated_asyncio_wrapper_test_case import IsolatedAsyncioWrapperTestCase
from unittest.mock import MagicMock

from hummingbot.core.data_type.common import PositionMode, TradeType
from hummingbot.data_feed.market_data_provider import MarketDataProvider
from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.data_types import PositionSummary
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig


# Import the ISAMM controller
try:
    from controllers.market_making.isamm_mm_v2 import (
        ISAMMMM2Config,
        ISAMMMM2Controller,
    )
except ImportError:
    # Fallback for when running tests from different directory
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
    from controllers.market_making.isamm_mm_v2 import (
        ISAMMMM2Config,
        ISAMMMM2Controller,
    )


class TestISAMMMM2Config(IsolatedAsyncioWrapperTestCase):
    """Test ISAMM configuration class."""

    def test_default_config_values(self):
        """Test that default configuration values are set correctly."""
        config = ISAMMMM2Config(
            id="test_isamm",
            connector_name="binance_perpetual",
            trading_pair="ETH-USDT",
            total_amount_quote=Decimal("1000"),
            buy_spreads=[0.01, 0.02],
            sell_spreads=[0.01, 0.02],
            buy_amounts_pct=[50, 50],
            sell_amounts_pct=[50, 50],
            executor_refresh_time=300,
            cooldown_time=15,
            leverage=20,
            position_mode=PositionMode.HEDGE,
        )

        # Test ISAMM-specific defaults
        self.assertEqual(config.controller_name, "isamm_mm_v2")
        self.assertEqual(config.spread_bps, Decimal("0.001"))  # 0.1% = 10 bps
        self.assertEqual(config.risk_lambda, Decimal("0.10"))
        self.assertEqual(config.gamma_impact, Decimal("0.00"))
        self.assertEqual(config.kappa, Decimal("0.00"))
        self.assertEqual(config.lambda_inv, Decimal("0.00"))
        self.assertEqual(config.max_inventory, Decimal("50"))

    def test_custom_isamm_params(self):
        """Test configuration with custom ISAMM parameters."""
        config = ISAMMMM2Config(
            id="test_isamm_custom",
            connector_name="binance_perpetual",
            trading_pair="ETH-USDT",
            total_amount_quote=Decimal("1000"),
            buy_spreads=[0.01],
            sell_spreads=[0.01],
            buy_amounts_pct=[100],
            sell_amounts_pct=[100],
            executor_refresh_time=300,
            cooldown_time=15,
            leverage=20,
            position_mode=PositionMode.HEDGE,
            spread_bps=Decimal("0.002"),  # 0.2% = 20 bps
            risk_lambda=Decimal("0.15"),
            gamma_impact=Decimal("0.01"),
            kappa=Decimal("0.5"),
            lambda_inv=Decimal("0.1"),
            max_inventory=Decimal("100"),
        )

        self.assertEqual(config.spread_bps, Decimal("0.002"))
        self.assertEqual(config.risk_lambda, Decimal("0.15"))
        self.assertEqual(config.gamma_impact, Decimal("0.01"))
        self.assertEqual(config.kappa, Decimal("0.5"))
        self.assertEqual(config.lambda_inv, Decimal("0.1"))
        self.assertEqual(config.max_inventory, Decimal("100"))


class TestISAMMMM2Controller(IsolatedAsyncioWrapperTestCase):
    """Test ISAMM controller class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = ISAMMMM2Config(
            id="test_isamm_controller",
            controller_name="isamm_mm_v2",
            connector_name="binance_perpetual",
            trading_pair="ETH-USDT",
            total_amount_quote=Decimal("1000"),
            buy_spreads=[0.01, 0.02],
            sell_spreads=[0.01, 0.02],
            buy_amounts_pct=[50, 50],
            sell_amounts_pct=[50, 50],
            executor_refresh_time=300,
            cooldown_time=15,
            leverage=20,
            position_mode=PositionMode.HEDGE,
        )

        # Mock market data provider
        self.mock_market_data_provider = MagicMock(spec=MarketDataProvider)
        self.mock_actions_queue = asyncio.Queue()

        # Create controller instance
        self.controller = ISAMMMM2Controller(
            config=self.config,
            market_data_provider=self.mock_market_data_provider,
            actions_queue=self.mock_actions_queue
        )

    def test_controller_initialization(self):
        """Test that controller initializes correctly."""
        self.assertEqual(self.controller.config, self.config)
        self.assertEqual(self.controller.config.controller_name, "isamm_mm_v2")

    def test_net_inventory_base_empty_positions(self):
        """Test inventory calculation with no positions."""
        self.controller.positions_held = []
        inventory = self.controller._net_inventory_base()
        self.assertEqual(inventory, Decimal("0"))

    def test_net_inventory_base_buy_position(self):
        """Test inventory calculation with only buy positions."""
        mock_position = MagicMock(spec=PositionSummary)
        mock_position.connector_name = "binance_perpetual"
        mock_position.trading_pair = "ETH-USDT"
        mock_position.side = TradeType.BUY
        mock_position.amount = Decimal("10")

        self.controller.positions_held = [mock_position]
        inventory = self.controller._net_inventory_base()
        self.assertEqual(inventory, Decimal("10"))

    def test_net_inventory_base_sell_position(self):
        """Test inventory calculation with only sell positions."""
        mock_position = MagicMock(spec=PositionSummary)
        mock_position.connector_name = "binance_perpetual"
        mock_position.trading_pair = "ETH-USDT"
        mock_position.side = TradeType.SELL
        mock_position.amount = Decimal("5")

        self.controller.positions_held = [mock_position]
        inventory = self.controller._net_inventory_base()
        self.assertEqual(inventory, Decimal("-5"))

    def test_net_inventory_base_mixed_positions(self):
        """Test inventory calculation with both buy and sell positions."""
        mock_buy = MagicMock(spec=PositionSummary)
        mock_buy.connector_name = "binance_perpetual"
        mock_buy.trading_pair = "ETH-USDT"
        mock_buy.side = TradeType.BUY
        mock_buy.amount = Decimal("10")

        mock_sell = MagicMock(spec=PositionSummary)
        mock_sell.connector_name = "binance_perpetual"
        mock_sell.trading_pair = "ETH-USDT"
        mock_sell.side = TradeType.SELL
        mock_sell.amount = Decimal("3")

        # Position for different trading pair (should be ignored)
        mock_other = MagicMock(spec=PositionSummary)
        mock_other.connector_name = "binance_perpetual"
        mock_other.trading_pair = "BTC-USDT"
        mock_other.side = TradeType.BUY
        mock_other.amount = Decimal("100")

        # Position for different connector (should be ignored)
        mock_other_connector = MagicMock(spec=PositionSummary)
        mock_other_connector.connector_name = "binance"
        mock_other_connector.trading_pair = "ETH-USDT"
        mock_other_connector.side = TradeType.BUY
        mock_other_connector.amount = Decimal("50")

        self.controller.positions_held = [mock_buy, mock_sell, mock_other, mock_other_connector]
        inventory = self.controller._net_inventory_base()
        # 10 - 3 = 7 (other positions ignored)
        self.assertEqual(inventory, Decimal("7"))

    async def test_update_processed_data_basic(self):
        """Test basic update of processed data."""
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)
        self.controller.positions_held = []

        await self.controller.update_processed_data()

        self.assertEqual(self.controller.processed_data["mid_price"], mid_price)
        self.assertEqual(self.controller.processed_data["inventory_base"], Decimal("0"))
        self.assertEqual(self.controller.processed_data["obi"], Decimal("0"))
        self.assertEqual(self.controller.processed_data["expected_mid"], mid_price)
        self.assertEqual(self.controller.processed_data["skew_price"], Decimal("0"))
        self.assertEqual(self.controller.processed_data["reference_price"], mid_price)
        self.assertEqual(
            self.controller.processed_data["spread_multiplier"],
            self.config.spread_bps
        )

    async def test_update_processed_data_with_inventory_skew(self):
        """Test processed data update with inventory skew."""
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)

        # Set lambda_inv for inventory skew
        self.config.lambda_inv = Decimal("0.1")

        # Add a buy position
        mock_position = MagicMock(spec=PositionSummary)
        mock_position.connector_name = "binance_perpetual"
        mock_position.trading_pair = "ETH-USDT"
        mock_position.side = TradeType.BUY
        mock_position.amount = Decimal("5")
        self.controller.positions_held = [mock_position]

        await self.controller.update_processed_data()

        # Inventory = 5
        self.assertEqual(self.controller.processed_data["inventory_base"], Decimal("5"))

        # Expected mid = 100 (kappa = 0)
        self.assertEqual(self.controller.processed_data["expected_mid"], Decimal("100"))

        # Skew price = 0.1 * 5 = 0.5
        self.assertEqual(self.controller.processed_data["skew_price"], Decimal("0.5"))

        # Reference price = 100 - 0.5 = 99.5
        self.assertEqual(self.controller.processed_data["reference_price"], Decimal("99.5"))

    async def test_update_processed_data_with_obi(self):
        """Test processed data update with order book imbalance."""
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)
        self.controller.positions_held = []

        # Set kappa for OBI adjustment
        self.config.kappa = Decimal("0.5")

        await self.controller.update_processed_data()

        # expected_mid = mid + kappa * obi (obi is currently 0)
        # When OBI is implemented, this will adjust the expected mid price
        self.assertEqual(self.controller.processed_data["expected_mid"], mid_price)

    async def test_update_processed_data_combined_skew_and_obi(self):
        """Test processed data update with both inventory and OBI effects."""
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)

        # Configure both lambda_inv and kappa
        self.config.lambda_inv = Decimal("0.2")
        self.config.kappa = Decimal("0.3")

        # Add a sell position (negative inventory)
        mock_position = MagicMock(spec=PositionSummary)
        mock_position.connector_name = "binance_perpetual"
        mock_position.trading_pair = "ETH-USDT"
        mock_position.side = TradeType.SELL
        mock_position.amount = Decimal("10")
        self.controller.positions_held = [mock_position]

        await self.controller.update_processed_data()

        # Inventory = -10
        self.assertEqual(self.controller.processed_data["inventory_base"], Decimal("-10"))

        # Expected mid = 100 (kappa * obi, but obi = 0)
        self.assertEqual(self.controller.processed_data["expected_mid"], Decimal("100"))

        # Skew price = 0.2 * (-10) = -2
        self.assertEqual(self.controller.processed_data["skew_price"], Decimal("-2"))

        # Reference price = 100 - (-2) = 102
        self.assertEqual(self.controller.processed_data["reference_price"], Decimal("102"))

    def test_get_executor_config_buy_side(self):
        """Test executor config generation for buy side."""
        self.mock_market_data_provider.time.return_value = 1234567890

        executor_config = self.controller.get_executor_config(
            level_id="buy_0",
            price=Decimal("99"),
            amount=Decimal("1.5")
        )

        self.assertIsInstance(executor_config, PositionExecutorConfig)
        self.assertEqual(executor_config.level_id, "buy_0")
        self.assertEqual(executor_config.connector_name, "binance_perpetual")
        self.assertEqual(executor_config.trading_pair, "ETH-USDT")
        self.assertEqual(executor_config.entry_price, Decimal("99"))
        self.assertEqual(executor_config.amount, Decimal("1.5"))
        self.assertEqual(executor_config.side, TradeType.BUY)
        self.assertEqual(executor_config.leverage, 20)

    def test_get_executor_config_sell_side(self):
        """Test executor config generation for sell side."""
        self.mock_market_data_provider.time.return_value = 1234567890

        executor_config = self.controller.get_executor_config(
            level_id="sell_0",
            price=Decimal("101"),
            amount=Decimal("1.0")
        )

        self.assertIsInstance(executor_config, PositionExecutorConfig)
        self.assertEqual(executor_config.level_id, "sell_0")
        self.assertEqual(executor_config.side, TradeType.SELL)

    def test_get_executor_config_triple_barrier_config(self):
        """Test that executor config includes triple barrier configuration."""
        self.mock_market_data_provider.time.return_value = 1234567890

        executor_config = self.controller.get_executor_config(
            level_id="buy_0",
            price=Decimal("99"),
            amount=Decimal("1.5")
        )

        # Check that triple barrier config is passed through
        self.assertEqual(executor_config.triple_barrier_config, self.config.triple_barrier_config)

    async def test_spread_multiplier_is_configurable(self):
        """Test that spread multiplier can be configured via config."""
        self.config.spread_bps = Decimal("0.002")  # 0.2%
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)
        self.controller.positions_held = []

        await self.controller.update_processed_data()

        self.assertEqual(
            self.controller.processed_data["spread_multiplier"],
            Decimal("0.002")
        )

    async def test_reference_price_adjustment_direction(self):
        """Test that reference price adjusts in correct direction based on inventory."""
        mid_price = Decimal("100")
        self.mock_market_data_provider.get_price_by_type.return_value = float(mid_price)

        self.config.lambda_inv = Decimal("0.1")

        # Test with positive inventory (should lower reference price to encourage selling)
        mock_buy = MagicMock(spec=PositionSummary)
        mock_buy.connector_name = "binance_perpetual"
        mock_buy.trading_pair = "ETH-USDT"
        mock_buy.side = TradeType.BUY
        mock_buy.amount = Decimal("10")
        self.controller.positions_held = [mock_buy]

        await self.controller.update_processed_data()
        ref_price_with_buy = self.controller.processed_data["reference_price"]

        # Test with negative inventory (should raise reference price to encourage buying)
        self.controller.positions_held = []
        mock_sell = MagicMock(spec=PositionSummary)
        mock_sell.connector_name = "binance_perpetual"
        mock_sell.trading_pair = "ETH-USDT"
        mock_sell.side = TradeType.SELL
        mock_sell.amount = Decimal("10")
        self.controller.positions_held = [mock_sell]

        await self.controller.update_processed_data()
        ref_price_with_sell = self.controller.processed_data["reference_price"]

        # Reference price should be lower when we have buy position (to encourage selling)
        # Reference price should be higher when we have sell position (to encourage buying)
        self.assertLess(ref_price_with_buy, Decimal("100"))
        self.assertGreater(ref_price_with_sell, Decimal("100"))