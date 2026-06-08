"""Find VMs by guest/runtime attribute (IP, name, hostname, MAC, guest OS, power).

The REST ``VM.FilterSpec`` exposes none of the guest-network fields, so "which VM
has ``10.20.3.41``?" is unanswerable there. Those fields only live on the pyVmomi
``guest.*`` properties, so this is a single ``PropertyCollector`` sweep over every
VM (one round-trip via a container view) plus a **pure matcher** that decides which
hits to keep. The matcher takes a plain props dict — no pyVmomi — so it unit-tests
in isolation; only :func:`find_matches` touches SOAP.
"""

from __future__ import annotations

import fnmatch
import ipaddress
from dataclasses import dataclass
from typing import Any

from pyVmomi import vim, vmodl

from vsc.connect.vmomi import vmomi_jsonable

# Fixed property paths the matcher inspects, retrieved for every VM. ``--props``
# paths are appended to this set (output only) — never a match criterion.
SEARCH_PATHS: tuple[str, ...] = (
    "name",
    "runtime.powerState",
    "guest.ipAddress",
    "guest.net",
    "guest.hostName",
    "guest.guestFullName",
)
POWER_STATES = frozenset({"poweredOn", "poweredOff", "suspended"})
_GLOB_CHARS = frozenset("*?[")


@dataclass(frozen=True)
class Criteria:
    """One value per match flag; repeated flags arrive as multiple entries.

    Fields **AND** together (every non-empty field must match); values within a
    field **OR** (any one is enough). ``--props``/``-o`` are not represented here —
    they never participate in matching.
    """

    ip: tuple[str, ...] = ()
    name: tuple[str, ...] = ()
    hostname: tuple[str, ...] = ()
    mac: tuple[str, ...] = ()
    guest_os: tuple[str, ...] = ()
    power_state: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when no match flag was given (we refuse to dump the whole inventory)."""
        return not (
            self.ip or self.name or self.hostname or self.mac or self.guest_os or self.power_state
        )


def validate_criteria(criteria: Criteria) -> None:
    """Raise ``ValueError`` for malformed input so it surfaces as a usage error."""
    for value in criteria.ip:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid --ip {value!r} (expected an address or CIDR)") from exc
    bad = [state for state in criteria.power_state if state not in POWER_STATES]
    if bad:
        allowed = ", ".join(sorted(POWER_STATES))
        raise ValueError(f"invalid --power-state {bad[0]!r} (one of: {allowed})")


def _addresses(props: dict[str, Any]) -> list[str]:
    """All guest IPs: the primary ``guest.ipAddress`` plus every NIC address, deduped."""
    out: list[str] = []
    primary = props.get("guest.ipAddress")
    if isinstance(primary, str):
        out.append(primary)
    for nic in props.get("guest.net") or []:
        for addr in (nic.get("ipAddress") if isinstance(nic, dict) else None) or []:
            if isinstance(addr, str):
                out.append(addr)
    # Preserve order, drop duplicates (primary often repeats a NIC address).
    return list(dict.fromkeys(out))


def _macs(props: dict[str, Any]) -> list[str]:
    """MAC addresses across every NIC in ``guest.net``."""
    return [
        nic["macAddress"]
        for nic in props.get("guest.net") or []
        if isinstance(nic, dict) and isinstance(nic.get("macAddress"), str)
    ]


def _text_match(value: Any, pattern: str) -> bool:
    """Case-insensitive substring match, or glob when the pattern has metachars."""
    if not isinstance(value, str):
        return False
    haystack, needle = value.lower(), pattern.lower()
    if _GLOB_CHARS & set(needle):
        return fnmatch.fnmatchcase(haystack, needle)
    return needle in haystack


def _ip_match(addresses: list[str], pattern: str) -> bool:
    """True if any guest address falls within ``pattern`` (exact IP or CIDR)."""
    try:
        network = ipaddress.ip_network(pattern, strict=False)
    except ValueError:
        return False
    for addr in addresses:
        try:
            if ipaddress.ip_address(addr) in network:
                return True
        except ValueError:
            continue  # zone-scoped/garbage guest address — skip, don't crash
    return False


def _mac_match(props: dict[str, Any], wanted: tuple[str, ...]) -> bool:
    have = {mac.lower() for mac in _macs(props)}
    return any(p.lower() in have for p in wanted)


def matches(props: dict[str, Any], criteria: Criteria) -> bool:
    """Decide whether one VM's properties satisfy every criterion (AND of ORs).

    Each field that was given must match at least one of its values; a field left
    unset imposes no constraint. ``all`` over the per-field results yields the AND.
    """
    return all(
        (
            not criteria.power_state or props.get("runtime.powerState") in criteria.power_state,
            not criteria.name or any(_text_match(props.get("name"), p) for p in criteria.name),
            not criteria.hostname
            or any(_text_match(props.get("guest.hostName"), p) for p in criteria.hostname),
            not criteria.guest_os
            or any(_text_match(props.get("guest.guestFullName"), p) for p in criteria.guest_os),
            not criteria.mac or _mac_match(props, criteria.mac),
            not criteria.ip or any(_ip_match(_addresses(props), p) for p in criteria.ip),
        )
    )


def summarize(obj: Any, props: dict[str, Any], extra_props: list[str]) -> dict[str, Any]:
    """Shape one matched VM into a directly-useful summary (pipes into ``vm get``)."""
    hit: dict[str, Any] = {
        "obj": obj,
        "name": props.get("name"),
        "power_state": props.get("runtime.powerState"),
        "ip_addresses": _addresses(props),
        "hostname": props.get("guest.hostName"),
        "guest_os": props.get("guest.guestFullName"),
    }
    if extra_props:
        hit["properties"] = {path: props.get(path) for path in extra_props}
    return hit


def _retrieve_all_vms(si: Any, paths: list[str]) -> list[Any]:
    """One ``RetrieveContents`` over every VM via a container view (destroyed after)."""
    content = si.content
    view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    try:
        pc = vmodl.query.PropertyCollector
        traversal = pc.TraversalSpec(
            name="toVm", type=vim.view.ContainerView, path="view", skip=False
        )
        obj_spec = pc.ObjectSpec(obj=view, skip=True, selectSet=[traversal])
        prop_spec = pc.PropertySpec(type=vim.VirtualMachine, pathSet=paths, all=False)
        filter_spec = pc.FilterSpec(objectSet=[obj_spec], propSet=[prop_spec])
        return content.propertyCollector.RetrieveContents(specSet=[filter_spec]) or []
    finally:
        view.Destroy()


def find_matches(si: Any, criteria: Criteria, extra_props: list[str]) -> list[dict[str, Any]]:
    """Sweep all VMs once, keep those satisfying ``criteria``, shape each hit."""
    # Fixed search paths first, then any output-only --props (deduped, order kept).
    paths = list(dict.fromkeys([*SEARCH_PATHS, *extra_props]))
    out: list[dict[str, Any]] = []
    for content in _retrieve_all_vms(si, paths):
        props = {dp.name: vmomi_jsonable(dp.val) for dp in (content.propSet or [])}
        if matches(props, criteria):
            out.append(summarize(vmomi_jsonable(content.obj), props, extra_props))
    return out
