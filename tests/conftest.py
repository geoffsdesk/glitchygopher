"""Shared test fixtures for GlitchyGopher tests."""

import pytest
from core.config import Config


@pytest.fixture
def config():
    """Returns a Config with test defaults (no real API keys)."""
    return Config(
        gemini_api_key="test-gemini-key",
        alpha_vantage_key="test-av-key",
        moltbook_api_key="test-moltbook-key",
        yield_threshold=4.2,
        rate_threshold=148.0,
    )


@pytest.fixture
def config_no_keys():
    """Returns a Config with no API keys set."""
    return Config()
