"""Tests for trade history persistence."""

import json
import os
import tempfile
import pytest
from skills.paper_trader.persistence import TradePersistence
from skills.paper_trader.memory_trader import Trade


@pytest.fixture
def tmp_path():
    """Create a temp directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "trades.json")


class TestTradePersistence:

    def test_save_and_load(self, tmp_path):
        p = TradePersistence(tmp_path)
        trades = [
            Trade(
                trade_id="mem-0001", instrument="USD_JPY",
                direction="long", units=1000,
                entry_price=146.5, entry_time=1000.0,
                sentiment="BULLISH_SQUEEZE",
            ),
            Trade(
                trade_id="mem-0002", instrument="USD_JPY",
                direction="short", units=-1000,
                entry_price=148.0, entry_time=2000.0,
                exit_price=146.0, exit_time=3000.0,
                pnl=2000.0, sentiment="GLITCH_PANIC", status="closed",
            ),
        ]
        p.save(trades, metadata={"trade_counter": 2, "last_signal": "GLITCH_PANIC"})

        data = p.load()
        assert data is not None
        assert data["trade_count"] == 2
        assert data["version"] == 1
        assert data["metadata"]["trade_counter"] == 2
        assert data["metadata"]["last_signal"] == "GLITCH_PANIC"

        loaded_trades = data["trades"]
        assert loaded_trades[0]["trade_id"] == "mem-0001"
        assert loaded_trades[0]["direction"] == "long"
        assert loaded_trades[1]["status"] == "closed"
        assert loaded_trades[1]["pnl"] == 2000.0

    def test_load_nonexistent_file(self, tmp_path):
        p = TradePersistence(tmp_path)
        assert p.load() is None

    def test_load_corrupt_file(self, tmp_path):
        # Write garbage
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        with open(tmp_path, "w") as f:
            f.write("{not valid json!!!")
        p = TradePersistence(tmp_path)
        assert p.load() is None

    def test_exists(self, tmp_path):
        p = TradePersistence(tmp_path)
        assert p.exists() is False
        p.save([])
        assert p.exists() is True

    def test_save_empty_list(self, tmp_path):
        p = TradePersistence(tmp_path)
        p.save([])
        data = p.load()
        assert data["trade_count"] == 0
        assert data["trades"] == []

    def test_atomic_write(self, tmp_path):
        """Verify no .tmp file remains after save."""
        p = TradePersistence(tmp_path)
        p.save([])
        assert not os.path.exists(tmp_path + ".tmp")
        assert os.path.exists(tmp_path)


class TestMemoryTraderWithPersistence:

    @pytest.mark.asyncio
    async def test_trades_survive_restart(self, tmp_path):
        from core.config import Config
        config = Config(paper_trade_units=1000)

        p = TradePersistence(tmp_path)

        # First instance: execute some trades
        from skills.paper_trader.memory_trader import MemoryTrader
        trader1 = MemoryTrader(config, persistence=p)
        await trader1.execute_signal("BULLISH_SQUEEZE", rate=146.0)
        assert len(trader1.trades) == 1

        # Second instance: should restore the trade
        trader2 = MemoryTrader(config, persistence=p)
        assert len(trader2.trades) == 1
        assert trader2.trades[0].trade_id == "mem-0001"
        assert trader2.trades[0].entry_price == 146.0
        assert trader2._trade_counter == 1
        assert trader2._last_signal == "BULLISH_SQUEEZE"

    @pytest.mark.asyncio
    async def test_counter_continues_after_restore(self, tmp_path):
        from core.config import Config
        from skills.paper_trader.memory_trader import MemoryTrader as MT
        config = Config(paper_trade_units=1000)

        p = TradePersistence(tmp_path)

        trader1 = MT(config, persistence=p)
        await trader1.execute_signal("BULLISH_SQUEEZE", rate=146.0)

        # Restore and execute a new trade
        trader2 = MT(config, persistence=p)
        await trader2.execute_signal("GLITCH_PANIC", rate=148.0)

        assert len(trader2.trades) == 2  # original long (closed in-place) + new short
        # Original trade should be closed
        assert trader2.trades[0].status == "closed"
        assert trader2.trades[0].pnl == 2000.0  # (148-146) * 1000
        # New trade should have incremented counter
        assert trader2.trades[1].trade_id == "mem-0002"
        assert trader2.trades[1].direction == "short"
        assert trader2.trades[1].status == "open"
