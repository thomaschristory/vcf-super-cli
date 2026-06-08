"""``vsc vsphere inventory vm|host`` — property walk via the pyVmomi PropertyCollector.

Fetches arbitrary managed-object properties (device trees, custom attributes,
relationships) that the REST list ops omit. ``--props`` selects specific property
paths (repeatable); without it a small per-type default summary is returned.
"""

from __future__ import annotations

from typing import Any

import typer
from pyVmomi import vim, vmodl

from vsc.connect.vmomi import vmomi_jsonable
from vsc.gen.complete import output_format_completer
from vsc.output.render import OutputFormat
from vsc.pyvmomi.find import Criteria, find_matches, validate_criteria
from vsc.pyvmomi.runner import run_read

inventory_app = typer.Typer(no_args_is_help=True, help="Property walk (pyVmomi fallback).")

# Modest per-type defaults when the caller names no property paths. Retrieving
# *all* properties can be very large, so we never default to that.
_DEFAULT_PROPS: dict[str, list[str]] = {
    "vm": ["name", "runtime.powerState", "config.hardware.numCPU", "config.hardware.memoryMB"],
    "host": ["name", "runtime.connectionState", "runtime.powerState"],
}


def retrieve_properties(
    property_collector: Any, entity: Any, props: list[str]
) -> list[dict[str, Any]]:
    """Retrieve ``props`` for ``entity`` and shape the result as JSON-able dicts."""
    pc = vmodl.query.PropertyCollector
    prop_spec = pc.PropertySpec(type=type(entity), pathSet=props, all=not props)
    obj_spec = pc.ObjectSpec(obj=entity)
    filter_spec = pc.FilterSpec(propSet=[prop_spec], objectSet=[obj_spec])

    contents = property_collector.RetrieveContents(specSet=[filter_spec]) or []
    return [
        {
            "obj": vmomi_jsonable(content.obj),
            "properties": {dp.name: vmomi_jsonable(dp.val) for dp in (content.propSet or [])},
        }
        for content in contents
    ]


def _run(moid: str, kind: str, props: list[str], fmt: str) -> None:
    cls = vim.VirtualMachine if kind == "vm" else vim.HostSystem

    def build(si: Any) -> list[dict[str, Any]]:
        entity = cls(moid, si._stub)
        return retrieve_properties(si.content.propertyCollector, entity, props)

    run_read(fmt, build)


_PROPS_HELP = "Property path (repeatable), e.g. config.hardware. Defaults to a summary set."


@inventory_app.command("vm")
def inventory_vm(
    vm: str = typer.Argument(..., help="VM managed-object id, e.g. vm-101."),
    props: list[str] = typer.Option(None, "--props", help=_PROPS_HELP),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """Retrieve properties of a virtual machine."""
    _run(vm, "vm", props or _DEFAULT_PROPS["vm"], output.value)


@inventory_app.command("host")
def inventory_host(
    host: str = typer.Argument(..., help="Host managed-object id, e.g. host-12."),
    props: list[str] = typer.Option(None, "--props", help=_PROPS_HELP),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """Retrieve properties of an ESXi host."""
    _run(host, "host", props or _DEFAULT_PROPS["host"], output.value)


_FIND_PROPS_HELP = "Extra property to surface per hit (repeatable). Output only — never matches."


@inventory_app.command("find")
def inventory_find(
    ip: list[str] = typer.Option(
        None, "--ip", help="Guest IP, exact or CIDR (e.g. 10.20.3.41 or 10.20.3.0/24). Repeatable."
    ),
    name: list[str] = typer.Option(
        None, "--name", help="VM name, substring or glob (case-insensitive). Repeatable."
    ),
    hostname: list[str] = typer.Option(
        None, "--hostname", help="Guest hostname, substring or glob. Repeatable."
    ),
    mac: list[str] = typer.Option(
        None, "--mac", help="NIC MAC address, exact (case-insensitive). Repeatable."
    ),
    guest_os: list[str] = typer.Option(
        None, "--guest-os", help="Guest OS name, substring or glob. Repeatable."
    ),
    power_state: list[str] = typer.Option(
        None, "--power-state", help="poweredOn | poweredOff | suspended. Repeatable."
    ),
    props: list[str] = typer.Option(None, "--props", help=_FIND_PROPS_HELP),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """Find VMs by guest/runtime attribute, without knowing the moid.

    Flags AND together; repeat a flag to OR within that field. At least one match
    flag is required (--props/-o alone do not count). Powered-off VMs and those
    without VMware Tools report no guest IP and won't match --ip.
    """

    def build(si: Any) -> list[dict[str, Any]]:
        criteria = Criteria(
            ip=tuple(ip or ()),
            name=tuple(name or ()),
            hostname=tuple(hostname or ()),
            mac=tuple(mac or ()),
            guest_os=tuple(guest_os or ()),
            power_state=tuple(power_state or ()),
        )
        if criteria.is_empty:
            raise ValueError(
                "give at least one match flag "
                "(--ip/--name/--hostname/--mac/--guest-os/--power-state)"
            )
        validate_criteria(criteria)
        return find_matches(si, criteria, props or [])

    run_read(output.value, build)
