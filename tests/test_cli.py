"""End-to-end CLI shape tests (offline)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from vsc import __version__
from vsc.cli.app import app
from vsc.connect import targets
from vsc.output.exit_codes import ExitCode

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_product_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "vsphere" in result.stdout
    assert "nsx" in result.stdout


@pytest.mark.parametrize(
    "path",
    [
        ["vsphere", "--help"],
        ["vsphere", "vm", "--help"],
        ["vsphere", "vm", "list", "--help"],
        ["vsphere", "vm", "get", "--help"],
        ["nsx", "--help"],
        ["nsx", "segments", "--help"],
    ],
)
def test_generated_help_is_clean(path: list[str]) -> None:
    result = runner.invoke(app, path)
    assert result.exit_code == 0, result.stdout


def test_missing_credentials_yields_config_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "VSC_VSPHERE_SERVER",
        "VSC_VSPHERE_USERNAME",
        "VSC_VSPHERE_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    targets.reset_cache()

    result = runner.invoke(app, ["vsphere", "vm", "get", "vm-1"])
    assert result.exit_code == int(ExitCode.CONFIG)
    envelope = json.loads(result.stderr)
    assert envelope["error"]["kind"] == "TargetNotConfigured"
