"""
In-Memory Paper Trading Engine for GlitchyGopher.

A lightweight fallback when OANDA is unavailable. Tracks virtual positions
and P&L against real market data from AlphaVantage.

No external dependencies required.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from core.config import Config

logger = logging.getLogger("memory_trader")


@dataclass
class Trade:
    """Represents a single paper trade."""
    trade_id: str
    instrument: str
    direction: str          # "long" or "short"
    units: int
    entry_price: float
    entry_time: float       # Unix timestamp
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    sentiment: str = ""     # Signal that triggered the trade
    status: str = "open"    # "open" or "closed"

    def close(self, exit_price: float):
        """Close the trade and calculate P&L."""
        self.exit_price = exit_price
        self.exit_time = time.time()
        self.status = "closed"

        if self.direction == "long":
            # Bought USD/JPY, profit when rate goes up
            self.pnl = (self.exit_price - self.entry_price) * self.units
        else:
            # Sold USD/JPY, profit when rate goes down
            self.pnl = (self.entry_price - self.exit_price) * abs(self.units)

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L at current market price."""
        if self.status == "closed":
            return self.pnl or 0.0
        if self.direction == "long":
            return (current_price - self.entry_price) * self.units
        else:
            return (self.entry_price - current_price) * abs(self.units)


class MemoryTrader:
    """
    In-memory paper trading engine.

    Tracks trades, calculates P&L, and provides portfolio summary.
    Designed as a drop-in fallback when OANDA is not configured.
    """

    INSTRUMENT = "USD_JPY"

    SIGNAL_MAP = {
        "BULLISH_SQUEEZE": "long",
        "GLITCH_PANIC": "short",
        "NEUTRAL": None,
    }

    def __init__(self, config: Config, persistence=None):
        self.config = config
        self.trades: List[Trade] = []
        self.starting_balance: float = 100_000.0  # Virtual $100K
        self._trade_counter = 0
        self._last_signal: Optional[str] = None
        self._persistence = persistence

        # Restore from disk if available
        if self._persistence:
            self._restore_from_persistence()

    def _next_trade_id(self) -> str:
        self._trade_counter += 1
        return f"mem-{self._trade_counter:04d}"

    def _restore_from_persistence(self):
        """Restore trade state from persisted JSON."""
        data = self._persistence.load()
        if not data:
            return

        metadata = data.get("metadata", {})
        self._trade_counter = metadata.get("trade_counter", 0)
        self._last_signal = metadata.get("last_signal")

        for td in data.get("trades", []):
            trade = Trade(
                trade_id=td["trade_id"],
                instrument=td["instrument"],
                direction=td["direction"],
                units=td["units"],
                entry_price=td["entry_price"],
                entry_time=td["entry_time"],
                exit_price=td.get("exit_price"),
                exit_time=td.get("exit_time"),
                pnl=td.get("pnl"),
                sentiment=td.get("sentiment", ""),
                status=td.get("status", "open"),
            )
            self.trades.append(trade)

        logger.info(
            f"Restored {len(self.trades)} trades from disk "
            f"(counter={self._trade_counter}, last_signal={self._last_signal})"
        )

    def _save_to_persistence(self):
        """Save current trade state to disk."""
        if not self._persistence:
            return
        self._persistence.save(
            self.trades,
            metadata={
                "trade_counter": self._trade_counter,
                "last_signal": self._last_signal,
                "engine": "memory",
            },
        )

    async def execute_signal(
        self,
        sentiment: str,
        rate: Optional[float] = None,
        yield_val: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a paper trade based on the current sentiment signal.

        Closes opposing positions before opening new ones.
        Returns trade details dict or None.
        """
        direction = self.SIGNAL_MAP.get(sentiment)
        if direction is None:
            return None

        if rate is None:
            logger.warning("Cannot execute trade: no current rate available.")
            return None

        # Don't open duplicate trades in the same direction
        if self._last_signal == sentiment:
            logger.info(f"Signal unchanged ({sentiment}). Skipping duplicate trade.")
            return None

        # Close any open positions in the opposite direction
        for trade in self.trades:
            if trade.status == "open" and trade.direction != direction:
                trade.close(rate)
                logger.info(
                    f"Closed {trade.direction.upper()} trade {trade.trade_id} "
                    f"@ {rate} | P&L: {trade.pnl:.2f} JPY"
                )

        # Open new position
        units = self.config.paper_trade_units
        if direction == "short":
            units = -units

        trade = Trade(
            trade_id=self._next_trade_id(),
            instrument=self.INSTRUMENT,
            direction=direction,
            units=units,
            entry_price=rate,
            entry_time=time.time(),
            sentiment=sentiment,
        )
        self.trades.append(trade)
        self._last_signal = sentiment

        result = {
            "trade_id": trade.trade_id,
            "instrument": self.INSTRUMENT,
            "direction": direction,
            "units": units,
            "fill_price": rate,
            "sentiment": sentiment,
            "rate_at_signal": rate,
            "yield_at_signal": yield_val,
            "engine": "memory",
        }

        logger.info(
            f"Memory paper trade: {direction.upper()} {abs(units)} "
            f"{self.INSTRUMENT} @ {rate} (trade {trade.trade_id})"
        )

        # Persist after every trade event
        self._save_to_persistence()

        return result

    async def get_account_summary(self, current_rate: Optional[float] = None) -> Dict[str, Any]:
        """Get virtual account summary."""
        realized_pnl = sum(t.pnl for t in self.trades if t.status == "closed" and t.pnl is not None)
        unrealized_pnl = 0.0
        open_count = 0

        if current_rate:
            for trade in self.trades:
                if trade.status == "open":
                    unrealized_pnl += trade.unrealized_pnl(current_rate)
                    open_count += 1

        return {
            "engine": "memory",
            "starting_balance": self.starting_balance,
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_pnl": round(realized_pnl + unrealized_pnl, 2),
            "open_trade_count": open_count,
            "total_trades": len(self.trades),
            "win_rate": self._win_rate(),
        }

    def _win_rate(self) -> Optional[float]:
        """Calculate win rate from closed trades."""
        closed = [t for t in self.trades if t.status == "closed" and t.pnl is not None]
        if not closed:
            return None
        wins = sum(1 for t in closed if t.pnl > 0)
        return round(wins / len(closed) * 100, 1)

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        return [
            {
                "trade_id": t.trade_id,
                "direction": t.direction,
                "units": t.units,
                "entry_price": t.entry_price,
                "sentiment": t.sentiment,
            }
            for t in self.trades
            if t.status == "open"
        ]

    def get_trade_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trade history."""
        recent = sorted(self.trades, key=lambda t: t.entry_time, reverse=True)[:limit]
        return [asdict(t) for t in recent]

    def format_summary_for_moltbook(self, current_rate: Optional[float] = None) -> str:
        """Format a summary string suitable for posting to Moltbook."""
        closed = [t for t in self.trades if t.status == "closed" and t.pnl is not None]
        open_trades = [t for t in self.trades if t.status == "open"]

        realized = sum(t.pnl for t in closed)
        unrealized = sum(t.unrealized_pnl(current_rate) for t in open_trades) if current_rate else 0

        lines = [f"📊 Paper Trading Log | {len(self.trades)} trades"]
        if open_trades:
            t = open_trades[-1]
            lines.append(f"Open: {t.direction.upper()} @ {t.entry_price}")
        lines.append(f"P&L: {realized + unrealized:+.1f} JPY")

        win_rate = self._win_rate()
        if win_rate is not None:
            lines.append(f"Win rate: {win_rate}%")

        return " | ".join(lines)
