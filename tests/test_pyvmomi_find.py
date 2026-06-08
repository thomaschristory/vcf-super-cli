"""`vsc vsphere inventory find` — pure matcher + container-view retrieval + CLI."""

from __future__ import annotations

import json
from typing import Any

import pytest
import typer
from pyVmomi import vim, vmodl
from typer.testing import CliRunner

from vsc.pyvmomi.find import (
    Criteria,
    find_matches,
    matches,
    summarize,
    validate_criteria,
)
from vsc.pyvmomi.inventory import inventory_app

runner = CliRunner()


# --------------------------------------------------------------------------- #
# props-dict fixtures (the matcher only ever sees plain dicts)
# --------------------------------------------------------------------------- #


def _props(
    *,
    name: str = "web-1",
    power: str = "poweredOn",
    primary_ip: str | None = "10.20.3.41",
    nics: list[dict[str, Any]] | None = None,
    hostname: str | None = "web-1.corp",
    guest_os: str | None = "Ubuntu Linux (64-bit)",
) -> dict[str, Any]:
    props: dict[str, Any] = {"name": name, "runtime.powerState": power}
    if primary_ip is not None:
        props["guest.ipAddress"] = primary_ip
    if nics is not None:
        props["guest.net"] = nics
    if hostname is not None:
        props["guest.hostName"] = hostname
    if guest_os is not None:
        props["guest.guestFullName"] = guest_os
    return props


# --------------------------------------------------------------------------- #
# matcher — IP
# --------------------------------------------------------------------------- #


def test_match_exact_ip() -> None:
    assert matches(_props(), Criteria(ip=("10.20.3.41",)))
    assert not matches(_props(), Criteria(ip=("10.20.3.42",)))


def test_match_cidr() -> None:
    assert matches(_props(), Criteria(ip=("10.20.3.0/24",)))
    assert not matches(_props(), Criteria(ip=("10.20.4.0/24",)))


def test_match_ipv6() -> None:
    props = _props(primary_ip=None, nics=[{"ipAddress": ["fe80::1", "2001:db8::5"]}])
    assert matches(props, Criteria(ip=("2001:db8::5",)))
    assert matches(props, Criteria(ip=("2001:db8::/32",)))
    assert not matches(props, Criteria(ip=("2001:dead::/32",)))


def test_match_ip_across_multiple_nics() -> None:
    props = _props(
        primary_ip="10.0.0.1",
        nics=[{"ipAddress": ["10.0.0.1"]}, {"ipAddress": ["192.168.5.9"]}],
    )
    assert matches(props, Criteria(ip=("192.168.5.9",)))


def test_no_tools_vm_has_no_ip() -> None:
    bare = {"name": "db-1", "runtime.powerState": "poweredOff"}
    assert not matches(bare, Criteria(ip=("10.20.3.41",)))


def test_ip_or_within_field() -> None:
    # Repeated --ip is OR: the VM only needs one of them.
    assert matches(_props(), Criteria(ip=("10.0.0.9", "10.20.3.41")))


def test_garbage_guest_address_does_not_crash() -> None:
    props = _props(primary_ip="not-an-ip", nics=[{"ipAddress": ["10.20.3.41"]}])
    assert matches(props, Criteria(ip=("10.20.3.41",)))


# --------------------------------------------------------------------------- #
# matcher — text / mac / power
# --------------------------------------------------------------------------- #


def test_name_substring_case_insensitive() -> None:
    assert matches(_props(name="PROD-web-1"), Criteria(name=("web",)))


def test_name_glob() -> None:
    assert matches(_props(name="web-prod-1"), Criteria(name=("web-*-1",)))
    assert not matches(_props(name="web-prod-2"), Criteria(name=("web-*-1",)))


def test_hostname_and_guest_os_match() -> None:
    assert matches(_props(), Criteria(hostname=("corp",)))
    assert matches(_props(), Criteria(guest_os=("ubuntu",)))


def test_mac_exact_case_insensitive() -> None:
    props = _props(nics=[{"macAddress": "00:50:56:AA:BB:CC"}])
    assert matches(props, Criteria(mac=("00:50:56:aa:bb:cc",)))
    assert not matches(props, Criteria(mac=("00:50:56:aa:bb:cd",)))


def test_power_state_match() -> None:
    assert matches(_props(power="poweredOff"), Criteria(power_state=("poweredOff",)))
    assert not matches(_props(power="poweredOn"), Criteria(power_state=("poweredOff",)))


# --------------------------------------------------------------------------- #
# matcher — AND across fields, no-match
# --------------------------------------------------------------------------- #


def test_and_across_fields() -> None:
    crit = Criteria(ip=("10.20.3.41",), power_state=("poweredOn",), name=("web",))
    assert matches(_props(), crit)
    # One failing field fails the whole match (AND).
    assert not matches(_props(power="poweredOff"), crit)


def test_no_match_returns_false() -> None:
    assert not matches(_props(), Criteria(name=("does-not-exist",)))


# --------------------------------------------------------------------------- #
# Criteria / validation
# --------------------------------------------------------------------------- #


def test_is_empty() -> None:
    assert Criteria().is_empty
    assert not Criteria(ip=("10.0.0.1",)).is_empty


def test_validate_rejects_bad_ip() -> None:
    with pytest.raises(ValueError, match="invalid --ip"):
        validate_criteria(Criteria(ip=("999.1.1.1",)))


def test_validate_rejects_bad_power_state() -> None:
    with pytest.raises(ValueError, match="invalid --power-state"):
        validate_criteria(Criteria(power_state=("on",)))


def test_validate_accepts_cidr_and_exact() -> None:
    validate_criteria(Criteria(ip=("10.20.3.0/24", "10.20.3.41"), power_state=("poweredOn",)))


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #


def test_summarize_shape_and_extra_props() -> None:
    props = _props(nics=[{"ipAddress": ["10.20.3.41", "fe80::1"]}])
    props["config.hardware.numCPU"] = 4
    hit = summarize({"type": "VirtualMachine", "value": "vm-1"}, props, ["config.hardware.numCPU"])
    assert hit["name"] == "web-1"
    assert hit["power_state"] == "poweredOn"
    assert "10.20.3.41" in hit["ip_addresses"]
    assert hit["hostname"] == "web-1.corp"
    assert hit["properties"] == {"config.hardware.numCPU": 4}


def test_summarize_no_extra_props_omits_properties_key() -> None:
    hit = summarize({"type": "VirtualMachine", "value": "vm-1"}, _props(), [])
    assert "properties" not in hit


# --------------------------------------------------------------------------- #
# retrieval over a mocked PropertyCollector (single round-trip, view destroyed)
# --------------------------------------------------------------------------- #


def _object_content(moid: str, **props: Any) -> Any:
    return vmodl.query.PropertyCollector.ObjectContent(
        obj=vim.VirtualMachine(moid, None),
        propSet=[vmodl.DynamicProperty(name=k, val=v) for k, v in props.items()],
    )


class _RecStub:
    """Records managed-method invocations so we can assert the view was destroyed."""

    def __init__(self) -> None:
        self.destroyed = False

    def InvokeMethod(self, *args: Any, **kwargs: Any) -> None:
        self.destroyed = True  # ContainerView.Destroy() is the only call we make


class _FakeView:
    """A real ContainerView (so ObjectSpec.obj type-checks) over a recording stub."""

    def __init__(self) -> None:
        self.stub = _RecStub()
        self.view = vim.view.ContainerView("view-1", self.stub)

    @property
    def destroyed(self) -> bool:
        return self.stub.destroyed


class _FakeViewManager:
    def __init__(self, view: _FakeView) -> None:
        self._view = view

    def CreateContainerView(self, container: Any, type_: Any, recursive: Any) -> Any:
        return self._view.view


class _FakePC:
    def __init__(self, contents: list[Any]) -> None:
        self.contents = contents
        self.calls = 0
        self.captured: Any = None

    def RetrieveContents(self, specSet: Any) -> list[Any]:
        self.calls += 1
        self.captured = specSet
        return self.contents


def _fake_si(pc: _FakePC, view: _FakeView) -> Any:
    content = type(
        "C",
        (),
        {
            "propertyCollector": pc,
            "viewManager": _FakeViewManager(view),
            "rootFolder": object(),
        },
    )()
    return type("SI", (), {"content": content, "_stub": object()})()


def test_find_matches_single_round_trip_and_destroys_view() -> None:
    contents = [
        _object_content("vm-1", **{"name": "web-1", "guest.ipAddress": "10.20.3.41"}),
        _object_content("vm-2", **{"name": "db-1", "guest.ipAddress": "10.20.9.9"}),
    ]
    pc, view = _FakePC(contents), _FakeView()
    hits = find_matches(_fake_si(pc, view), Criteria(ip=("10.20.3.41",)), [])
    assert pc.calls == 1  # one RetrieveContents for the whole inventory
    assert view.destroyed  # container view torn down in finally
    assert [h["obj"]["value"] for h in hits] == ["vm-1"]


def test_find_matches_appends_extra_props_to_path_set() -> None:
    pc, view = _FakePC([]), _FakeView()
    find_matches(_fake_si(pc, view), Criteria(name=("x",)), ["config.hardware.numCPU"])
    path_set = pc.captured[0].propSet[0].pathSet
    assert "config.hardware.numCPU" in path_set
    assert "guest.net" in path_set  # fixed search paths still present
    assert path_set.count("config.hardware.numCPU") == 1  # deduped


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(inventory_app, name="inventory")
    return app


def test_find_cli_by_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    contents = [_object_content("vm-1", **{"name": "web-1", "guest.ipAddress": "10.20.3.41"})]
    pc, view = _FakePC(contents), _FakeView()
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc, view))
    result = runner.invoke(_app(), ["inventory", "find", "--ip", "10.20.3.41"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["obj"]["value"] == "vm-1"
    assert out[0]["ip_addresses"] == ["10.20.3.41"]


def test_find_cli_with_props(monkeypatch: pytest.MonkeyPatch) -> None:
    contents = [
        _object_content(
            "vm-1",
            **{"name": "web-1", "guest.ipAddress": "10.20.3.41", "config.version": "vmx-19"},
        )
    ]
    pc, view = _FakePC(contents), _FakeView()
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc, view))
    result = runner.invoke(
        _app(), ["inventory", "find", "--name", "web", "--props", "config.version"]
    )
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["properties"] == {"config.version": "vmx-19"}


def test_find_cli_no_match_flag_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    pc, view = _FakePC([]), _FakeView()
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc, view))
    # --props alone does not count as a match flag.
    result = runner.invoke(_app(), ["inventory", "find", "--props", "config.version"])
    assert result.exit_code == 2, result.stdout
    assert pc.calls == 0  # refused before any retrieve


def test_find_cli_bad_ip_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    pc, view = _FakePC([]), _FakeView()
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc, view))
    result = runner.invoke(_app(), ["inventory", "find", "--ip", "999.1.1.1"])
    assert result.exit_code == 2, result.stdout


def test_find_cli_no_matches_empty_array(monkeypatch: pytest.MonkeyPatch) -> None:
    pc, view = _FakePC([]), _FakeView()
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc, view))
    result = runner.invoke(_app(), ["inventory", "find", "--ip", "10.20.3.41"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []
