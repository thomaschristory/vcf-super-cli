"""Entry point: assemble and run the ``vsc`` Typer application.

The ``vsphere`` and ``nsx`` groups are generated at startup by introspecting the
installed ``vcf-sdk`` vAPI bindings (``vsc.gen``). Generation is offline, so
``--version`` and ``--help`` work without a server or credentials.
"""

from __future__ import annotations

import typer

from vsc import __version__
from vsc.connect.targets import connect_for_backend
from vsc.gen.builder import build_group
from vsc.gen.discover import (
    discover_operations,
    nsx_services,
    vsphere_services,
)


def _build_app() -> typer.Typer:
    app = typer.Typer(
        name="vsc",
        help="CLI for VMware Cloud Foundation 9 (vSphere + NSX), generated from the vcf-sdk.",
        no_args_is_help=True,
        add_completion=True,
    )

    vsphere_ops = [op for cls in vsphere_services() for op in discover_operations(cls, "vsphere")]
    nsx_ops = [op for cls in nsx_services() for op in discover_operations(cls, "nsx")]

    app.add_typer(
        build_group(vsphere_ops, connect_for_backend),
        name="vsphere",
        help="vSphere / vCenter commands (generated from vmware-vcenter).",
        no_args_is_help=True,
    )
    app.add_typer(
        build_group(nsx_ops, connect_for_backend),
        name="nsx",
        help="NSX Policy commands (generated from vcf-nsx).",
        no_args_is_help=True,
    )

    @app.callback()
    def main_callback(
        _version: bool = typer.Option(
            False,
            "--version",
            "-V",
            help="Show the vsc version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ) -> None:
        """Global options for ``vsc``."""

    return app


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


app = _build_app()


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
