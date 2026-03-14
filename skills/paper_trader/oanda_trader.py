"""
OANDA v20 Paper Trading Integration for GlitchyGopher.

Uses OANDA's Practice (demo) account to execute paper trades on USD/JPY
based on GlitchyGopher's sentiment signals.

Requires:
  - pip install v20
  - OANDA_API_KEY (practice account token)
  - OANDA_ACCOUNT_ID (practice account ID)
"""

import logging
from typing import Optional, Dict, Any
from core.config import Config

logger = logging.getLogger("oanda_trader")


class OandaTrader:
    """Executes paper trades on OANDA's Practice environment."""

    INSTRUMENT = "USD_JPY"

    # Map GlitchyGopher sentiments to trade directions
    SIGNAL_MAP = {
        "BULLISH_SQUEEZE": "long",    # Expect USD/JPY to rise
        "GLITCH_PANIC": "short",      # Expect BoJ intervention → JPY strengthens → rate drops
        "NEUTRAL": None,              # No trade
    }

    def __init__(self, config: Config):
        self.config = config
        self._ctx = None
        self._initialized = False

    def _get_context(self):
        """Lazily initialize the OANDA v20 context."""
        if not self._initialized:
            try:
                import v20
                hostname = (
                    "api-fxpractice.oanda.com"
                    if self.config.oanda_environment == "practice"
                    else "api-fxtrade.oanda.com"
                )
                self._ctx = v20.Context(
                    hostname,
                    token=self.config.oanda_api_key,
                )
                self._initialized = True
                logger.info(f"OANDA context initialized ({self.config.oanda_environment} environment)")
            except ImportError:
                logger.error("v20 package not installed. Run: pip install v20")
                self._initialized = True  # Don't retry
            except Exception as e:
                logger.error(f"Failed to initialize OANDA context: {e}")
                self._initialized = True
        return self._ctx

    async def execute_signal(
        self,
        sentiment: str,
        rate: Optional[float] = None,
        yield_val: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a paper trade based on the current sentiment signal.

        Returns a dict with trade details, or None if no trade was placed.
        """
        direction = self.SIGNAL_MAP.get(sentiment)
        if direction is None:
            logger.info(f"Signal {sentiment}: No trade action.")
            return None

        ctx = self._get_context()
        if ctx is None:
            logger.warning("OANDA context unavailable. Skipping trade.")
            return None

        units = self.config.paper_trade_units
        if direction == "short":
            units = -units

        try:
            response = ctx.order.market(
                self.config.oanda_account_id,
                instrument=self.INSTRUMENT,
                units=units,
            )

            if response.status == 201:
                order_fill = response.body.get("orderFillTransaction", {})
                trade_id = getattr(order_fill, "id", "unknown")
                fill_price = getattr(order_fill, "price", "unknown")

                result = {
                    "trade_id": trade_id,
                    "instrument": self.INSTRUMENT,
                    "direction": direction,
                    "units": units,
                    "fill_price": fill_price,
                    "sentiment": sentiment,
                    "rate_at_signal": rate,
                    "yield_at_signal": yield_val,
                }
                logger.info(
                    f"OANDA paper trade executed: {direction.upper()} {abs(units)} "
                    f"{self.INSTRUMENT} @ {fill_price} (trade {trade_id})"
                )
                return result
            else:
                logger.error(
                    f"OANDA order failed. Status: {response.status}, "
                    f"Body: {response.body}"
                )
                return None

        except Exception as e:
            logger.error(f"OANDA trade execution failed: {e}")
            return None

    async def get_account_summary(self) -> Optional[Dict[str, Any]]:
        """Fetch the current paper trading account summary."""
        ctx = self._get_context()
        if ctx is None:
            return None

        try:
            response = ctx.account.summary(self.config.oanda_account_id)
            if response.status == 200:
                account = response.body.get("account", {})
                return {
                    "balance": getattr(account, "balance", None),
                    "unrealized_pl": getattr(account, "unrealizedPL", None),
                    "open_trade_count": getattr(account, "openTradeCount", None),
                    "nav": getattr(account, "NAV", None),
                }
        except Exception as e:
            logger.error(f"Failed to fetch OANDA account summary: {e}")
        return None

    async def get_open_positions(self) -> Optional[Dict[str, Any]]:
        """Fetch open positions for USD/JPY."""
        ctx = self._get_context()
        if ctx is None:
            return None

        try:
            response = ctx.position.get(
                self.config.oanda_account_id,
                self.INSTRUMENT,
            )
            if response.status == 200:
                position = response.body.get("position", {})
                long_units = getattr(getattr(position, "long", None), "units", "0")
                short_units = getattr(getattr(position, "short", None), "units", "0")
                unrealized_pl = getattr(position, "unrealizedPL", "0")
                return {
                    "instrument": self.INSTRUMENT,
                    "long_units": long_units,
                    "short_units": short_units,
                    "unrealized_pl": unrealized_pl,
                }
        except Exception as e:
            logger.error(f"Failed to fetch OANDA positions: {e}")
        return None
