"""Pydantic models for the on-disk configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

BACKENDS = ("vsphere", "nsx")


class BackendCreds(BaseModel):
    """Connection details for one backend within a profile."""

    server: str
    username: str
    password: str | None = None  # None => look in the OS keyring
    insecure: bool = False
    # Optional path to a CA bundle used to verify the target's certificate.
    # Lets self-signed lab certs be pinned instead of disabling TLS entirely
    # (`insecure: true`). Ignored when `insecure` is set. Overridable via
    # VSC_<BACKEND>_CACERT.
    ca_bundle: str | None = None

    model_config = {"extra": "forbid"}


class Profile(BaseModel):
    """A named target environment (a vCenter and/or an NSX manager)."""

    vsphere: BackendCreds | None = None
    nsx: BackendCreds | None = None

    model_config = {"extra": "forbid"}

    def backend(self, name: str) -> BackendCreds | None:
        return getattr(self, name, None)


class Config(BaseModel):
    """The whole configuration file."""

    current_profile: str | None = None
    profiles: dict[str, Profile] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}
