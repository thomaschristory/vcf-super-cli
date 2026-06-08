"""A tiny on-disk TTL cache for live shell-completion candidates.

Repeated ``<TAB>`` presses must not re-hit the API, and a stale-but-recent answer
is fine for completion. This stores each ``(profile, backend, resource-type)``
result as a small JSON file under the platform cache dir with a timestamp; reads
within the TTL skip the fetch.

**Fail-soft by contract.** A missing, expired, corrupt or unwritable cache is a
miss — never an exception. Writes are best-effort. Completion must never error
or hang because of the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import platformdirs

# (id, label) pairs — label is the human name shown as completion help.
CompletionItems = list[tuple[str, str]]

_DEFAULT_TTL = 60.0
_PAIR_LEN = 2  # each cached item is an (id, label) pair


def _base_cache_dir() -> Path:
    """Base cache directory (``VSC_CACHE_DIR`` overrides the platform default)."""
    override = os.environ.get("VSC_CACHE_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_cache_dir("vcf-super-cli", appauthor=False))


def cache_dir() -> Path:
    """Directory holding the completion cache files."""
    return _base_cache_dir() / "completion"


def cache_ttl() -> float:
    """Cache TTL in seconds (``VSC_COMPLETE_TTL`` overrides; default 60s).

    A malformed override falls back to the default rather than raising.
    """
    raw = os.environ.get("VSC_COMPLETE_TTL")
    if raw is None:
        return _DEFAULT_TTL
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TTL


def _path_for(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return cache_dir() / f"{digest}.json"


def _coerce_items(raw: object) -> CompletionItems:
    """Normalise a decoded ``items`` payload into ``(str, str)`` pairs.

    Malformed entries are dropped (never raise) so a partially-corrupt file still
    yields whatever is usable.
    """
    if not isinstance(raw, list):
        return []
    items: CompletionItems = []
    for entry in raw:
        if isinstance(entry, (list, tuple)) and len(entry) == _PAIR_LEN:
            ident, label = entry
            items.append((str(ident), str(label)))
    return items


def _read(key: str, ttl: float, now: float) -> CompletionItems | None:
    """Return cached items if present and fresh, else ``None`` (never raises)."""
    try:
        with _path_for(key).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        ts = float(payload["ts"])
        if now - ts >= ttl:
            return None
        return _coerce_items(payload.get("items"))
    except Exception:
        return None


def _write(key: str, items: CompletionItems, now: float) -> None:
    """Best-effort atomic write of the cache entry; failures are swallowed."""
    try:
        directory = cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = _path_for(key)
        payload = {"ts": now, "items": [[i, label] for i, label in items]}
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except Exception:
        # A cache we can't write is simply not cached — never fatal at <TAB>.
        return


def get_or_fetch(
    key: str,
    ttl: float,
    fetch_fn: Callable[[], CompletionItems],
    *,
    now: float | None = None,
) -> CompletionItems:
    """Return cached items for ``key`` if fresh, else call ``fetch_fn`` and store.

    ``now`` is injectable for tests; it defaults to the wall clock.
    """
    moment = time.time() if now is None else now
    cached = _read(key, ttl, moment)
    if cached is not None:
        return cached
    items = fetch_fn()
    _write(key, items, moment)
    return items
