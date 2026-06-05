"""Cursor-following pagination for list operations.

NSX Policy list operations return an opaque ``cursor`` with each page; passing it
back fetches the next page. This helper drives that loop given a ``fetch_page``
callable, so the SDK-specific details (which kwarg carries the cursor, where the
results live on the response) stay in the command layer and the loop itself is
pure and unit-testable.

vSphere REST list operations do not paginate; they are handled by a simple
client-side cap in the command layer, not here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# fetch_page(cursor) -> (results_for_this_page, next_cursor_or_None)
FetchPage = Callable[[Any], "tuple[list[Any], str | None]"]


def follow_cursor(fetch_page: FetchPage, *, max_items: int | None = None) -> list[Any]:
    """Fetch and concatenate every page, following the returned cursor.

    Starts from ``cursor=None`` (the first page). Stops when the response carries
    no next cursor, when a cursor repeats (a misbehaving server guard), or once
    ``max_items`` results have been collected.
    """
    collected: list[Any] = []
    seen: set[str] = set()
    cursor: str | None = None
    while True:
        results, next_cursor = fetch_page(cursor)
        collected.extend(results)
        if max_items is not None and len(collected) >= max_items:
            return collected[:max_items]
        if not next_cursor or next_cursor in seen:
            return collected
        seen.add(next_cursor)
        cursor = next_cursor
