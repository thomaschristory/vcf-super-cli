"""Offline introspection tests against the real installed vcf-sdk."""

from __future__ import annotations

from vsc.gen.discover import (
    discover_all,
    discover_operations,
    nsx_services,
    vsphere_services,
)
from vsc.gen.model import ParamKind


def test_vsphere_services_include_core_inventory() -> None:
    names = {c.__name__ for c in vsphere_services()}
    assert {"VM", "Host", "Cluster", "Datastore", "Network"} <= names


def test_nsx_services_resolve() -> None:
    names = {c.__name__ for c in nsx_services()}
    assert "Segments" in names
    assert len(names) >= 5


def test_vm_get_and_list_are_generated() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    by_verb = {o.cli_verb: o for o in ops}
    assert "get" in by_verb and "list" in by_verb
    assert all(o.http_method == "GET" for o in ops)


def test_vm_get_has_required_id_path_param() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    get_op = next(o for o in ops if o.cli_verb == "get")
    vm_param = next(p for p in get_op.params if p.name == "vm")
    assert vm_param.in_path
    assert vm_param.required
    assert vm_param.kind is ParamKind.ID


def test_vm_list_filter_is_optional_struct() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    list_op = next(o for o in ops if o.cli_verb == "list")
    filt = next(p for p in list_op.params if p.name == "filter")
    assert filt.kind is ParamKind.STRUCT
    assert not filt.required
    assert filt.struct_class is not None


def test_read_only_filter_drops_write_ops() -> None:
    vm = vsphere_services()[0]
    reads = discover_operations(vm, "vsphere", read_only=True)
    everything = discover_operations(vm, "vsphere", read_only=False)
    assert all(o.http_method == "GET" for o in reads)
    assert len(everything) > len(reads)  # VM has create/delete/etc.


def test_discover_all_covers_both_backends() -> None:
    ops = discover_all()
    backends = {o.backend for o in ops}
    assert backends == {"vsphere", "nsx"}
