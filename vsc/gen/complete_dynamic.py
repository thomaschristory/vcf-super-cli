"""Live (network-backed) resource-id completer for ``ID``-kind args/options.

This is the dynamic tier layered on top of the static/offline completers in
:mod:`vsc.gen.complete`. On ``<TAB>`` for an id argument it suggests *real* ids
pulled from the live inventory, with the resource's name shown as help.

Three hard rules keep it safe:

* **Opt-in.** Inactive unless ``VSC_COMPLETE_DYNAMIC`` is truthy; otherwise it
  returns ``[]`` — exactly v0.3's behaviour, so ``<TAB>`` never touches the API
  by default.
* **Time-bounded.** The fetch runs in a daemon thread joined with a short hard
  timeout (``VSC_COMPLETE_TIMEOUT``, default 2s); an overrun yields ``[]`` and
  the abandoned thread cannot block process exit.
* **Fail-soft.** Any error — no auth, no config, transport failure, timeout —
  yields ``[]``. ``<TAB>`` must never hang or traceback. Failed/timed-out
  fetches are *not* cached, so a later authenticated press still works.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

from vsc.connect.targets import active_profile_name, connect_for_backend
from vsc.gen.complete_cache import CompletionItems, cache_ttl, get_or_fetch
from vsc.gen.resources import ResourceSource, resource_source

DynamicCompleter = Callable[[str], list[tuple[str, str]]]

_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_TIMEOUT = 2.0


class _FetchFailed(Exception):
    """Internal marker: a live fetch failed or timed out (so: do not cache)."""


def _dynamic_enabled() -> bool:
    return os.environ.get("VSC_COMPLETE_DYNAMIC", "").strip().lower() in _TRUTHY


def _timeout() -> float:
    raw = os.environ.get("VSC_COMPLETE_TIMEOUT")
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT


def _run_with_timeout(fn: Callable[[], CompletionItems], timeout: float) -> CompletionItems | None:
    """Run ``fn`` in a daemon thread; return its result, or ``None`` on overrun/error."""
    result: list[CompletionItems] = []
    errors: list[BaseException] = []

    def target() -> None:
        # Completion must swallow everything the fetch can throw.
        try:
            result.append(fn())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or errors or not result:
        return None
    return result[0]


def _extract(result: object, src: ResourceSource) -> CompletionItems:
    """Pull ``(id, name)`` pairs out of a list op's result."""
    # NSX-style cursor results wrap the rows in ``.results``; plain vSphere lists
    # are already the row sequence.
    rows: Any = getattr(result, "results", None)
    if rows is None:
        rows = result
    items: CompletionItems = []
    try:
        iterator = iter(rows)
    except TypeError:
        return items
    for row in iterator:
        ident = getattr(row, src.id_field, None)
        if ident is None:
            continue
        label = ""
        if src.name_field:
            name = getattr(row, src.name_field, None)
            if name is not None:
                label = str(name)
        items.append((str(ident), label))
    return items


def _fetch_ids(src: ResourceSource) -> CompletionItems:
    """Open a connection for the source backend and run its list op."""
    cfg = connect_for_backend(src.backend)
    service = src.list_op.service_cls(cfg)
    method = getattr(service, src.list_op.method_name, None)
    result = method() if callable(method) else service._invoke(src.list_op.op_id, {})
    return _extract(result, src)


def _safe_profile() -> str | None:
    try:
        return active_profile_name()
    except Exception:
        return None


def _cached_fetch(resource_type: str) -> CompletionItems:
    src = resource_source(resource_type)
    if src is None:
        return []
    key = f"{_safe_profile()}\x00{src.backend}\x00{resource_type}"

    def fetch() -> CompletionItems:
        got = _run_with_timeout(lambda: _fetch_ids(src), _timeout())
        if got is None:
            # Don't cache a failure/timeout — raise so get_or_fetch stores nothing.
            raise _FetchFailed
        return got

    return get_or_fetch(key, cache_ttl(), fetch)


def resource_completer(resource_type: str | None) -> DynamicCompleter:
    """A completer suggesting live ids for ``resource_type`` (opt-in, fail-soft)."""

    def complete(incomplete: str) -> list[tuple[str, str]]:
        if not _dynamic_enabled() or not resource_type:
            return []
        try:
            items = _cached_fetch(resource_type)
        except Exception:
            return []
        prefix = incomplete or ""
        return [(ident, label) for ident, label in items if ident.startswith(prefix)]

    return complete
