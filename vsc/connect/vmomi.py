"""pyVmomi (SOAP) connection + a JSON adapter for its object graph.

The vAPI/REST surface (``vsc.connect.session``) covers most of v0.1/v0.2, but a few
inventory/perf areas are only reachable through the older pyVmomi SOAP API. This
module authenticates with ``SmartConnect`` — reusing the same resolved vSphere
credentials as the REST path — and converts the returned managed/data objects into
plain JSON-able structures so the curated pyVmomi commands emit through the same
output contract as everything else.
"""

from __future__ import annotations

import atexit
import contextlib
import datetime as _dt
import ssl
from typing import Any

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim, vmodl

from vsc.connect.targets import resolve_target

# Process-wide cache, mirroring vsc.connect.targets for the vAPI path.
_SI: dict[str, Any] = {}

# DataObject bookkeeping fields that are always noise in our output.
_SKIP_PROPS = frozenset({"dynamicType", "dynamicProperty"})


def _ssl_context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        # Mirrors the REST path (vsc.connect.session): only when the profile/env
        # explicitly opts into insecure (self-signed lab certs).
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def connect_vmomi() -> Any:
    """Return an authenticated pyVmomi ``ServiceInstance`` for vSphere (cached)."""
    cached = _SI.get("vsphere")
    if cached is not None:
        return cached
    target = resolve_target("vsphere")
    si = SmartConnect(
        host=target.server,
        user=target.username,
        pwd=target.password,
        sslContext=_ssl_context(target.verify),
    )
    _SI["vsphere"] = si
    return si


def reset_vmomi_cache() -> None:
    """Disconnect and drop cached ServiceInstances (tests, re-auth, atexit)."""
    for si in _SI.values():
        with contextlib.suppress(Exception):  # best-effort teardown
            Disconnect(si)
    _SI.clear()


# Sessions are best-effort closed at interpreter exit; on an empty cache this is a
# no-op, so registering unconditionally at import is safe and avoids a global flag.
atexit.register(reset_vmomi_cache)


def vmomi_jsonable(obj: Any) -> Any:
    """Convert a pyVmomi object graph into JSON-able Python values.

    Managed objects collapse to ``{"type", "value"}`` (their moref); data objects
    become dicts of their set properties; lists/datetimes/scalars are handled
    structurally. Unset properties and bookkeeping fields are dropped.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [vmomi_jsonable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): vmomi_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, vim.ManagedObject):
        type_name = getattr(obj, "_wsdlName", None) or type(obj).__name__.rsplit(".", 1)[-1]
        return {"type": type_name, "value": obj._moId}
    if isinstance(obj, vmodl.DynamicData):
        result: dict[str, Any] = {}
        for prop in obj._GetPropertyList():
            if prop.name in _SKIP_PROPS:
                continue
            value = getattr(obj, prop.name, None)
            if value is None:
                continue
            # Skip empty collections without `== []` — equality on a managed-object
            # value would dereference a missing ``_moId`` and raise.
            if isinstance(value, (list, tuple)) and not value:
                continue
            result[prop.name] = vmomi_jsonable(value)
        return result
    return str(obj)
