"""On-disk TTL cache for live completion candidates.

The cache keeps ``<TAB>`` fast and stops repeated completions from re-hitting the
API. It is fail-soft by contract: a missing, corrupt or unwritable cache is a
miss, never an exception — completion must never error or hang.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vsc.gen.complete_cache import cache_dir, cache_ttl, get_or_fetch


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("VSC_COMPLETE_TTL", raising=False)


def test_hit_within_ttl_skips_fetch() -> None:
    calls = 0

    def fetch() -> list[tuple[str, str]]:
        nonlocal calls
        calls += 1
        return [("vm-1", "web"), ("vm-2", "db")]

    first = get_or_fetch("k", ttl=60.0, fetch_fn=fetch, now=1000.0)
    second = get_or_fetch("k", ttl=60.0, fetch_fn=fetch, now=1059.0)
    assert first == [("vm-1", "web"), ("vm-2", "db")]
    assert second == first
    assert calls == 1  # served from cache the second time


def test_expired_entry_refetches() -> None:
    calls = 0

    def fetch() -> list[tuple[str, str]]:
        nonlocal calls
        calls += 1
        return [(f"vm-{calls}", "x")]

    get_or_fetch("k", ttl=60.0, fetch_fn=fetch, now=1000.0)
    again = get_or_fetch("k", ttl=60.0, fetch_fn=fetch, now=1061.0)
    assert calls == 2
    assert again == [("vm-2", "x")]


def test_corrupt_file_is_a_miss() -> None:
    # Pre-create a garbage cache file at the key's path; get_or_fetch must treat
    # it as a miss and never raise.
    get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("a", "a")], now=0.0)
    files = list(cache_dir().glob("*.json"))
    assert files
    files[0].write_text("}{ not json", encoding="utf-8")
    out = get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("b", "b")], now=1.0)
    assert out == [("b", "b")]


def test_cache_dir_created_lazily() -> None:
    assert not cache_dir().exists()
    get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("a", "a")], now=0.0)
    assert cache_dir().exists()


def test_write_failure_is_failsoft(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("vsc.gen.complete_cache.os.replace", boom)
    out = get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("a", "n")], now=0.0)
    assert out == [("a", "n")]  # fetched value still returned despite write failure


def test_items_round_trip_as_tuples() -> None:
    get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("vm-1", "web")], now=0.0)
    out = get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("zzz", "zzz")], now=1.0)
    assert out == [("vm-1", "web")]
    assert all(isinstance(item, tuple) and len(item) == 2 for item in out)


def test_malformed_entries_in_payload_are_dropped() -> None:
    get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("a", "n")], now=0.0)
    path = next(iter(cache_dir().glob("*.json")))
    path.write_text(
        json.dumps({"ts": 0.0, "items": [["ok", "name"], "bad", ["x"], [1, 2, 3]]}),
        encoding="utf-8",
    )
    out = get_or_fetch("k", ttl=60.0, fetch_fn=lambda: [("z", "z")], now=1.0)
    assert out == [("ok", "name")]


def test_cache_ttl_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cache_ttl() == 60.0
    monkeypatch.setenv("VSC_COMPLETE_TTL", "5")
    assert cache_ttl() == 5.0
    monkeypatch.setenv("VSC_COMPLETE_TTL", "not-a-number")
    assert cache_ttl() == 60.0  # invalid -> default, never raises


def test_cache_dir_under_override() -> None:
    assert cache_dir().parent == Path(__import__("os").environ["VSC_CACHE_DIR"])
    assert cache_dir().name == "completion"
