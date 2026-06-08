"""Live id completion: opt-in, cached, timeout-bounded, blanket fail-soft.

No real vCenter is touched — the list-op fetch (`_fetch_ids`) is mocked. These
tests pin the safety contract: off by default, never raise, never hang, and
never cache a failure.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import ClassVar

import pytest

from vsc.gen import complete_dynamic as cd
from vsc.gen.builder import _build_signature
from vsc.gen.model import Operation, Param, ParamKind
from vsc.gen.resources import ResourceSource


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("VSC_COMPLETE_DYNAMIC", raising=False)
    monkeypatch.delenv("VSC_COMPLETE_TTL", raising=False)
    monkeypatch.delenv("VSC_COMPLETE_TIMEOUT", raising=False)
    # active profile lookup should be inert in tests
    monkeypatch.setattr(cd, "active_profile_name", lambda: None)


def _fake_items(monkeypatch: pytest.MonkeyPatch, items: list[tuple[str, str]]) -> None:
    monkeypatch.setattr(cd, "_fetch_ids", lambda _src: list(items))


def test_disabled_by_default_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even a working fetch must not run when the opt-in is unset.
    def boom(_src: object) -> list[tuple[str, str]]:
        raise AssertionError("fetch must not run when dynamic completion is disabled")

    monkeypatch.setattr(cd, "_fetch_ids", boom)
    assert cd.resource_completer("VirtualMachine")("") == []


def test_disabled_opens_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_backend: str) -> object:
        raise AssertionError("no connection at <TAB> by default")

    monkeypatch.setattr(cd, "connect_for_backend", boom)
    assert cd.resource_completer("VirtualMachine")("vm-") == []


def test_enabled_returns_ids_prefix_filtered_with_name_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    _fake_items(monkeypatch, [("vm-1", "web"), ("vm-2", "db"), ("host-1", "esx")])
    complete = cd.resource_completer("VirtualMachine")
    assert complete("") == [("vm-1", "web"), ("vm-2", "db"), ("host-1", "esx")]
    assert complete("vm-") == [("vm-1", "web"), ("vm-2", "db")]
    assert complete("vm-1") == [("vm-1", "web")]


def test_cache_hit_avoids_second_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    calls = 0

    def fetch(_src: object) -> list[tuple[str, str]]:
        nonlocal calls
        calls += 1
        return [("vm-1", "web")]

    monkeypatch.setattr(cd, "_fetch_ids", fetch)
    complete = cd.resource_completer("VirtualMachine")
    complete("")
    complete("")
    assert calls == 1  # second press served from cache


def test_fetch_error_returns_empty_and_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    calls = 0

    def boom(_src: object) -> list[tuple[str, str]]:
        nonlocal calls
        calls += 1
        raise RuntimeError("auth failed")

    monkeypatch.setattr(cd, "_fetch_ids", boom)
    complete = cd.resource_completer("VirtualMachine")
    assert complete("") == []
    assert complete("") == []
    assert calls == 2  # failure was not cached; it retried


def test_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    monkeypatch.setenv("VSC_COMPLETE_TIMEOUT", "0.05")

    def slow(_src: object) -> list[tuple[str, str]]:
        time.sleep(1.0)
        return [("vm-1", "web")]

    monkeypatch.setattr(cd, "_fetch_ids", slow)
    assert cd.resource_completer("VirtualMachine")("") == []


def test_unknown_resource_type_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    assert cd.resource_completer("NoSuchType")("") == []


def test_none_resource_type_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSC_COMPLETE_DYNAMIC", "1")
    assert cd.resource_completer(None)("") == []


def test_extract_handles_plain_and_cursor_results() -> None:
    src = ResourceSource(
        backend="vsphere",
        service_cls=object,
        list_op=Operation(
            backend="vsphere",
            service_cls=object,
            iface_id="x.VM",
            op_id="list",
            method_name="list",
            cli_verb="list",
            http_method="GET",
            url_template="/vm",
        ),
        id_field="vm",
        name_field="name",
    )

    class Row:
        def __init__(self, vm: str, name: str) -> None:
            self.vm = vm
            self.name = name

    plain = [Row("vm-1", "web"), Row("vm-2", "db")]
    assert cd._extract(plain, src) == [("vm-1", "web"), ("vm-2", "db")]

    class Cursor:
        results: ClassVar[list[object]] = [Row("vm-9", "z")]

    assert cd._extract(Cursor(), src) == [("vm-9", "z")]


# --------------------------------------------------------------------------- #
# Builder wiring: ID-kind args/options carry the resource completer
# --------------------------------------------------------------------------- #


def _id_param(*, in_path: bool) -> Param:
    p = Param(name="vm", kind=ParamKind.ID, required=True, in_path=in_path)
    p.resource_types = "VirtualMachine"
    return p


def _op_with(param: Param) -> Operation:
    return Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.vmware.vcenter.VM",
        op_id="get",
        method_name="get",
        cli_verb="get",
        http_method="GET",
        url_template="/vcenter/vm/{vm}",
        path_vars=["vm"] if param.in_path else [],
        params=[param],
    )


def test_id_path_argument_gets_resource_completer() -> None:
    sig, _spec, _fp = _build_signature(_op_with(_id_param(in_path=True)))
    arg = sig.parameters["vm"].default
    assert arg.autocompletion is not None
    # Inert (offline) by default — no env, so no fetch, returns [].
    assert arg.autocompletion("") == []


def test_id_option_gets_resource_completer() -> None:
    sig, _spec, _fp = _build_signature(_op_with(_id_param(in_path=False)))
    opt = sig.parameters["vm"].default
    assert opt.autocompletion is not None
    assert opt.autocompletion("") == []


def test_id_param_without_resource_type_has_no_completer() -> None:
    bare = Param(name="vm", kind=ParamKind.ID, required=False, in_path=False)
    sig, _spec, _fp = _build_signature(_op_with(bare))
    assert sig.parameters["vm"].default.autocompletion is None


def test_building_signature_opens_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_backend: str) -> object:
        raise AssertionError("signature build must stay offline")

    monkeypatch.setattr(cd, "connect_for_backend", boom)
    sig = inspect.signature  # keep import used
    assert sig is not None
    _build_signature(_op_with(_id_param(in_path=True)))  # must not raise
