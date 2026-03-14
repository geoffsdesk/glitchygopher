"""Tests for the LRUSet used to track replied posts."""

from skills.usd_jpy_expert.skill import LRUSet


class TestLRUSet:

    def test_basic_add_and_contains(self):
        s = LRUSet(maxsize=5)
        s.add("a")
        s.add("b")
        assert "a" in s
        assert "b" in s
        assert "c" not in s

    def test_eviction_at_capacity(self):
        s = LRUSet(maxsize=3)
        s.add("a")
        s.add("b")
        s.add("c")
        s.add("d")  # "a" should be evicted
        assert "a" not in s
        assert "b" in s
        assert "d" in s
        assert len(s) == 3

    def test_access_refreshes_order(self):
        s = LRUSet(maxsize=3)
        s.add("a")
        s.add("b")
        s.add("c")
        s.add("a")  # Re-add "a" → refreshes it to most recent
        s.add("d")  # Now "b" (oldest) should be evicted
        assert "a" in s
        assert "b" not in s
        assert "c" in s
        assert "d" in s

    def test_empty_set(self):
        s = LRUSet(maxsize=10)
        assert "anything" not in s
        assert len(s) == 0
