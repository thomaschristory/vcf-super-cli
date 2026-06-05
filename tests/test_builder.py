"""Generated-command invoke pipeline tests (offline, mocked connections)."""

from __future__ import annotations

import dataclasses
import json

import com.vmware.vapi.std.errors_client as verr
import pytest
import requests
import typer
from com.vmware.vapi.std_client import LocalizableMessage
from typer.testing import CliRunner

from vsc.gen.builder import _collect_kwargs, make_command
from vsc.gen.discover import discover_operations, vsphere_services
from vsc.gen.model import Param, ParamKind
from vsc.output.exit_codes import ExitCode

runner = CliRunner()
_CAPTURED: dict[str, object] = {}


def _vm_op(verb: str) -> object:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    return next(o for o in ops if o.cli_verb == verb)


def _app_for(op: object, service_cls: type) -> typer.Typer:
    op2 = dataclasses.replace(op, service_cls=service_cls)  # type: ignore[type-var]
    app = typer.Typer()
    app.command(op2.cli_verb)(make_command(op2, lambda _backend: object()))
    return app


def test_get_success_coerces_and_invokes() -> None:
    _CAPTURED.clear()

    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def get(self, **kwargs: object) -> dict[str, object]:
            _CAPTURED.update(kwargs)
            return {"name": "web", "power_state": "POWERED_ON"}

    app = _app_for(_vm_op("get"), FakeVM)
    result = runner.invoke(app, ["vm-123"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"name": "web", "power_state": "POWERED_ON"}
    assert _CAPTURED == {"vm": "vm-123"}


def test_not_found_maps_to_exit_code_and_envelope() -> None:
    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def get(self, **_kwargs: object) -> dict[str, object]:
            lm = LocalizableMessage(id="x", default_message="no such vm", args=[])
            raise verr.NotFound(messages=[lm], data=None)

    app = _app_for(_vm_op("get"), FakeVM)
    result = runner.invoke(app, ["vm-404"])
    assert result.exit_code == int(ExitCode.NOT_FOUND)
    assert json.loads(result.stderr)["error"]["kind"] == "NOT_FOUND"


def test_connection_error_maps_to_connection_exit() -> None:
    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def get(self, **_kwargs: object) -> dict[str, object]:
            raise requests.exceptions.ConnectionError("vcenter down")

    app = _app_for(_vm_op("get"), FakeVM)
    result = runner.invoke(app, ["vm-1"])
    assert result.exit_code == int(ExitCode.CONNECTION)
    assert json.loads(result.stderr)["error"]["code"] == int(ExitCode.CONNECTION)


def test_bad_json_filter_yields_usage_envelope() -> None:
    app = _app_for(_vm_op("list"), object)
    result = runner.invoke(app, ["--filter", "{not json"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert json.loads(result.stderr)["error"]["kind"] == "InvalidArgument"


def test_unknown_filter_field_yields_usage_envelope() -> None:
    app = _app_for(_vm_op("list"), object)
    result = runner.invoke(app, ["--filter", '{"bogus_field": 1}'])
    assert result.exit_code == int(ExitCode.USAGE)
    assert json.loads(result.stderr)["error"]["kind"] == "InvalidArgument"


def test_invalid_output_format_rejected() -> None:
    app = _app_for(_vm_op("get"), object)
    result = runner.invoke(app, ["vm-1", "-o", "yaml"])
    assert result.exit_code == 2  # Click rejects the closed OutputFormat choice


def test_collect_kwargs_enum_validation() -> None:
    spec = [
        (Param(name="state", kind=ParamKind.ENUM, required=False, enum_values=["A", "B"]), "state")
    ]
    assert _collect_kwargs(spec, {"state": "A"}) == {"state": "A"}
    with pytest.raises(ValueError):
        _collect_kwargs(spec, {"state": "C"})
