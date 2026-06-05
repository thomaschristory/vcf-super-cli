"""`vsc vsphere inventory vm|host` (pyVmomi PropertyCollector) — helper + CLI."""

from __future__ import annotations

import json
from typing import Any

import pytest
import typer
from pyVmomi import vim, vmodl
from typer.testing import CliRunner

from vsc.pyvmomi.inventory import inventory_app, retrieve_properties

runner = CliRunner()


def _object_content(moid: str, **props: Any) -> Any:
    return vmodl.query.PropertyCollector.ObjectContent(
        obj=vim.VirtualMachine(moid, None),
        propSet=[vmodl.DynamicProperty(name=k, val=v) for k, v in props.items()],
    )


class _FakePC:
    def __init__(self, contents: list[Any]) -> None:
        self.contents = contents
        self.captured: Any = None

    def RetrieveContents(self, specSet: Any) -> list[Any]:
        self.captured = specSet
        return self.contents


def _fake_si(pc: _FakePC) -> Any:
    content = type("C", (), {"propertyCollector": pc})()
    return type("SI", (), {"content": content, "_stub": object()})()


# --------------------------------------------------------------------------- #
# retrieve_properties
# --------------------------------------------------------------------------- #


def test_retrieve_properties_shapes_object_content() -> None:
    pc = _FakePC([_object_content("vm-1", name="web-1", powerState="poweredOn")])
    out = retrieve_properties(pc, vim.VirtualMachine("vm-1", None), ["name", "runtime.powerState"])
    assert out[0]["obj"] == {"type": "VirtualMachine", "value": "vm-1"}
    assert out[0]["properties"] == {"name": "web-1", "powerState": "poweredOn"}


def test_retrieve_properties_builds_filter_spec() -> None:
    pc = _FakePC([])
    retrieve_properties(pc, vim.VirtualMachine("vm-9", None), ["config.hardware"])
    spec = pc.captured[0]
    assert spec.objectSet[0].obj._moId == "vm-9"
    assert spec.propSet[0].type == vim.VirtualMachine
    assert spec.propSet[0].pathSet == ["config.hardware"]
    assert spec.propSet[0].all is False  # specific paths -> not "all properties"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(inventory_app, name="inventory")
    return app


def test_inventory_vm_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    pc = _FakePC([_object_content("vm-1", name="web-1")])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc))
    result = runner.invoke(_app(), ["inventory", "vm", "vm-1", "--props", "name"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["properties"]["name"] == "web-1"
    assert pc.captured[0].propSet[0].pathSet == ["name"]


def test_inventory_vm_default_props(monkeypatch: pytest.MonkeyPatch) -> None:
    pc = _FakePC([_object_content("vm-1", name="web-1")])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc))
    result = runner.invoke(_app(), ["inventory", "vm", "vm-1"])  # no --props
    assert result.exit_code == 0, result.stdout
    assert pc.captured[0].propSet[0].pathSet  # a sensible default set was requested


def test_inventory_host_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    pc = _FakePC([_object_content("host-1", name="esx-1")])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pc))
    result = runner.invoke(_app(), ["inventory", "host", "host-1", "--props", "name"])
    assert result.exit_code == 0, result.stdout
    assert pc.captured[0].propSet[0].type == vim.HostSystem
