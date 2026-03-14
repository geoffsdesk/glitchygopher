"""
Unified Paper Trader — facade that delegates to OANDA or in-memory engine.

Usage:
    trader = PaperTrader(config)
    result = await trader.execute_signal("BULLISH_SQUEEZE", rate=152.5, yield_val=4.3)
"""

import logging
from typing import Optional, Dict, Any, List
from core.config import Config

logger = logging.getLogger("paper_trader")


class PaperTrader:
    """
    Unified paper trading interface.

    If OANDA is configured, uses the OANDA Practice account.
    Otherwise, falls back to the in-memory trading engine.
    Optionally persists trade history to JSON.
    """

    def __init__(self, config: Config):
        self.config = config
        self._engine = None
        self._engine_name = "none"
        self._persistence = None

        # Set up persistence if enabled
        if config.trade_persistence_enabled:
            from skills.paper_trader.persistence import TradePersistence
            self._persistence = TradePersistence(config.trade_history_path)

        if config.paper_trading_enabled and config.oanda_api_key:
            try:
                from skills.paper_trader.oanda_trader import OandaTrader
                self._engine = OandaTrader(config)
                self._engine_name = "oanda"
                logger.info("Paper trading engine: OANDA Practice")
            except Exception as e:
                logger.error(f"Failed to init OANDA trader, falling back to memory: {e}")

        if self._engine is None:
            from skills.paper_trader.memory_trader import MemoryTrader
            self._engine = MemoryTrader(config, persistence=self._persistence)
            self._engine_name = "memory"
            logger.info("Paper trading engine: In-Memory")

    @property
    def engine_name(self) -> str:
        return self._engine_name

    async def execute_signal(
        self,
        sentiment: str,
        rate: Optional[float] = None,
        yield_val: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a paper trade based on the sentiment signal."""
        if self._engine is None:
            return None

        result = await self._engine.execute_signal(
            sentiment=sentiment,
            rate=rate,
            yield_val=yield_val,
        )

        if result:
            result["engine"] = self._engine_name

        return result

    async def get_account_summary(self, current_rate: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Get account summary from the active engine."""
        if self._engine is None:
            return None

        if self._engine_name == "memory":
            return await self._engine.get_account_summary(current_rate=current_rate)
        else:
            return await self._engine.get_account_summary()

    async def get_open_positions(self) -> Optional[Any]:
        """Get open positions from the active engine."""
        if self._engine is None:
            return None
        return await self._engine.get_open_positions()

    def get_trade_history(self, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """Get recent trade history (memory engine only)."""
        if self._engine_name == "memory" and hasattr(self._engine, "get_trade_history"):
            return self._engine.get_trade_history(limit=limit)
        return None

    def format_summary_for_moltbook(self, current_rate: Optional[float] = None) -> Optional[str]:
        """Get a Moltbook-ready summary string (memory engine only)."""
        if self._engine_name == "memory" and hasattr(self._engine, "format_summary_for_moltbook"):
            return self._engine.format_summary_for_moltbook(current_rate=current_rate)
        return None

    def has_trades(self) -> bool:
        """Check if any trades have been executed."""
        if self._engine_name == "memory":
            return len(self._engine.trades) > 0
        return False  # OANDA always has trades visible in their dashboard
