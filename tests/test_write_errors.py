"""Write-path error mapping: CONFLICT / UNAVAILABLE families resolve to the
documented exit codes when a write is applied. The error envelope + exit-code
map already exist (vsc/output/errors.py); these tests exercise them through the
generated write command's --apply path against real vAPI error types.
"""

from __future__ import annotations

import dataclasses
import json

import com.vmware.vapi.std.errors_client as verr
import pytest
import typer
from com.vmware.vapi.std_client import LocalizableMessage
from typer.testing import CliRunner

from vsc.gen.builder import make_command
from vsc.gen.discover import discover_operations, vsphere_services
from vsc.gen.model import Operation
from vsc.output.errors import ERROR_TYPE_TO_EXIT
from vsc.output.exit_codes import ExitCode

runner = CliRunner()


def _error_classes_by_type() -> dict[str, type]:
    """Reverse-index every instantiable vAPI ``Error`` subclass by its error_type."""
    lm = [LocalizableMessage(id="x", default_message="b", args=[])]
    index: dict[str, type] = {}
    for obj in vars(verr).values():
        if not (isinstance(obj, type) and issubclass(obj, verr.Error) and obj is not verr.Error):
            continue
        try:
            error_type = obj(messages=lm, data=None).error_type
        except Exception:  # skip classes with a non-standard constructor
            continue
        index[error_type] = obj
    return index


_BY_TYPE = _error_classes_by_type()

# Derive the matrix straight from the production map so it can never drift: every
# error_type that maps to CONFLICT/UNAVAILABLE must be exercised through the write
# path. New mappings are picked up automatically.
_WRITE_ERROR_CASES = sorted(
    (error_type, code)
    for error_type, code in ERROR_TYPE_TO_EXIT.items()
    if code in (ExitCode.CONFLICT, ExitCode.UNAVAILABLE)
)


def _vm_delete() -> Operation:
    ops = discover_operations(vsphere_services()[0], "vsphere", read_only=False)
    return next(o for o in ops if o.cli_verb == "delete")


def _app_raising(error_cls: type) -> typer.Typer:
    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def delete(self, **_kwargs: object) -> None:
            lm = LocalizableMessage(id="x", default_message="boom", args=[])
            raise error_cls(messages=[lm], data=None)

    op = dataclasses.replace(_vm_delete(), service_cls=FakeVM)
    app = typer.Typer()
    app.command("delete")(make_command(op, lambda _b: object()))
    return app


def test_conflict_and_unavailable_maps_are_non_empty() -> None:
    # Guard against the matrix silently becoming empty (e.g. a refactor of the map).
    codes = {code for _t, code in _WRITE_ERROR_CASES}
    assert codes == {ExitCode.CONFLICT, ExitCode.UNAVAILABLE}


@pytest.mark.parametrize(("error_type", "expected"), _WRITE_ERROR_CASES)
def test_write_error_maps_to_exit_code(error_type: str, expected: ExitCode) -> None:
    error_cls = _BY_TYPE.get(error_type)
    assert error_cls is not None, f"no vAPI Error class found for {error_type}"
    app = _app_raising(error_cls)
    result = runner.invoke(app, ["vm-1", "--apply"])
    assert result.exit_code == int(expected), result.stderr
    env = json.loads(result.stderr)["error"]
    assert env["code"] == int(expected)
    assert env["kind"] == error_type  # stable error_type surfaced as the envelope kind


def test_dry_run_never_reaches_write_error() -> None:
    # Without --apply the SDK method is never called, so a server-side conflict
    # cannot occur — the command previews and exits 0.
    app = _app_raising(verr.AlreadyExists)
    result = runner.invoke(app, ["vm-1"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["applied"] is False
