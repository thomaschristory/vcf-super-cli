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

from vsc.gen.builder import _build_signature, _collect_kwargs, build_group, make_command
from vsc.gen.discover import discover_operations, nsx_services, vsphere_services
from vsc.gen.model import Operation, Param, ParamKind
from vsc.output.exit_codes import ExitCode

runner = CliRunner()
_CAPTURED: dict[str, object] = {}


def _vm_op(verb: str) -> object:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    return next(o for o in ops if o.cli_verb == verb)


def _write(service_name: str, verb: str, backend: str) -> Operation:
    services = vsphere_services() if backend == "vsphere" else nsx_services()
    cls = next(c for c in services if c.__name__ == service_name)
    return next(o for o in discover_operations(cls, backend, read_only=False) if o.cli_verb == verb)


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


def test_dry_run_incomplete_body_is_clean_usage_error() -> None:
    # A struct body missing required fields must surface as the structured usage
    # envelope (exit 2) without opening a connection — not a vAPI traceback.
    calls: list[str] = []

    def connect(backend: str) -> object:
        calls.append(backend)
        return object()

    app = _write_app(_vm_op("create"), object, connect)
    result = runner.invoke(app, ["--spec", '{"name": "x"}'])  # missing guest_OS, no --apply
    assert result.exit_code == int(ExitCode.USAGE), result.stdout
    assert json.loads(result.stderr)["error"]["kind"] == "InvalidArgument"
    assert calls == []  # never connected


def test_write_apply_routes_named_body_op() -> None:
    _CAPTURED.clear()

    class FakeSeg:
        def __init__(self, _cfg: object) -> None:
            pass

        def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
            def method(**kwargs: object) -> dict[str, str]:
                _CAPTURED.update(kwargs)
                return {"id": "web"}

            return method

    op = _write("Segments", "set", "nsx")
    app = _write_app(op, FakeSeg, lambda _b: object())
    result = runner.invoke(app, ["web", "--segment", '{"display_name": "x"}', "--apply"])
    assert result.exit_code == 0, result.stdout
    env = json.loads(result.stdout)
    assert env["applied"] is True
    assert env["request"]["body"] == {"display_name": "x"}
    assert _CAPTURED["segment_id"] == "web"
    assert "segment" in _CAPTURED  # body struct routed to the SDK method


def test_traceflows_set_dry_run_emits_put_body_and_never_connects() -> None:
    # #58: the new NSX Traceflow write surface must inherit the dry-run gate —
    # preview a PUT with the traceflow-config body, opening no connection.
    calls: list[str] = []

    def connect(backend: str) -> object:
        calls.append(backend)
        return object()

    op = _write("Traceflows", "set", "nsx")
    app = _write_app(op, object, connect)
    result = runner.invoke(app, ["tf-1", "--traceflow-config", '{"display_name": "tf-web"}'])
    assert result.exit_code == 0, result.stdout
    env = json.loads(result.stdout)
    assert env["applied"] is False
    assert env["request"]["method"] == "PUT"
    assert env["request"]["body"] == {"display_name": "tf-web"}
    assert calls == []  # invariant: dry-run opens no connection


def test_traceflows_restart_dry_run_gate_never_connects() -> None:
    # #58: the restart action (POST, no ?action=) is a write and must inherit the
    # dry-run gate — preview and open no connection without --apply.
    calls: list[str] = []

    def connect(backend: str) -> object:
        calls.append(backend)
        return object()

    op = _write("Traceflows", "policy-lm-restart-traceflow", "nsx")
    app = _write_app(op, object, connect)
    result = runner.invoke(app, ["tf-1"])  # no --apply
    assert result.exit_code == 0, result.stdout
    env = json.loads(result.stdout)
    assert env["applied"] is False
    assert env["request"]["method"] == "POST"
    assert calls == []  # invariant: dry-run opens no connection


def test_observations_list_all_on_non_cursor_op_does_not_crash() -> None:
    # #58: observations list returns a cursor-shaped result but the op takes NO
    # cursor input param. --all must not re-invoke with a cursor kwarg (which the
    # SDK method rejects) — it degrades to a safe single-page no-op, like vSphere.
    invocations: list[dict[str, object]] = []

    class Res:
        def __init__(self, cursor: str | None) -> None:
            self.results = [{"hop": 1}]
            self.cursor = cursor

    class FakeObs:
        def __init__(self, _cfg: object) -> None:
            pass

        def policy_lm_list_traceflow_observations(self, **kwargs: object) -> Res:
            invocations.append(kwargs)
            if "cursor" in kwargs:
                raise TypeError("unexpected keyword argument 'cursor'")
            return Res("PAGE2")  # server hands back a cursor

    obs = next(c for c in nsx_services() if c.__name__ == "Observations")
    op = next(o for o in discover_operations(obs, "nsx") if o.cli_verb == "list")
    app = _app_for(op, FakeObs)
    result = runner.invoke(app, ["tf-1", "--all"])
    assert result.exit_code == 0, result.stdout or repr(result.exception)
    # The op takes no cursor input, so --all must invoke exactly once and never
    # forward a cursor kwarg — no attempt to follow the returned cursor.
    assert invocations == [{"traceflow_id": "tf-1"}]


def _synthetic_write_with_param(param_name: str) -> Operation:
    return Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.vmware.vcenter.thing",
        op_id="act",
        method_name="act",
        cli_verb="act",
        http_method="POST",
        url_template="/vcenter/thing",
        path_vars=[],
        path_var_map={},
        params=[Param(name=param_name, kind=ParamKind.STRING, required=False)],
    )


def test_injected_flags_do_not_collide_with_reserved_param_names() -> None:
    # A write op with a body param literally named 'apply' must not produce two
    # --apply option declarations; the user param is renamed.
    sig, _spec, _fp = _build_signature(_synthetic_write_with_param("apply"))
    decls: list[str] = []
    for p in sig.parameters.values():
        info = p.default
        for d in getattr(info, "param_decls", None) or []:
            decls.append(d)
    apply_decls = [d for d in decls if d in ("--apply/--no-apply", "--apply")]
    assert len(apply_decls) == 1  # only the injected gate, not the user param
    assert "--apply-" in decls  # user param renamed to avoid the clash
