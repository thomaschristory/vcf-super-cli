"""Resolve connection targets and hand out cached StubConfigurations.

Resolution order for each field: the active profile (file + keyring), then
environment-variable overrides (``VSC_<BACKEND>_*``), which always win. With no
config file at all, pure env-var operation still works.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from vmware.vapi.bindings.stub import StubConfiguration

from vsc.config.schema import BackendCreds
from vsc.config.store import keyring_get, load_config
from vsc.connect.session import connect_nsx, connect_vsphere

_TRUTHY = {"1", "true", "yes", "on"}

# Process-wide active profile override set by the global --profile option.
# Held in a dict to avoid a module-level `global` statement.
_state: dict[str, str | None] = {"profile": None}


class TargetNotConfigured(Exception):
    """A backend was invoked without the credentials needed to reach it."""


@dataclass(frozen=True)
class Target:
    """Resolved connection details for one backend."""

    server: str
    username: str
    password: str
    verify: bool


def set_active_profile(name: str | None) -> None:
    """Set the profile selected via ``--profile`` for this process."""
    _state["profile"] = name


def active_profile_name() -> str | None:
    """The effective profile name: --profile, then VSC_PROFILE, then config."""
    if _state["profile"]:
        return _state["profile"]
    env = os.environ.get("VSC_PROFILE")
    if env:
        return env
    return load_config().current_profile


def _profile_creds(backend: str) -> tuple[BackendCreds | None, str | None]:
    name = active_profile_name()
    if not name:
        return None, None
    profile = load_config().profiles.get(name)
    if profile is None:
        return None, name
    return profile.backend(backend), name


def resolve_target(backend: str) -> Target:
    """Resolve a :class:`Target` from profile + env overrides for ``backend``."""
    creds, profile_name = _profile_creds(backend)
    server = creds.server if creds else None
    username = creds.username if creds else None
    password = creds.password if creds else None
    insecure = creds.insecure if creds else False
    if creds and password is None and profile_name:
        password = keyring_get(profile_name, backend)

    prefix = f"VSC_{backend.upper()}"
    server = os.environ.get(f"{prefix}_SERVER", server or "") or None
    username = os.environ.get(f"{prefix}_USERNAME", username or "") or None
    password = os.environ.get(f"{prefix}_PASSWORD", password or "") or None
    env_insecure = os.environ.get(f"{prefix}_INSECURE")
    if env_insecure is not None:
        insecure = env_insecure.strip().lower() in _TRUTHY

    missing = [
        field
        for field, val in (("server", server), ("username", username), ("password", password))
        if not val
    ]
    if missing:
        hint = (
            f"profile {active_profile_name()!r}" if active_profile_name() else "no active profile"
        )
        raise TargetNotConfigured(
            f"{backend}: missing {', '.join(missing)} ({hint}; "
            f"set {prefix}_* env vars or run `vsc profiles add`)"
        )
    assert server and username and password
    return Target(server=server, username=username, password=password, verify=not insecure)


_CACHE: dict[str, StubConfiguration] = {}


def connect_for_backend(backend: str) -> StubConfiguration:
    """Return an authenticated StubConfiguration for ``backend`` (cached)."""
    cached = _CACHE.get(backend)
    if cached is not None:
        return cached
    target = resolve_target(backend)
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
