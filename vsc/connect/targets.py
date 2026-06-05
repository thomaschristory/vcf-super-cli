"""Resolve connection targets and hand out cached StubConfigurations.

For v0.1, targets come from environment variables. The named-profile config layer
(issue #6) plugs in here later by providing a resolver; env vars keep working as
overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from vmware.vapi.bindings.stub import StubConfiguration

from vsc.connect.session import connect_nsx, connect_vsphere

_TRUTHY = {"1", "true", "yes", "on"}


class TargetNotConfigured(Exception):
    """A backend was invoked without the credentials needed to reach it."""


@dataclass(frozen=True)
class Target:
    """Resolved connection details for one backend."""

    server: str
    username: str
    password: str
    verify: bool


def _env_target(backend: str) -> Target:
    prefix = f"VSC_{backend.upper()}"
    server = os.environ.get(f"{prefix}_SERVER")
    username = os.environ.get(f"{prefix}_USERNAME")
    password = os.environ.get(f"{prefix}_PASSWORD")
    missing = [
        name
        for name, val in (
            (f"{prefix}_SERVER", server),
            (f"{prefix}_USERNAME", username),
            (f"{prefix}_PASSWORD", password),
        )
        if not val
    ]
    if missing:
        raise TargetNotConfigured(
            f"{backend}: missing {', '.join(missing)} (set these env vars or configure a profile)"
        )
    insecure = os.environ.get(f"{prefix}_INSECURE", "").strip().lower() in _TRUTHY
    assert server and username and password  # narrowed by the missing check above
    return Target(server=server, username=username, password=password, verify=not insecure)


_CACHE: dict[str, StubConfiguration] = {}


def connect_for_backend(backend: str) -> StubConfiguration:
    """Return an authenticated StubConfiguration for ``backend`` (cached)."""
    cached = _CACHE.get(backend)
    if cached is not None:
        return cached
    target = _env_target(backend)
    if backend == "vsphere":
        cfg = connect_vsphere(target.server, target.username, target.password, verify=target.verify)
    elif backend == "nsx":
        cfg = connect_nsx(target.server, target.username, target.password, verify=target.verify)
    else:  # pragma: no cover - guarded by the generator's backend values
        raise TargetNotConfigured(f"unknown backend {backend!r}")
    _CACHE[backend] = cfg
    return cfg


def reset_cache() -> None:
    """Drop cached connections (used by tests and re-auth)."""
    _CACHE.clear()
