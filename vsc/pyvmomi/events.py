"""``vsc vsphere events list`` — recent events via the pyVmomi EventManager.

vAPI/REST has no event query surface, so this reads over SOAP. ``--since`` accepts
a duration (``30s``/``15m``/``2h``/``1d``); ``--vm``/``--host`` scope to one entity.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import typer
from pyVmomi import vim

from vsc.connect.vmomi import vmomi_jsonable
from vsc.gen.complete import output_format_completer
from vsc.output.render import OutputFormat
from vsc.pyvmomi.runner import run_read

events_app = typer.Typer(no_args_is_help=True, help="Recent events (pyVmomi fallback).")

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_since(text: str) -> int:
    """Parse a duration like ``30s``/``15m``/``2h``/``1d`` into seconds."""
    unit = text[-1:]
    if unit not in _UNIT_SECONDS or not text[:-1].isdigit():
        raise ValueError(f"invalid duration {text!r} (use e.g. 30s, 15m, 2h, 1d)")
    return int(text[:-1]) * _UNIT_SECONDS[unit]


def query_events(
    event_manager: Any,
    *,
    entity: Any = None,
    recursion: str = "self",
    since: int | None = None,
    current_time: _dt.datetime | None = None,
    max_count: int | None = None,
) -> list[dict[str, Any]]:
    """Query events matching the optional entity/time filters, shaped as dicts."""
    spec = vim.event.EventFilterSpec()
    if entity is not None:
        spec.entity = vim.event.EventFilterSpec.ByEntity(entity=entity, recursion=recursion)
    if since is not None:
        now = current_time or _dt.datetime.now(_dt.UTC)
        spec.time = vim.event.EventFilterSpec.ByTime(beginTime=now - _dt.timedelta(seconds=since))
    if max_count is not None:
        spec.maxCount = max_count
    events = event_manager.QueryEvents(filter=spec) or []
    if max_count is not None:
        events = events[:max_count]
    return [vmomi_jsonable(event) for event in events]


@events_app.command("list")
def events_list(
    vm: str | None = typer.Option(None, "--vm", help="Scope to a VM moid, e.g. vm-101."),
    host: str | None = typer.Option(None, "--host", help="Scope to a host moid, e.g. host-12."),
    since: str | None = typer.Option(None, "--since", help="Only events newer than, e.g. 1h."),
    max_count: int = typer.Option(100, "--max-count", help="Cap the number of events returned."),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """List recent events, optionally scoped to one VM or host."""
    if vm and host:
        raise typer.BadParameter("pass at most one of --vm / --host")
    try:
        since_seconds = parse_since(since) if since else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    def build(si: Any) -> list[dict[str, Any]]:
        entity = None
        if vm:
            entity = vim.VirtualMachine(vm, si._stub)
        elif host:
            entity = vim.HostSystem(host, si._stub)
        return query_events(
            si.content.eventManager,
            entity=entity,
            since=since_seconds,
            current_time=si.CurrentTime(),
            max_count=max_count,
        )

    run_read(output.value, build)
