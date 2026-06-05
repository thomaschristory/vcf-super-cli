"""Enumerate vAPI service classes and their operations, fully offline.

Every service is a ``VapiInterface`` subclass; instantiating it with a
``StubConfiguration`` built on a no-op connector populates the generated
``_<Name>Stub`` (``service._api_interface``) whose ``_operations`` and
``_rest_metadata`` dicts carry everything we need — no server required.
"""

from __future__ import annotations

import importlib
from typing import Any

import com.vmware.vcenter_client as vc
import structlog
from vmware.vapi.bindings.stub import StubConfiguration
from vmware.vapi.protocol.client.connector import Connector

from vsc.gen.model import Operation
from vsc.gen.params import param_from_type

log = structlog.get_logger(__name__)

# Canonical read verbs; anything else keeps its operation id as the command name.
_KNOWN_VERBS = frozenset({"get", "list", "create", "delete", "update"})


class _OfflineConnector(Connector):  # type: ignore[misc]
    """A connector with no API provider — enough to read embedded metadata."""

    def __init__(self) -> None:
        super().__init__(api_provider=None, provider_filter_chain=[])

    def connect(self) -> None:  # pragma: no cover - never called offline
        pass

    def disconnect(self) -> None:  # pragma: no cover - never called offline
        pass


def introspect_stub(service_cls: type) -> Any:
    """Return the generated ``_<Name>Stub`` (ApiInterfaceStub) for a service."""
    service = service_cls(StubConfiguration(_OfflineConnector()))
    return service._api_interface


def _cli_verb(op_id: str, http_method: str) -> str:
    if op_id in _KNOWN_VERBS:
        return op_id
    low = op_id.lower()
    if "list" in low:
        return "list"
    if low.startswith("read") or "_read_" in low or "{" in low:
        return "get"
    if http_method == "GET":
        return "get"
    return op_id.replace("$", "-")


def discover_operations(
    service_cls: type, backend: str, *, read_only: bool = True
) -> list[Operation]:
    """Introspect ``service_cls`` into a list of :class:`Operation`.

    With ``read_only`` (the v0.1 default) only ``GET`` operations are emitted.
    """
    stub = introspect_stub(service_cls)
    iface_id = stub._iface_id.get_name()
    operations: dict[str, dict[str, Any]] = stub._operations
    rest_metadata: dict[str, Any] = stub._rest_metadata

    ops: list[Operation] = []
    for op_id in sorted(set(operations) & set(rest_metadata)):
        rest = rest_metadata[op_id]
        http_method = rest.http_method
        if read_only and http_method != "GET":
            continue
        input_type = operations[op_id]["input_type"]
        path_vars = tuple(rest.get_path_variable_field_names())
        query_vars = frozenset(rest.get_query_parameter_field_names())
        body_param = rest.request_body_parameter
        params = [
            param_from_type(
                fname,
                input_type.get_field(fname),
                path_vars=path_vars,
                query_vars=query_vars,
                body_param=body_param,
            )
            for fname in input_type.get_field_names()
        ]
        ops.append(
            Operation(
                backend=backend,
                service_cls=service_cls,
                iface_id=iface_id,
                op_id=op_id,
                method_name=op_id,
                cli_verb=_cli_verb(op_id, http_method),
                http_method=http_method,
                url_template=rest._url_template,
                path_vars=list(path_vars),
                params=params,
                output_type=operations[op_id].get("output_type"),
                error_types=operations[op_id].get("errors", []),
            )
        )
    return ops


# --------------------------------------------------------------------------- #
# Curated service catalogs (v0.1 read-only surface)
# --------------------------------------------------------------------------- #


def vsphere_services() -> list[type]:
    """vCenter service classes exposed under ``vsc vsphere`` for v0.1."""
    return [vc.VM, vc.Host, vc.Cluster, vc.Datacenter, vc.Datastore, vc.Folder, vc.Network]


# (module path, attribute names) for NSX Policy services. Imported defensively so
# a single moved symbol cannot break the whole NSX surface.
_NSX_SERVICE_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "vcf.nsx.policy.api.v1.infra_client",
        ("Segments", "Tier0s", "Tier1s", "Services"),
    ),
    (
        "vcf.nsx.policy.api.v1.infra.domains_client",
        ("Groups", "SecurityPolicies", "GatewayPolicies"),
    ),
)


def nsx_services() -> list[type]:
    """NSX Policy service classes exposed under ``vsc nsx`` for v0.1."""
    services: list[type] = []
    for module_path, names in _NSX_SERVICE_SPECS:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            log.warning("nsx.module_import_failed", module=module_path, error=str(exc))
            continue
        for name in names:
            cls = getattr(module, name, None)
            if cls is None:
                log.warning("nsx.service_missing", module=module_path, name=name)
                continue
            services.append(cls)
    return services


def discover_all(*, read_only: bool = True) -> list[Operation]:
    """Discover every v0.1 operation across both backends."""
    ops: list[Operation] = []
    for cls in vsphere_services():
        ops.extend(discover_operations(cls, "vsphere", read_only=read_only))
    for cls in nsx_services():
        ops.extend(discover_operations(cls, "nsx", read_only=read_only))
    return ops
