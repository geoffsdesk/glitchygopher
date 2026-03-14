"""Tests for the HTTP trading API endpoints."""

import json
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from core.config import Config
from core.main import GlitchyServer
from skills.usd_jpy_expert.skill import UsdJpySkill
from skills.paper_trader.trader import PaperTrader


@pytest.fixture
def config():
    return Config(
        gemini_api_key="test",
        alpha_vantage_key="test",
        moltbook_api_key="test",
        trade_persistence_enabled=False,
    )


@pytest.fixture
def skill(config):
    s = UsdJpySkill(config)
    s.current_rate = 152.5
    s.current_yield = 4.3
    s.sentiment = "NEUTRAL"
    return s


@pytest.fixture
def trader(config):
    return PaperTrader(config)


@pytest.fixture
async def server(config, skill, trader):
    srv = GlitchyServer(port=0, trader=trader, skill=skill)
    return srv


@pytest.fixture
async def client(aiohttp_client, server):
    return await aiohttp_client(server._app)


class TestHealthEndpoints:

    @pytest.mark.asyncio
    async def test_healthz(self, aiohttp_client, config, skill, trader):
        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        srv._start_time = 1000.0
        client = await aiohttp_client(srv._app)

        resp = await client.get("/healthz")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_readyz_not_ready(self, aiohttp_client, config, skill, trader):
        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/readyz")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "not_ready"

    @pytest.mark.asyncio
    async def test_readyz_ready(self, aiohttp_client, config, skill, trader):
        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        srv.is_ready = True
        srv.last_heartbeat = 12345.0
        client = await aiohttp_client(srv._app)

        resp = await client.get("/readyz")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ready"


class TestTradesEndpoints:

    @pytest.mark.asyncio
    async def test_trades_empty(self, aiohttp_client, config, skill, trader):
        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/trades")
        assert resp.status == 200
        data = await resp.json()
        assert data["engine"] == "memory"
        assert data["market"]["usd_jpy"] == 152.5
        assert data["market"]["us10y"] == 4.3
        assert data["market"]["sentiment"] == "NEUTRAL"
        assert data["account"]["open_trade_count"] == 0

    @pytest.mark.asyncio
    async def test_trades_with_position(self, aiohttp_client, config, skill, trader):
        # Place a trade first
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5, yield_val=4.5)

        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/trades")
        data = await resp.json()
        assert data["account"]["open_trade_count"] == 1
        assert len(data["open_positions"]) == 1
        assert data["open_positions"][0]["direction"] == "long"

    @pytest.mark.asyncio
    async def test_trades_history(self, aiohttp_client, config, skill, trader):
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5)

        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/trades/history")
        assert resp.status == 200
        data = await resp.json()
        assert data["engine"] == "memory"
        assert data["count"] == 1
        assert data["trades"][0]["direction"] == "long"

    @pytest.mark.asyncio
    async def test_trades_history_with_limit(self, aiohttp_client, config, skill, trader):
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5)
        await trader.execute_signal("GLITCH_PANIC", rate=148.0)

        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/trades/history?limit=1")
        data = await resp.json()
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_trades_summary(self, aiohttp_client, config, skill, trader):
        await trader.execute_signal("BULLISH_SQUEEZE", rate=146.5)

        srv = GlitchyServer(port=0, trader=trader, skill=skill)
        client = await aiohttp_client(srv._app)

        resp = await client.get("/trades/summary")
        assert resp.status == 200
        data = await resp.json()
        assert "Paper Trading Log" in data["summary"]
        assert data["account"] is not None
