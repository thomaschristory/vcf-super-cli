"""Gating for the live end-to-end suite.

These tests talk to a real vCenter/NSX. They are excluded from the default run
(``--ignore=tests/e2e`` in pyproject) and, even when targeted explicitly, are
skipped unless ``VSC_E2E`` is truthy and the relevant backend credentials are set.

Run them with, e.g.::

    VSC_E2E=1 VSC_VSPHERE_SERVER=... VSC_VSPHERE_USERNAME=... \
        VSC_VSPHERE_PASSWORD=... uv run pytest tests/e2e -v
"""

from __future__ import annotations

import os

import pytest

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _truthy(os.environ.get("VSC_E2E")):
        return
    skip = pytest.mark.skip(reason="live e2e: set VSC_E2E=1 (and backend creds) to run")
    for item in items:
        item.add_marker(skip)


def backend_configured(backend: str) -> bool:
    prefix = f"VSC_{backend.upper()}"
    return all(os.environ.get(f"{prefix}_{field}") for field in ("SERVER", "USERNAME", "PASSWORD"))


@pytest.fixture
def require_vsphere() -> None:
    if not backend_configured("vsphere"):
        pytest.skip("vSphere creds not set (VSC_VSPHERE_SERVER/USERNAME/PASSWORD)")


@pytest.fixture
def require_nsx() -> None:
    if not backend_configured("nsx"):
        pytest.skip("NSX creds not set (VSC_NSX_SERVER/USERNAME/PASSWORD)")
