"""Static (offline) shell-completion helpers and their wiring into commands."""

from __future__ import annotations

import inspect
from typing import ClassVar

import pytest

from vsc.gen.builder import _OUTPUT_PARAM, _build_signature
from vsc.gen.complete import enum_completer, output_format_completer, profile_completer
from vsc.gen.model import Operation, Param, ParamKind


def test_enum_completer_prefix_filters() -> None:
    complete = enum_completer(["POWERED_ON", "POWERED_OFF", "SUSPENDED"])
    assert complete("POWERED_") == ["POWERED_ON", "POWERED_OFF"]


def test_enum_completer_empty_incomplete_returns_all() -> None:
    values = ["A", "B", "C"]
    assert enum_completer(values)("") == values


def test_enum_completer_no_match_returns_empty() -> None:
    assert enum_completer(["A", "B"])("Z") == []


def test_enum_completer_none_incomplete_returns_all() -> None:
    # Typer's wrapper types incomplete as ``str | None``; a None must not crash
    # completion — treat it like an empty prefix.
    assert enum_completer(["A", "B"])(None) == ["A", "B"]  # type: ignore[arg-type]


def test_output_format_completer_offers_formats() -> None:
    assert output_format_completer()("") == ["json", "table"]
    assert output_format_completer()("t") == ["table"]


def test_profile_completer_filters_names(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Cfg:
        profiles: ClassVar[dict[str, object]] = {"prod": 1, "prod-eu": 2, "lab": 3}

    monkeypatch.setattr("vsc.gen.complete.load_config", _Cfg)
    assert profile_completer()("prod") == ["prod", "prod-eu"]


def test_profile_completer_is_failsoft(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> object:
        raise RuntimeError("no config readable")

    monkeypatch.setattr("vsc.gen.complete.load_config", _boom)
    assert profile_completer()("anything") == []  # never raises during <TAB>


# --------------------------------------------------------------------------- #
# Wiring: generated options carry the right completer
# --------------------------------------------------------------------------- #


def _op_with(param: Param) -> Operation:
    return Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.vmware.vcenter.thing",
        op_id="get",
        method_name="get",
        cli_verb="get",
        http_method="GET",
        url_template="/vcenter/thing",
        path_vars=[],
        path_var_map={},
        params=[param],
    )


def _option_for(sig: inspect.Signature, sig_name: str) -> object:
    return sig.parameters[sig_name].default


def test_enum_option_gets_autocompletion() -> None:
    enum_param = Param(name="state", kind=ParamKind.ENUM, required=False, enum_values=["ON", "OFF"])
    sig, _spec, _fp = _build_signature(_op_with(enum_param))
    opt = _option_for(sig, "state")
    assert opt.autocompletion is not None
    assert opt.autocompletion("O") == ["ON", "OFF"]


def test_non_enum_option_has_no_autocompletion() -> None:
    string_param = Param(name="name", kind=ParamKind.STRING, required=False)
    sig, _spec, _fp = _build_signature(_op_with(string_param))
    assert _option_for(sig, "name").autocompletion is None


def test_output_option_gets_format_completion() -> None:
    string_param = Param(name="name", kind=ParamKind.STRING, required=False)
    sig, _spec, _fp = _build_signature(_op_with(string_param))
    opt = _option_for(sig, _OUTPUT_PARAM)
    assert opt.autocompletion is not None
    assert opt.autocompletion("") == ["json", "table"]
