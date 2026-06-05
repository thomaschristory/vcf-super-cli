"""Output rendering tests."""

from __future__ import annotations

import json
from decimal import Decimal

import com.vmware.vapi.std.errors_client as verr
from com.vmware.vapi.std_client import LocalizableMessage
from rich.console import Console

from vsc.output.render import emit, emit_request, jsonable, to_json, to_table, write_envelope


def _sample_struct() -> object:
    lm = LocalizableMessage(id="x.y", default_message="boom", args=[])
    return verr.NotFound(messages=[lm], data=None)


def test_jsonable_converts_vapistruct() -> None:
    out = jsonable(_sample_struct())
    assert isinstance(out, dict)
    assert out["error_type"] == "NOT_FOUND"
    assert out["messages"][0]["default_message"] == "boom"


def test_to_json_is_valid_and_handles_decimal() -> None:
    text = to_json({"ratio": Decimal("1.5"), "items": [1, 2]})
    parsed = json.loads(text)
    assert parsed["items"] == [1, 2]
    assert parsed["ratio"] == "1.5"  # Decimal serialized via default=str


def test_to_table_with_rows() -> None:
    console = Console(record=True, width=120)
    assert to_table([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], console) is True
    assert "a" in console.export_text()


def test_to_table_rejects_non_tabular() -> None:
    console = Console(record=True)
    assert to_table(42, console) is False


def test_emit_table_falls_back_to_json(capsys) -> None:
    emit(42, "table")
    out = capsys.readouterr().out
    assert json.loads(out) == 42


def test_write_envelope_dry_run_shape() -> None:
    plan = {"method": "DELETE", "url": "/x/1"}
    env = write_envelope(plan, applied=False)
    assert env == {
        "applied": False,
        "request": plan,
        "apply_hint": "re-run with --apply to execute",
    }
    assert "result" not in env


def test_write_envelope_applied_includes_result() -> None:
    plan = {"method": "POST", "url": "/x"}
    env = write_envelope(plan, applied=True, result={"id": "vm-1"})
    assert env["applied"] is True
    assert env["result"] == {"id": "vm-1"}
    assert "apply_hint" not in env


def test_emit_request_table_applied_no_body_does_not_dump_json(capsys) -> None:
    emit_request({"method": "DELETE", "url": "/x/1"}, applied=True, result=None, fmt="table")
    out = capsys.readouterr().out
    assert "APPLIED" in out and "DELETE" in out
    assert "(no body)" in out
    assert "applied" not in out  # the JSON envelope key must not leak into table mode


def test_emit_request_json_applied_emits_envelope(capsys) -> None:
    emit_request({"method": "POST", "url": "/x"}, applied=True, result={"id": "1"}, fmt="json")
    env = json.loads(capsys.readouterr().out)
    assert env["applied"] is True and env["result"] == {"id": "1"}
