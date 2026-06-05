"""Request-plan (dry-run preview) builder tests. Pure, no network."""

from __future__ import annotations

from vsc.gen.discover import discover_operations, nsx_services, vsphere_services
from vsc.gen.model import Operation, Param, ParamKind
from vsc.gen.preview import build_request_plan


def _write(service_name: str, verb: str, backend: str) -> Operation:
    services = vsphere_services() if backend == "vsphere" else nsx_services()
    cls = next(c for c in services if c.__name__ == service_name)
    return next(o for o in discover_operations(cls, backend, read_only=False) if o.cli_verb == verb)


def test_plan_resolves_kebab_path_var() -> None:
    op = _write("ResourcePool", "delete", "vsphere")
    plan = build_request_plan(op, {"resource_pool": "rp-1"})
    assert plan["method"] == "DELETE"
    assert plan["url"] == "/vcenter/resource-pool/rp-1"
    assert plan["path_params"] == {"resource_pool": "rp-1"}
    assert plan["body"] is None
    assert plan["backend"] == "vsphere"


def test_plan_nsx_named_body_and_camel_path_var() -> None:
    op = _write("Segments", "set", "nsx")
    plan = build_request_plan(op, {"segment_id": "web", "segment": {"display_name": "web"}})
    assert plan["method"] == "PUT"
    assert plan["url"] == "/policy/api/v1/infra/segments/web"
    assert plan["path_params"] == {"segment_id": "web"}
    assert plan["body"] == {"display_name": "web"}  # body is the segment, not wrapped


def test_plan_vsphere_body_from_nonpath_params() -> None:
    op = _write("VM", "create", "vsphere")
    plan = build_request_plan(op, {"spec": {"name": "vm-1"}})
    assert plan["method"] == "POST"
    assert plan["url"] == "/vcenter/vm"
    assert plan["path_params"] == {}
    assert plan["body"] == {"spec": {"name": "vm-1"}}  # vCenter wraps in the param name


def test_plan_omits_absent_optional_values() -> None:
    op = _write("VM", "delete", "vsphere")
    plan = build_request_plan(op, {"vm": "vm-42", "unset": None})
    assert plan["url"] == "/vcenter/vm/vm-42"
    assert "unset" not in plan["body"] if plan["body"] else True


def test_plan_extracts_query_params() -> None:
    # Synthetic op to pin query extraction deterministically.
    op = Operation(
        backend="vsphere",
        service_cls=object,
        iface_id="com.vmware.vcenter.thing",
        op_id="do",
        method_name="do",
        cli_verb="do",
        http_method="POST",
        url_template="/vcenter/thing/{id}",
        path_vars=["id"],
        path_var_map={"id": "id"},
        params=[
            Param(name="id", kind=ParamKind.STRING, required=True, in_path=True),
            Param(name="mode", kind=ParamKind.STRING, required=False, in_query=True),
            Param(name="payload", kind=ParamKind.STRUCT, required=True, is_body=True),
        ],
    )
    plan = build_request_plan(op, {"id": "t1", "mode": "fast", "payload": {"k": 1}})
    assert plan["url"] == "/vcenter/thing/t1"
    assert plan["query"] == {"mode": "fast"}
    assert plan["path_params"] == {"id": "t1"}
    assert plan["body"] == {"k": 1}
