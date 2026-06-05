"""pyVmomi → JSON adapter and the SmartConnect wrapper (no live vCenter)."""

from __future__ import annotations

import datetime as _dt
from typing import Any

from pyVmomi import vim

from vsc.connect import vmomi
from vsc.connect.vmomi import vmomi_jsonable


def test_scalars_pass_through() -> None:
    assert vmomi_jsonable("x") == "x"
    assert vmomi_jsonable(7) == 7
    assert vmomi_jsonable(True) is True
    assert vmomi_jsonable(None) is None


def test_lists_recurse() -> None:
    assert vmomi_jsonable([1, "a", None]) == [1, "a", None]


def test_datetime_becomes_isoformat() -> None:
    ts = _dt.datetime(2026, 6, 5, 12, 0, tzinfo=_dt.UTC)
    assert vmomi_jsonable(ts) == ts.isoformat()


def test_managed_object_becomes_type_value() -> None:
    vm = vim.VirtualMachine("vm-101", None)
    assert vmomi_jsonable(vm) == {"type": "VirtualMachine", "value": "vm-101"}


def test_data_object_becomes_dict_of_set_properties() -> None:
    counter = vim.PerfMetricId(counterId=2, instance="agg")
    out = vmomi_jsonable(counter)
    assert out == {"counterId": 2, "instance": "agg"}
    # The dynamicType/dynamicProperty noise (always None here) is dropped.
    assert "dynamicType" not in out


def test_nested_data_object_with_moref_and_datetime() -> None:
    series = vim.PerfMetricIntSeries(id=vim.PerfMetricId(counterId=2, instance=""), value=[10, 20])
    out = vmomi_jsonable(series)
    assert out["value"] == [10, 20]
    assert out["id"] == {"counterId": 2, "instance": ""}


def test_managed_object_nested_in_data_object() -> None:
    # A managed object reached *through* a data object's property must collapse to
    # its moref via recursion (ManagedObject is handled before DynamicData).
    em = vim.PerfEntityMetric(entity=vim.VirtualMachine("vm-9", None), sampleInfo=[], value=[])
    assert vmomi_jsonable(em) == {"entity": {"type": "VirtualMachine", "value": "vm-9"}}


# --------------------------------------------------------------------------- #
# connect_vmomi
# --------------------------------------------------------------------------- #


def test_connect_vmomi_uses_target_and_caches(monkeypatch: Any) -> None:
    vmomi.reset_vmomi_cache()
    calls: list[dict[str, Any]] = []

    class _Target:
        server = "vc.example"
        username = "administrator@vsphere.local"
        password = "s3cret"
        verify = True

    monkeypatch.setattr(vmomi, "resolve_target", lambda _backend: _Target())

    def fake_smart_connect(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(vmomi, "SmartConnect", fake_smart_connect)

    si1 = vmomi.connect_vmomi()
    si2 = vmomi.connect_vmomi()
    assert si1 is si2  # cached: SmartConnect called once
    assert len(calls) == 1
    assert calls[0]["host"] == "vc.example"
    assert calls[0]["user"] == "administrator@vsphere.local"
    assert calls[0]["pwd"] == "s3cret"
    vmomi.reset_vmomi_cache()


def test_connect_vmomi_insecure_disables_verification(monkeypatch: Any) -> None:
    vmomi.reset_vmomi_cache()
    captured: dict[str, Any] = {}

    class _Target:
        server = "vc.example"
        username = "u"
        password = "p"
        verify = False

    monkeypatch.setattr(vmomi, "resolve_target", lambda _backend: _Target())

    def fake_smart_connect(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(vmomi, "SmartConnect", fake_smart_connect)
    vmomi.connect_vmomi()
    ctx = captured["sslContext"]
    assert ctx.verify_mode.name == "CERT_NONE"  # verification disabled for insecure
    vmomi.reset_vmomi_cache()


def test_connect_vmomi_secure_requires_verification(monkeypatch: Any) -> None:
    # The default (verify=True) MUST keep TLS verification on — a regression that
    # disabled it would otherwise pass silently.
    vmomi.reset_vmomi_cache()
    captured: dict[str, Any] = {}

    class _Target:
        server = "vc.example"
        username = "u"
        password = "p"
        verify = True

    monkeypatch.setattr(vmomi, "resolve_target", lambda _backend: _Target())
    monkeypatch.setattr(vmomi, "SmartConnect", lambda **kw: captured.update(kw) or object())
    vmomi.connect_vmomi()
    ctx = captured["sslContext"]
    assert ctx.verify_mode.name == "CERT_REQUIRED"
    assert ctx.check_hostname is True
    vmomi.reset_vmomi_cache()
