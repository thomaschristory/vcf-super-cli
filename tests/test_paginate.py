"""Cursor-following pagination helper (pure, no SDK)."""

from __future__ import annotations

from vsc.gen.paginate import follow_cursor


def _pager(pages: list[tuple[list[int], str | None]]):
    """Return a fetch_page(cursor) backed by a fixed list of (results, next_cursor).

    The cursor that yields page *i* is the next_cursor of page *i-1* (None first).
    """
    by_cursor: dict[str | None, tuple[list[int], str | None]] = {}
    cursor: str | None = None
    for results, next_cursor in pages:
        by_cursor[cursor] = (results, next_cursor)
        cursor = next_cursor
    calls: list[str | None] = []

    def fetch_page(cursor: str | None) -> tuple[list[int], str | None]:
        calls.append(cursor)
        return by_cursor[cursor]

    fetch_page.calls = calls  # type: ignore[attr-defined]
    return fetch_page


def test_follows_cursor_across_pages_and_concatenates() -> None:
    pages = [([1, 2], "c1"), ([3, 4], "c2"), ([5], None)]
    assert follow_cursor(_pager(pages)) == [1, 2, 3, 4, 5]


def test_single_page_terminates_on_empty_cursor() -> None:
    assert follow_cursor(_pager([([1, 2, 3], None)])) == [1, 2, 3]


def test_respects_max_items_and_stops_early() -> None:
    pages = [([1, 2], "c1"), ([3, 4], "c2"), ([5, 6], None)]
    fetch = _pager(pages)
    assert follow_cursor(fetch, max_items=3) == [1, 2, 3]
    # Stops fetching once the cap is reached — third page never requested.
    assert fetch.calls == [None, "c1"]  # type: ignore[attr-defined]


def test_terminates_on_repeated_cursor() -> None:
    # A misbehaving API that keeps returning the same cursor must not loop forever.
    def fetch_page(cursor: str | None) -> tuple[list[int], str | None]:
        return ([1], "stuck")

    assert follow_cursor(fetch_page) == [1, 1]  # first page + one repeat, then stop


def test_empty_first_page() -> None:
    assert follow_cursor(_pager([([], None)])) == []
