"""`vsc vsphere events list` (pyVmomi EventManager) — helpers, CLI, filters."""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import pytest
import typer
from pyVmomi import vim
from typer.testing import CliRunner

from vsc.pyvmomi.events import events_app, parse_since, query_events

runner = CliRunner()


def _event(key: int, message: str) -> vim.event.Event:
    return vim.event.Event(
        key=key,
        chainId=key,
        createdTime=_dt.datetime(2026, 6, 5, 12, 0, tzinfo=_dt.UTC),
        userName="root",
        fullFormattedMessage=message,
    )


class _FakeEM:
    def __init__(self, events: list[Any]) -> None:
        self.events = events
        self.captured: Any = None

    def QueryEvents(self, filter: Any) -> list[Any]:
        self.captured = filter
        return self.events


def _fake_si(em: _FakeEM, current: _dt.datetime | None = None) -> Any:
    content = type("C", (), {"eventManager": em})()
    return type(
        "SI",
        (),
        {"content": content, "_stub": object(), "CurrentTime": lambda self: current},
    )()


# --------------------------------------------------------------------------- #
# parse_since
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("30s", 30), ("15m", 900), ("2h", 7200), ("1d", 86400)],
)
def test_parse_since_units(text: str, seconds: int) -> None:
    assert parse_since(text) == seconds


def test_parse_since_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="duration"):
        parse_since("soon")


# --------------------------------------------------------------------------- #
# query_events
# --------------------------------------------------------------------------- #


def test_query_events_shapes_and_caps() -> None:
    em = _FakeEM([_event(1, "a"), _event(2, "b"), _event(3, "c")])
    out = query_events(em, max_count=2)
    assert [e["fullFormattedMessage"] for e in out] == ["a", "b"]
    assert em.captured.maxCount == 2


def test_query_events_builds_entity_and_time_filter() -> None:
    em = _FakeEM([])
    now = _dt.datetime(2026, 6, 5, 12, 0, tzinfo=_dt.UTC)
    query_events(em, entity=vim.VirtualMachine("vm-1", None), since=3600, current_time=now)
    assert em.captured.entity.entity._moId == "vm-1"
    assert em.captured.time.beginTime == now - _dt.timedelta(seconds=3600)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(events_app, name="events")
    return app


def test_events_list_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    em = _FakeEM([_event(1, "VM powered on")])
    now = _dt.datetime(2026, 6, 5, 12, 0, tzinfo=_dt.UTC)
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(em, now))
    result = runner.invoke(_app(), ["events", "list", "--vm", "vm-1", "--since", "1h"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["fullFormattedMessage"] == "VM powered on"
    assert em.captured.entity.entity._moId == "vm-1"


def test_events_list_rejects_two_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    em = _FakeEM([])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(em))
    result = runner.invoke(_app(), ["events", "list", "--vm", "vm-1", "--host", "host-2"])
    assert result.exit_code == 2  # only one entity filter allowed


def test_events_list_bad_since_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    em = _FakeEM([])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(em))
    result = runner.invoke(_app(), ["events", "list", "--since", "soon"])
    assert result.exit_code == 2
