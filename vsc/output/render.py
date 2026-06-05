"""Render SDK results to JSON (default) or a Rich table.

vAPI results are ``VapiStruct`` instances (or lists/maps of them). ``to_dict()``
parses floats as ``Decimal``, so JSON serialization uses ``default=str``. Dict
keys are wire/canonical names (e.g. ``memory_size_MiB``), not the snake_case
constructor kwargs — we surface them as-is.
"""

from __future__ import annotations

import enum
import json
from typing import Any

from rich.console import Console
from rich.table import Table
from vmware.vapi.bindings.struct import VapiStruct


class OutputFormat(str, enum.Enum):
    """Supported ``--output`` formats."""

    json = "json"
    table = "table"


def jsonable(value: Any) -> Any:
    """Convert a vAPI result into a JSON-serializable structure."""
    if isinstance(value, VapiStruct):
        return {k: jsonable(v) for k, v in value.to_dict().items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return value


def to_json(value: Any) -> str:
    """Serialize a result to indented JSON text."""
    return json.dumps(jsonable(value), indent=2, default=str, sort_keys=False)


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def to_table(value: Any, console: Console) -> bool:
    """Render ``value`` as a Rich table. Returns ``False`` if it isn't tabular."""
    data = jsonable(value)
    rows = _rows(data)
    if not rows:
        return False
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = Table(show_header=True, header_style="bold")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[_cell(row.get(col)) for col in columns])
    console.print(table)
    return True


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def emit(value: Any, fmt: str | OutputFormat = "json", *, console: Console | None = None) -> None:
    """Print a result in the requested format (``json`` or ``table``)."""
    fmt = fmt.value if isinstance(fmt, OutputFormat) else fmt
    if fmt == "table":
        console = console or Console()
        if to_table(value, console):
            return
        # Fall back to JSON for non-tabular payloads (e.g. a single scalar).
    print(to_json(value))


_APPLY_HINT = "re-run with --apply to execute"


def write_envelope(plan: dict[str, Any], *, applied: bool, result: Any = None) -> dict[str, Any]:
    """Build the stable write envelope shared by dry-run and apply.

    Dry-run (``applied=False``) carries the plan and an apply hint and never a
    result; apply (``applied=True``) carries the plan and the SDK response.
    """
    env: dict[str, Any] = {"applied": applied, "request": plan}
    if applied:
        env["result"] = jsonable(result)
    else:
        env["apply_hint"] = _APPLY_HINT
    return env


def emit_request(
    plan: dict[str, Any],
    *,
    applied: bool,
    result: Any = None,
    fmt: str | OutputFormat = "json",
    console: Console | None = None,
) -> None:
    """Print the write envelope (dry-run preview or applied result)."""
    fmt = fmt.value if isinstance(fmt, OutputFormat) else fmt
    env = write_envelope(plan, applied=applied, result=result)
    if fmt == "table":
        console = console or Console()
        status = "APPLIED" if applied else "DRY-RUN"
        console.print(f"[bold]{status}[/bold] {plan['method']} {plan['url']}")
        if not applied:
            console.print(f"({_APPLY_HINT})")
            return
        # Applied: show the result as a table, or a clean scalar/empty line — never
        # fall through to dumping the whole JSON envelope in table mode.
        if result is None:
            console.print("(no body)")
        elif not to_table(result, console):
            console.print(to_json(result))
        return
    print(to_json(env))
