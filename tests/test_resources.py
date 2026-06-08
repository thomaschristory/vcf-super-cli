"""The resource-type -> list-op registry that powers live id completion.

The registry is built purely by introspecting the SDK metadata (``discover_all``);
no network call is involved. It maps a vAPI ``resource_type`` (carried on an
``ID``-kind :class:`Param`) to the *list* operation that enumerates those ids,
plus which element fields hold the id and a human-readable name.
"""

from __future__ import annotations

from vsc.gen.model import Operation, Param, ParamKind
from vsc.gen.resources import ResourceSource, build_resource_registry, resource_source


def test_virtual_machine_resolves_to_vm_list() -> None:
    src = resource_source("VirtualMachine")
    assert src is not None
    assert src.backend == "vsphere"
    assert src.list_op.cli_verb == "list"
    assert src.list_op.service_short == "vm"
    assert src.id_field == "vm"
    assert src.name_field == "name"


def test_host_and_cluster_resolve() -> None:
    host = resource_source("HostSystem")
    assert host is not None
    assert host.backend == "vsphere"
    assert host.id_field == "host"
    assert host.name_field == "name"

    cluster = resource_source("ClusterComputeResource")
    assert cluster is not None
    assert cluster.id_field == "cluster"


def test_unknown_resource_type_returns_none() -> None:
    assert resource_source("NoSuchType") is None


def test_subresource_types_are_unsupported() -> None:
    # Disk/Ethernet ids only make sense relative to a parent VM (their list op
    # needs a required ``vm`` path arg), so they are deliberately not registered:
    # tab-completing them standalone is meaningless.
    assert resource_source("com.vmware.vcenter.vm.hardware.Disk") is None


def test_registry_is_offline_and_covers_core_inventory() -> None:
    registry = build_resource_registry()
    # Every core vSphere inventory type the SDK annotates with a resource_type.
    for rt in (
        "VirtualMachine",
        "HostSystem",
        "ClusterComputeResource",
        "Datacenter",
        "Datastore",
        "ResourcePool",
    ):
        assert rt in registry, rt
        assert isinstance(registry[rt], ResourceSource)


def test_injected_operations_resolve_without_discovery() -> None:
    # A by-id "get" op carries the resource_type; the sibling "list" op (same
    # service, no required path arg) yields the ids. The builder must correlate
    # them from an injected op list, never touching discover_all.
    id_param = Param(name="thing", kind=ParamKind.ID, required=True, in_path=True)
    id_param.resource_types = "Widget"
    get_op = Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.example.Thing",
        op_id="get",
        method_name="get",
        cli_verb="get",
        http_method="GET",
        url_template="/things/{thing}",
        path_vars=["thing"],
        params=[id_param],
    )
    list_op = Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.example.Thing",
        op_id="list",
        method_name="list",
        cli_verb="list",
        http_method="GET",
        url_template="/things",
        params=[],
    )
    registry = build_resource_registry([get_op, list_op])
    src = registry.get("Widget")
    assert src is not None
    assert src.list_op is list_op


def test_list_op_with_required_path_arg_is_skipped() -> None:
    # A "list" that needs a parent id is a sub-resource list, not a registry source.
    id_param = Param(name="child", kind=ParamKind.ID, required=True, in_path=True)
    id_param.resource_types = "Child"
    parent = Param(name="parent", kind=ParamKind.ID, required=True, in_path=True)
    list_op = Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.example.Child",
        op_id="list",
        method_name="list",
        cli_verb="list",
        http_method="GET",
        url_template="/parents/{parent}/children",
        path_vars=["parent"],
        params=[id_param, parent],
    )
    assert build_resource_registry([list_op]).get("Child") is None
