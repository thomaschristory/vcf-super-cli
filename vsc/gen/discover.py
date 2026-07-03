"""Enumerate vAPI service classes and their operations, fully offline.

Every service is a ``VapiInterface`` subclass; instantiating it with a
``StubConfiguration`` built on a no-op connector populates the generated
``_<Name>Stub`` (``service._api_interface``) whose ``_operations`` and
``_rest_metadata`` dicts carry everything we need — no server required.
"""

from __future__ import annotations

import importlib
from typing import Any

import structlog
from vmware.vapi.bindings.stub import StubConfiguration
from vmware.vapi.protocol.client.connector import Connector

from vsc.gen.model import Operation
from vsc.gen.params import param_from_type

log = structlog.get_logger(__name__)

# Canonical read verbs; anything else keeps its operation id as the command name.
_KNOWN_VERBS = frozenset({"get", "list", "create", "delete", "update"})

# Mutating HTTP method -> base CLI verb. ``force`` variants are prefixed so they
# stay distinct from their non-force siblings within a service group.
_METHOD_VERB = {"PUT": "set", "PATCH": "patch", "DELETE": "delete"}


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


def _action_from_url(url_template: str) -> str | None:
    """Return the ``?action=<value>`` verb from a REST URL template, if present."""
    if "?" not in url_template:
        return None
    query = url_template.split("?", 1)[1]
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key == "action" and value:
            return value
    return None


def _cli_verb(op_id: str, http_method: str, url_template: str = "") -> str:
    if op_id in _KNOWN_VERBS:
        return op_id
    low = op_id.lower()
    # Reads: keep v0.1 behaviour exactly (these branches run before any write logic).
    if "list" in low:
        return "list"
    if low.startswith("read") or "_read_" in low or "{" in low:
        return "get"
    if http_method == "GET":
        return "get"
    # Writes: prefer an explicit ``?action=`` verb, then the HTTP method, keeping
    # ``force`` variants distinct. POST without an action falls back to its op id.
    action = _action_from_url(url_template)
    if action is not None:
        return action.replace("_", "-")
    base = _METHOD_VERB.get(http_method)
    if base is not None:
        return f"force-{base}" if "force" in low else base
    return op_id.replace("$", "-").replace("_", "-")


def discover_operations(
    service_cls: type, backend: str, *, read_only: bool = False
) -> list[Operation]:
    """Introspect ``service_cls`` into a list of :class:`Operation`.

    With ``read_only=True`` only ``GET`` operations are emitted (the v0.1 surface);
    the v0.2 default emits writes as well.
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
        # field name -> URL template variable (the two differ, e.g.
        # 'resource_pool' -> 'resource-pool', 'segment_id' -> 'segmentId').
        path_var_map = dict(getattr(rest, "_path_variables", None) or {})
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
                cli_verb=_cli_verb(op_id, http_method, rest._url_template),
                http_method=http_method,
                url_template=rest._url_template,
                path_vars=list(path_vars),
                path_var_map=path_var_map,
                params=params,
                output_type=operations[op_id].get("output_type"),
                error_types=operations[op_id].get("errors", []),
            )
        )
    return ops


# --------------------------------------------------------------------------- #
# Curated service catalogs (read + write surface)
# --------------------------------------------------------------------------- #


def _load_services(backend: str, specs: tuple[tuple[str, tuple[str, ...]], ...]) -> list[type]:
    """Resolve ``(module, names)`` specs into classes, skipping any that moved.

    A missing module or symbol is logged and skipped so one relocated class can
    never break a whole backend's command surface.
    """
    services: list[type] = []
    for module_path, names in specs:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            log.warning(
                "service.module_import_failed", backend=backend, module=module_path, error=str(exc)
            )
            continue
        for name in names:
            cls = getattr(module, name, None)
            if cls is None:
                log.warning("service.missing", backend=backend, module=module_path, name=name)
                continue
            services.append(cls)
    return services


# vCenter services. Core inventory lives in ``vcenter_client``; v0.2 adds VM power,
# VM hardware (cpu/memory/disk/ethernet) and resource pools for the write surface.
_VSPHERE_SERVICE_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "com.vmware.vcenter_client",
        ("VM", "Host", "Cluster", "Datacenter", "Datastore", "Folder", "Network", "ResourcePool"),
    ),
    ("com.vmware.vcenter.vm_client", ("Power",)),
    ("com.vmware.vcenter.vm.hardware_client", ("Cpu", "Memory", "Disk", "Ethernet")),
)


def vsphere_services() -> list[type]:
    """vCenter service classes exposed under ``vsc vsphere``."""
    return _load_services("vsphere", _VSPHERE_SERVICE_SPECS)


# NSX Policy services. Imported defensively so a single moved symbol cannot break
# the whole NSX surface. v0.2 adds IP pools, DHCP configs and Tier-1 locale services;
# #58 adds Traceflow (config CRUD + restart) and its observations (the traced path).
_NSX_SERVICE_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "vcf.nsx.policy.api.v1.infra_client",
        (
            "Segments",
            "Tier0s",
            "Tier1s",
            "Services",
            "IpPools",
            "DhcpServerConfigs",
            "DhcpRelayConfigs",
            "Traceflows",
        ),
    ),
    (
        "vcf.nsx.policy.api.v1.infra.domains_client",
        ("Groups", "SecurityPolicies", "GatewayPolicies"),
    ),
    ("vcf.nsx.policy.api.v1.infra.tier_1s_client", ("LocaleServices",)),
    ("vcf.nsx.policy.api.v1.infra.traceflows_client", ("Observations",)),
)


def nsx_services() -> list[type]:
    """NSX Policy service classes exposed under ``vsc nsx``."""
    return _load_services("nsx", _NSX_SERVICE_SPECS)


def discover_all(*, read_only: bool = False) -> list[Operation]:
    """Discover every operation across both backends (writes included by default)."""
    ops: list[Operation] = []
    for cls in vsphere_services():
        ops.extend(discover_operations(cls, "vsphere", read_only=read_only))
    for cls in nsx_services():
        ops.extend(discover_operations(cls, "nsx", read_only=read_only))
    return ops
