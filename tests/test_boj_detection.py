"""Tests for BoJ intervention detection from Moltbook feed."""

import pytest
from skills.usd_jpy_expert.skill import UsdJpySkill


class TestBojDetection:
    """Tests for _scan_for_boj_intervention."""

    def _make_post(self, title="", content="", author="trader1", post_id="p1"):
        return {
            "id": post_id,
            "title": title,
            "content": content,
            "author": {"name": author},
        }

    def test_detects_intervention_keyword(self, config):
        skill = UsdJpySkill(config)
        posts = [self._make_post(content="BoJ just announced intervention in FX markets")]
        assert skill._scan_for_boj_intervention(posts) is True

    def test_detects_boj_intervene(self, config):
        skill = UsdJpySkill(config)
        posts = [self._make_post(title="Breaking: BoJ intervene to support yen")]
        assert skill._scan_for_boj_intervention(posts) is True

    def test_detects_yen_buying(self, config):
        skill = UsdJpySkill(config)
        posts = [self._make_post(content="massive yen buying detected in tokyo session")]
        assert skill._scan_for_boj_intervention(posts) is True

    def test_detects_rate_check(self, config):
        skill = UsdJpySkill(config)
        posts = [self._make_post(content="BoJ conducting rate check right now")]
        assert skill._scan_for_boj_intervention(posts) is True

    def test_no_panic_on_normal_posts(self, config):
        skill = UsdJpySkill(config)
        posts = [
            self._make_post(content="USD/JPY looking bullish today"),
            self._make_post(content="carry trade is heating up"),
        ]
        assert skill._scan_for_boj_intervention(posts) is False

    def test_no_panic_on_empty_feed(self, config):
        skill = UsdJpySkill(config)
        assert skill._scan_for_boj_intervention([]) is False

    def test_case_insensitive(self, config):
        skill = UsdJpySkill(config)
        posts = [self._make_post(content="CURRENCY INTERVENTION by central bank")]
        assert skill._scan_for_boj_intervention(posts) is True
