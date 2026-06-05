"""Smoke tests for the bootstrap CLI shape."""

from __future__ import annotations

from typer.testing import CliRunner

from vsc import __version__
from vsc.cli.app import app

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
