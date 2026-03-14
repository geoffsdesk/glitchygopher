"""Tests for the in-memory paper trading engine."""

import pytest
from core.config import Config
from skills.paper_trader.memory_trader import MemoryTrader, Trade


@pytest.fixture
def trader():
    config = Config(paper_trade_units=1000)
    return MemoryTrader(config)


class TestMemoryTrader:

    @pytest.mark.asyncio
    async def test_no_trade_on_neutral(self, trader):
        result = await trader.execute_signal("NEUTRAL", rate=152.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_long_on_bullish(self, trader):
        result = await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5, yield_val=4.5)
        assert result is not None
        assert result["direction"] == "long"
        assert result["units"] == 1000
        assert result["fill_price"] == 146.5

    @pytest.mark.asyncio
    async def test_short_on_panic(self, trader):
        result = await trader.execute_signal("GLITCH_PANIC", rate=155.0, yield_val=3.8)
        assert result is not None
        assert result["direction"] == "short"
        assert result["units"] == -1000
        assert result["fill_price"] == 155.0

    @pytest.mark.asyncio
    async def test_no_duplicate_trades(self, trader):
        r1 = await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5)
        r2 = await trader.execute_signal("BULLISH_SQUEEZE", rate=147.0)
        assert r1 is not None
        assert r2 is None  # Same signal, should skip

    @pytest.mark.asyncio
    async def test_closes_opposing_position(self, trader):
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5)
        assert len([t for t in trader.trades if t.status == "open"]) == 1

        await trader.execute_signal("GLITCH_PANIC", rate=148.0)
        # The long should be closed, short should be open
        closed = [t for t in trader.trades if t.status == "closed"]
        open_t = [t for t in trader.trades if t.status == "open"]
        assert len(closed) == 1
        assert closed[0].direction == "long"
        assert closed[0].pnl == (148.0 - 146.5) * 1000  # Profit on long
        assert len(open_t) == 1
        assert open_t[0].direction == "short"

    @pytest.mark.asyncio
    async def test_no_trade_without_rate(self, trader):
        result = await trader.execute_signal("BULLISH_SQUEEZE", rate=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_account_summary(self, trader):
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.0)
        summary = await trader.get_account_summary(current_rate=147.0)
        assert summary["open_trade_count"] == 1
        assert summary["unrealized_pnl"] == (147.0 - 146.0) * 1000

    @pytest.mark.asyncio
    async def test_win_rate(self, trader):
        # Win
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.0)
        await trader.execute_signal("GLITCH_PANIC", rate=148.0)  # Closes long at profit

        # Loss
        await trader.execute_signal("BULLISH_SQUEEZE", rate=150.0)  # Closes short at loss
        # Force close the last trade
        for t in trader.trades:
            if t.status == "open":
                t.close(149.0)

        summary = await trader.get_account_summary()
        assert summary["win_rate"] is not None


class TestTrade:

    def test_long_pnl_profit(self):
        trade = Trade(
            trade_id="t1", instrument="USD_JPY",
            direction="long", units=1000,
            entry_price=146.0, entry_time=0,
        )
        trade.close(148.0)
        assert trade.pnl == 2000.0  # (148-146) * 1000

    def test_long_pnl_loss(self):
        trade = Trade(
            trade_id="t1", instrument="USD_JPY",
            direction="long", units=1000,
            entry_price=148.0, entry_time=0,
        )
        trade.close(146.0)
        assert trade.pnl == -2000.0

    def test_short_pnl_profit(self):
        trade = Trade(
            trade_id="t1", instrument="USD_JPY",
            direction="short", units=-1000,
            entry_price=155.0, entry_time=0,
        )
        trade.close(152.0)
        assert trade.pnl == 3000.0  # (155-152) * 1000

    def test_short_pnl_loss(self):
        trade = Trade(
            trade_id="t1", instrument="USD_JPY",
            direction="short", units=-1000,
            entry_price=152.0, entry_time=0,
        )
        trade.close(155.0)
        assert trade.pnl == -3000.0

    def test_unrealized_pnl(self):
        trade = Trade(
            trade_id="t1", instrument="USD_JPY",
            direction="long", units=1000,
            entry_price=146.0, entry_time=0,
        )
        assert trade.unrealized_pnl(148.0) == 2000.0
        assert trade.unrealized_pnl(144.0) == -2000.0
