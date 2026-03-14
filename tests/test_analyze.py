"""Tests for the _analyze() signal logic in UsdJpySkill."""

import pytest
from skills.usd_jpy_expert.skill import UsdJpySkill


class TestAnalyze:
    """Tests for 'The Glitch' analytical logic."""

    def _make_skill(self, config, rate=None, yield_val=None, boj_panic=False):
        skill = UsdJpySkill(config)
        skill.current_rate = rate
        skill.current_yield = yield_val
        skill.boj_panic_active = boj_panic
        return skill

    def test_neutral_when_both_below_threshold(self, config):
        """Yield below threshold, rate above threshold → NEUTRAL."""
        skill = self._make_skill(config, rate=155.0, yield_val=3.8)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_neutral_when_yield_high_rate_high(self, config):
        """Yield above threshold but rate ALSO above threshold → NEUTRAL."""
        skill = self._make_skill(config, rate=150.0, yield_val=4.5)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_neutral_when_yield_low_rate_low(self, config):
        """Yield below threshold even though rate below threshold → NEUTRAL."""
        skill = self._make_skill(config, rate=145.0, yield_val=3.5)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_bullish_squeeze_detected(self, config):
        """Yield > 4.2% AND rate < 148 → BULLISH_SQUEEZE."""
        skill = self._make_skill(config, rate=146.5, yield_val=4.5)
        skill._analyze()
        assert skill.sentiment == "BULLISH_SQUEEZE"

    def test_bullish_squeeze_boundary_yield(self, config):
        """Yield exactly at threshold (4.2) is NOT > 4.2 → NEUTRAL."""
        skill = self._make_skill(config, rate=146.0, yield_val=4.2)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_bullish_squeeze_boundary_rate(self, config):
        """Rate exactly at threshold (148.0) is NOT < 148 → NEUTRAL."""
        skill = self._make_skill(config, rate=148.0, yield_val=4.5)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_glitch_panic_overrides_bullish(self, config):
        """BoJ panic should override even if bullish conditions are also met."""
        skill = self._make_skill(config, rate=146.5, yield_val=4.5, boj_panic=True)
        skill._analyze()
        assert skill.sentiment == "GLITCH_PANIC"

    def test_glitch_panic_from_feed(self, config):
        """BoJ panic from feed scanning → GLITCH_PANIC regardless of data."""
        skill = self._make_skill(config, rate=155.0, yield_val=3.5, boj_panic=True)
        skill._analyze()
        assert skill.sentiment == "GLITCH_PANIC"

    def test_neutral_when_no_data(self, config):
        """No market data → NEUTRAL (no crash)."""
        skill = self._make_skill(config, rate=None, yield_val=None)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_neutral_when_partial_data(self, config):
        """Only rate, no yield → NEUTRAL."""
        skill = self._make_skill(config, rate=146.0, yield_val=None)
        skill._analyze()
        assert skill.sentiment == "NEUTRAL"

    def test_custom_thresholds(self):
        """Custom config thresholds should be respected."""
        from core.config import Config
        custom_config = Config(
            gemini_api_key="k", alpha_vantage_key="k", moltbook_api_key="k",
            yield_threshold=5.0,
            rate_threshold=160.0,
        )
        skill = UsdJpySkill(custom_config)
        skill.current_rate = 155.0
        skill.current_yield = 5.5
        skill._analyze()
        assert skill.sentiment == "BULLISH_SQUEEZE"

        # Same values but default thresholds would NOT trigger
        skill2 = UsdJpySkill(Config(
            gemini_api_key="k", alpha_vantage_key="k", moltbook_api_key="k",
        ))
        skill2.current_rate = 155.0
        skill2.current_yield = 5.5
        skill2._analyze()
        assert skill2.sentiment == "NEUTRAL"  # rate 155 is NOT < 148
