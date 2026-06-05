"""Entry point: assemble and run the ``vsc`` Typer application.

Bootstrap scaffold. The dynamic command tree (introspected from the ``vcf-sdk``
vAPI bindings) is built by ``vsc.gen`` and mounted under the ``vsphere`` and
``nsx`` groups — tracked as separate issues. For now those groups exist as
placeholders so the CLI shape, ``--version``, and ``--help`` are real.
"""

from __future__ import annotations

import typer

from vsc import __version__

app = typer.Typer(
    name="vsc",
    help="Modern CLI for VMware Cloud Foundation 9 (vSphere + NSX), generated from the vcf-sdk.",
    no_args_is_help=True,
    add_completion=True,
)

vsphere_app = typer.Typer(
    help="vSphere / vCenter commands (generated from vmware-vcenter).",
    no_args_is_help=True,
)
nsx_app = typer.Typer(
    help="NSX commands (generated from the vcf-nsx Policy API).",
    no_args_is_help=True,
)

app.add_typer(vsphere_app, name="vsphere")
app.add_typer(nsx_app, name="nsx")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
