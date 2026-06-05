"""Entry point: assemble and run the ``vsc`` Typer application.

The ``vsphere`` and ``nsx`` groups are generated at startup by introspecting the
installed ``vcf-sdk`` vAPI bindings (``vsc.gen``). Generation is offline, so
``--version`` and ``--help`` work without a server or credentials.
"""

from __future__ import annotations

import typer

from vsc import __version__
from vsc.cli.profiles import profiles_app
from vsc.cli.skill import skill_app
from vsc.connect.targets import connect_for_backend, set_active_profile
from vsc.gen.builder import build_group
from vsc.gen.complete import profile_completer
from vsc.gen.discover import (
    discover_operations,
    nsx_services,
    vsphere_services,
)
from vsc.logging_config import configure_logging
from vsc.pyvmomi.events import events_app
from vsc.pyvmomi.inventory import inventory_app
from vsc.pyvmomi.perf import perf_app
from vsc.pyvmomi.tasks import tasks_app


def _build_app() -> typer.Typer:
    configure_logging()
    app = typer.Typer(
        name="vsc",
        help="CLI for VMware Cloud Foundation 9 (vSphere + NSX), generated from the vcf-sdk.",
        no_args_is_help=True,
        add_completion=True,
    )

    # Reads and writes are both mounted; write commands are dry-run by default and
    # require --apply to execute (see vsc.gen.builder), so exposing them is safe.
    vsphere_ops = [
        op
        for cls in vsphere_services()
        for op in discover_operations(cls, "vsphere", read_only=False)
    ]
    nsx_ops = [
        op for cls in nsx_services() for op in discover_operations(cls, "nsx", read_only=False)
    ]

    # Generated vSphere commands, plus the curated pyVmomi fallback groups
    # (perf/…) mounted alongside them under the same `vsc vsphere` tree.
    vsphere_group = build_group(vsphere_ops, connect_for_backend)
    vsphere_group.add_typer(perf_app, name="perf")
    vsphere_group.add_typer(events_app, name="events")
    vsphere_group.add_typer(tasks_app, name="tasks")
    vsphere_group.add_typer(inventory_app, name="inventory")
    app.add_typer(
        vsphere_group,
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
    app.add_typer(profiles_app, name="profiles")
    app.add_typer(skill_app, name="skill")

    @app.callback()
    def main_callback(
        profile: str | None = typer.Option(
            None,
            "--profile",
            "-p",
            help="Named profile to use (overrides VSC_PROFILE and the config default).",
            autocompletion=profile_completer(),
        ),
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
        set_active_profile(profile)

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
