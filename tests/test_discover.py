"""Offline introspection tests against the real installed vcf-sdk."""

from __future__ import annotations

from vsc.gen.discover import (
    _action_from_url,
    discover_all,
    discover_operations,
    nsx_services,
    vsphere_services,
)
from vsc.gen.model import Operation, ParamKind


def test_vsphere_services_include_core_inventory() -> None:
    names = {c.__name__ for c in vsphere_services()}
    assert {"VM", "Host", "Cluster", "Datastore", "Network"} <= names


def test_nsx_services_resolve() -> None:
    names = {c.__name__ for c in nsx_services()}
    assert "Segments" in names
    assert len(names) >= 5


def test_vm_get_and_list_are_generated() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere", read_only=True)
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


# --------------------------------------------------------------------------- #
# v0.2: write discovery
# --------------------------------------------------------------------------- #


def _vm_writes() -> list[Operation]:
    vm = vsphere_services()[0]
    return [o for o in discover_operations(vm, "vsphere", read_only=False) if o.is_write]


def test_default_discovery_includes_writes() -> None:
    # v0.2 default is write-enabled (read_only defaults to False).
    vm = vsphere_services()[0]
    ops = discover_operations(vm, "vsphere")
    assert any(o.is_write for o in ops)
    assert any(not o.is_write for o in ops)


def test_is_write_tracks_http_method() -> None:
    vm = vsphere_services()[0]
    ops = discover_operations(vm, "vsphere", read_only=False)
    for o in ops:
        assert o.is_write == (o.http_method != "GET")


def test_vm_create_and_delete_are_writes() -> None:
    by_verb = {o.cli_verb: o for o in _vm_writes()}
    assert "create" in by_verb and by_verb["create"].http_method == "POST"
    assert "delete" in by_verb and by_verb["delete"].http_method == "DELETE"


def test_path_var_map_maps_field_to_template_var() -> None:
    # The runtime field name and the URL template variable differ for
    # resource-pool: field 'resource_pool' -> template var 'resource-pool'.
    rp = next(c for c in vsphere_services() if c.__name__ == "ResourcePool")
    delete = next(
        o for o in discover_operations(rp, "vsphere", read_only=False) if o.cli_verb == "delete"
    )
    assert delete.path_var_map == {"resource_pool": "resource-pool"}
    assert "{resource-pool}" in delete.url_template


def test_path_var_map_camelcase_for_nsx() -> None:
    # NSX maps snake_case fields to camelCase template vars.
    segments = next(c for c in nsx_services() if c.__name__ == "Segments")
    delete = next(
        o for o in discover_operations(segments, "nsx", read_only=False) if o.cli_verb == "delete"
    )
    assert delete.path_var_map == {"segment_id": "segmentId"}
    assert "{segmentId}" in delete.url_template


def test_post_without_action_uses_kebab_op_id() -> None:
    # The dominant vSphere write-verb path: POST with no ?action -> hyphenated op id.
    by_verb = {o.cli_verb: o for o in _vm_writes()}
    assert "instant-clone" in by_verb
    assert by_verb["instant-clone"].http_method == "POST"
    assert all("_" not in o.cli_verb for o in _vm_writes())


def test_write_verbs_are_clean_for_nsx() -> None:
    segments = next(c for c in nsx_services() if c.__name__ == "Segments")
    verbs = {
        o.cli_verb for o in discover_operations(segments, "nsx", read_only=False) if o.is_write
    }
    # PUT -> set, PATCH -> patch, DELETE -> delete, POST ?action -> the action.
    assert {"set", "patch", "delete"} <= verbs
    assert "force-delete" in verbs  # force variant kept distinct
    assert not any(v.startswith("policy_lm_") or "_" in v for v in verbs)


def test_post_action_verb_from_url() -> None:
    secpol = next(c for c in nsx_services() if c.__name__ == "SecurityPolicies")
    verbs = {o.cli_verb for o in discover_operations(secpol, "nsx", read_only=False)}
    assert "revise" in verbs  # POST .../?action=revise


def test_vsphere_catalog_expansion() -> None:
    names = {c.__name__ for c in vsphere_services()}
    assert {"Power", "Cpu", "Memory", "Disk", "Ethernet", "ResourcePool"} <= names


def test_nsx_catalog_expansion() -> None:
    names = {c.__name__ for c in nsx_services()}
    assert {"IpPools", "DhcpServerConfigs", "DhcpRelayConfigs", "LocaleServices"} <= names


def test_expanded_catalog_read_contract_holds() -> None:
    # Across every expanded service, read_only=True must still yield only GET ops
    # whose verb is in the v0.1 read vocabulary — locking the read contract.
    for cls in vsphere_services() + nsx_services():
        backend = "vsphere" if cls in vsphere_services() else "nsx"
        for op in discover_operations(cls, backend, read_only=True):
            assert op.http_method == "GET"
            assert op.cli_verb in {"get", "list"}


# --------------------------------------------------------------------------- #
# NSX Traceflow (#58)
# --------------------------------------------------------------------------- #


def test_nsx_catalog_includes_traceflow_services() -> None:
    names = {c.__name__ for c in nsx_services()}
    assert {"Traceflows", "Observations"} <= names


def _traceflow_ops() -> list[Operation]:
    tf = next(c for c in nsx_services() if c.__name__ == "Traceflows")
    return discover_operations(tf, "nsx", read_only=False)


def test_traceflows_expose_crud_verbs() -> None:
    by_verb = {o.cli_verb: o for o in _traceflow_ops()}
    assert by_verb["list"].http_method == "GET"
    assert by_verb["get"].http_method == "GET"
    assert by_verb["set"].http_method == "PUT"
    assert by_verb["patch"].http_method == "PATCH"
    assert by_verb["delete"].http_method == "DELETE"


def test_traceflows_set_body_is_required_struct() -> None:
    set_op = next(o for o in _traceflow_ops() if o.cli_verb == "set")
    cfg = next(p for p in set_op.params if p.name == "traceflow_config")
    assert cfg.kind is ParamKind.STRUCT
    assert cfg.required
    assert cfg.is_body


def test_observations_list_has_required_traceflow_id_path_param() -> None:
    obs = next(c for c in nsx_services() if c.__name__ == "Observations")
    list_op = next(o for o in discover_operations(obs, "nsx") if o.cli_verb == "list")
    tid = next(p for p in list_op.params if p.name == "traceflow_id")
    assert tid.in_path
    assert tid.required


def test_action_from_url_edge_cases() -> None:
    assert _action_from_url("/x?action=revise") == "revise"
    assert _action_from_url("/x?force=true&action=reprocess") == "reprocess"  # not first
    assert _action_from_url("/x?action=") is None  # empty value
    assert _action_from_url("/x?force=true") is None  # no action key
    assert _action_from_url("/vcenter/vm/{vm}") is None  # no query
    assert _action_from_url("/weird/action=nope") is None  # 'action=' but no '?'
