"""Tests for configuration loading."""

import os
import pytest
from core.config import Config


class TestConfig:

    def test_defaults(self):
        """Config should have sensible defaults."""
        config = Config()
        assert config.yield_threshold == 4.2
        assert config.rate_threshold == 148.0
        assert config.fetch_interval_seconds == 3600
        assert config.post_cooldown_seconds == 1860
        assert config.heartbeat_seconds == 60
        assert config.paper_trading_enabled is False

    def test_load_from_env(self, monkeypatch):
        """Config.load() should read from environment variables."""
        monkeypatch.setenv("GEMINI_API_KEY", "gem-123")
        monkeypatch.setenv("ALPHA_VANTAGE_KEY", "av-456")
        monkeypatch.setenv("MOLTBOOK_API_KEY", "mb-789")
        monkeypatch.setenv("YIELD_THRESHOLD", "4.5")
        monkeypatch.setenv("RATE_THRESHOLD", "150.0")
        monkeypatch.setenv("HEARTBEAT_SECONDS", "30")

        config = Config.load()
        assert config.gemini_api_key == "gem-123"
        assert config.alpha_vantage_key == "av-456"
        assert config.moltbook_api_key == "mb-789"
        assert config.yield_threshold == 4.5
        assert config.rate_threshold == 150.0
        assert config.heartbeat_seconds == 30

    def test_invalid_int_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("HEARTBEAT_SECONDS", "not_a_number")
        config = Config.load()
        assert config.heartbeat_seconds == 60  # default

    def test_invalid_float_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("YIELD_THRESHOLD", "abc")
        config = Config.load()
        assert config.yield_threshold == 4.2  # default

    def test_paper_trading_auto_enabled_with_oanda_key(self, monkeypatch):
        monkeypatch.setenv("OANDA_API_KEY", "oanda-test-key")
        monkeypatch.setenv("OANDA_ACCOUNT_ID", "001-001-001")
        config = Config.load()
        assert config.paper_trading_enabled is True

    def test_paper_trading_disabled_without_oanda_key(self, monkeypatch):
        monkeypatch.delenv("OANDA_API_KEY", raising=False)
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        config = Config.load()
        assert config.paper_trading_enabled is False  # No key = forced off

    def test_bool_parsing(self, monkeypatch):
        monkeypatch.setenv("OANDA_API_KEY", "key")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        config = Config.load()
        assert config.paper_trading_enabled is False
