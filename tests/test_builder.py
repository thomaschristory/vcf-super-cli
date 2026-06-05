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

from vsc.gen.builder import _collect_kwargs, build_group, make_command
from vsc.gen.discover import discover_operations, vsphere_services
from vsc.gen.model import Operation, Param, ParamKind
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


# --------------------------------------------------------------------------- #
# v0.2: write commands — dry-run gate + --apply
# --------------------------------------------------------------------------- #


def _write_app(op: object, service_cls: type, connect_fn: object) -> typer.Typer:
    op2 = dataclasses.replace(op, service_cls=service_cls)  # type: ignore[type-var]
    app = typer.Typer()
    app.command(op2.cli_verb)(make_command(op2, connect_fn))  # type: ignore[arg-type]
    return app


def test_write_dry_run_by_default_emits_plan_and_never_connects() -> None:
    calls: list[str] = []

    def connect(backend: str) -> object:
        calls.append(backend)
        return object()

    app = _write_app(_vm_op("delete"), object, connect)
    result = runner.invoke(app, ["vm-1"])  # no --apply
    assert result.exit_code == 0, result.stdout
    env = json.loads(result.stdout)
    assert env["applied"] is False
    assert env["request"]["method"] == "DELETE"
    assert env["request"]["url"] == "/vcenter/vm/vm-1"
    assert "apply_hint" in env and "result" not in env
    assert calls == []  # invariant: dry-run opens no connection


def test_write_apply_connects_invokes_and_emits_applied_envelope() -> None:
    _CAPTURED.clear()
    calls: list[str] = []

    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def delete(self, **kwargs: object) -> None:
            _CAPTURED.update(kwargs)

    def connect(backend: str) -> object:
        calls.append(backend)
        return object()

    app = _write_app(_vm_op("delete"), FakeVM, connect)
    result = runner.invoke(app, ["vm-1", "--apply"])
    assert result.exit_code == 0, result.stdout
    env = json.loads(result.stdout)
    assert env["applied"] is True
    assert env["request"]["method"] == "DELETE"
    assert "result" in env
    assert _CAPTURED == {"vm": "vm-1"}  # routed to the SDK method with coerced kwargs
    assert calls == ["vsphere"]


def test_write_apply_maps_conflict_error() -> None:
    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def delete(self, **_kwargs: object) -> None:
            lm = LocalizableMessage(id="x", default_message="in use", args=[])
            raise verr.AlreadyExists(messages=[lm], data=None)

    app = _write_app(_vm_op("delete"), FakeVM, lambda _b: object())
    result = runner.invoke(app, ["vm-1", "--apply"])
    assert result.exit_code == int(ExitCode.CONFLICT)
    assert json.loads(result.stderr)["error"]["kind"] == "ALREADY_EXISTS"


def test_read_command_has_no_apply_flag() -> None:
    app = _app_for(_vm_op("get"), object)
    result = runner.invoke(app, ["vm-1", "--apply"])
    assert result.exit_code == 2  # unknown option on a read command


def _synthetic_put(op_id: str, verb: str) -> Operation:
    return Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.vmware.vcenter.thing",
        op_id=op_id,
        method_name=op_id,
        cli_verb=verb,
        http_method="PUT",
        url_template="/vcenter/thing/{id}",
        path_vars=[],
        path_var_map={},
        params=[],
    )


def test_build_group_disambiguates_colliding_verbs() -> None:
    ops = [_synthetic_put("alpha_set", "set"), _synthetic_put("beta_set", "set")]
    root = build_group(ops, lambda _b: object())
    group = next(g for g in root.registered_groups if g.name == "thing")
    names = {c.name for c in group.typer_instance.registered_commands}
    assert "set" in names  # first keeps the clean verb
    assert "beta-set" in names  # second falls back to its op id, no overwrite
    assert len(names) == 2
