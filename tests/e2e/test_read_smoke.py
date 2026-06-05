"""Live read smoke tests against a real vCenter / NSX (gated; see conftest)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from vsc.cli.app import app
from vsc.connect import targets

runner = CliRunner()


def _run(args: list[str]) -> tuple[int, object]:
    targets.reset_cache()
    result = runner.invoke(app, args)
    payload: object
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    return result.exit_code, payload


def test_vsphere_vm_list(require_vsphere: None) -> None:
    code, payload = _run(["vsphere", "vm", "list"])
    assert code == 0
    assert isinstance(payload, list)


def test_vsphere_host_list(require_vsphere: None) -> None:
    code, payload = _run(["vsphere", "host", "list"])
    assert code == 0
    assert isinstance(payload, list)


def test_nsx_segments_list(require_nsx: None) -> None:
    code, payload = _run(["nsx", "segments", "list"])
    assert code == 0
    # NSX Policy list responses are typically wrapped objects with "results".
    assert payload is not None
