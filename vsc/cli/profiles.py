"""Curated (non-generated) commands for managing named profiles."""

from __future__ import annotations

import typer

from vsc.config.schema import BACKENDS, BackendCreds, Profile
from vsc.config.store import (
    keyring_delete,
    keyring_set,
    load_config,
    save_config,
)
from vsc.output.exit_codes import ExitCode
from vsc.output.render import to_json

profiles_app = typer.Typer(no_args_is_help=True, help="Manage named connection profiles.")


def _print(data: object) -> None:
    print(to_json(data))


def _store_password(profile: str, backend: str, password: str, store_in_file: bool) -> str | None:
    """Persist a password. Returns the value to keep in the file (None if keyring)."""
    if store_in_file:
        return password
    if keyring_set(profile, backend, password):
        return None
    typer.echo(
        f"No usable OS keyring backend; re-run with --store-in-file to save the "
        f"{backend} password in the config file (mode 0600).",
        err=True,
    )
    raise typer.Exit(int(ExitCode.CONFIG))


def _make_creds(
    profile: str,
    backend: str,
    server: str | None,
    username: str | None,
    password: str | None,
    insecure: bool,
    store_in_file: bool,
) -> BackendCreds | None:
    if not server and not username and not password:
        return None
    if not server or not username:
        typer.echo(
            f"{backend}: both --{backend}-server and --{backend}-username are required.", err=True
        )
        raise typer.Exit(int(ExitCode.USAGE))
    stored = _store_password(profile, backend, password, store_in_file) if password else None
    return BackendCreds(server=server, username=username, password=stored, insecure=insecure)


@profiles_app.command("add")
def add(
    name: str = typer.Argument(..., help="Profile name."),
    vsphere_server: str | None = typer.Option(None, "--vsphere-server"),
    vsphere_username: str | None = typer.Option(None, "--vsphere-username"),
    vsphere_password: str | None = typer.Option(None, "--vsphere-password", hide_input=True),
    vsphere_insecure: bool = typer.Option(False, "--vsphere-insecure/--vsphere-verify"),
    nsx_server: str | None = typer.Option(None, "--nsx-server"),
    nsx_username: str | None = typer.Option(None, "--nsx-username"),
    nsx_password: str | None = typer.Option(None, "--nsx-password", hide_input=True),
    nsx_insecure: bool = typer.Option(False, "--nsx-insecure/--nsx-verify"),
    store_in_file: bool = typer.Option(
        False, "--store-in-file", help="Store passwords in the config file instead of the keyring."
    ),
    use: bool = typer.Option(False, "--use/--no-use", help="Make this the current profile."),
) -> None:
    """Create or update a profile (passwords go to the OS keyring by default)."""
    config = load_config()
    profile = Profile(
        vsphere=_make_creds(
            name,
            "vsphere",
            vsphere_server,
            vsphere_username,
            vsphere_password,
            vsphere_insecure,
            store_in_file,
        ),
        nsx=_make_creds(
            name, "nsx", nsx_server, nsx_username, nsx_password, nsx_insecure, store_in_file
        ),
    )
    config.profiles[name] = profile
    if use or config.current_profile is None:
        config.current_profile = name
    path = save_config(config)
    _print({"saved": name, "current": config.current_profile, "path": str(path)})


@profiles_app.command("list")
def list_profiles() -> None:
    """List configured profiles."""
    config = load_config()
    _print(
        {
            "current": config.current_profile,
            "profiles": sorted(config.profiles),
        }
    )


@profiles_app.command("show")
def show(name: str = typer.Argument(..., help="Profile name.")) -> None:
    """Show a profile (passwords are never printed)."""
    config = load_config()
    profile = config.profiles.get(name)
    if profile is None:
        typer.echo(f"No such profile: {name}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    out: dict[str, object] = {"name": name, "current": config.current_profile == name}
    for backend in BACKENDS:
        creds = profile.backend(backend)
        if creds is not None:
            out[backend] = {
                "server": creds.server,
                "username": creds.username,
                "password": "set-in-file" if creds.password else "keyring-or-env",
                "insecure": creds.insecure,
            }
    _print(out)


@profiles_app.command("use")
def use(name: str = typer.Argument(..., help="Profile name.")) -> None:
    """Set the current (default) profile."""
    config = load_config()
    if name not in config.profiles:
        typer.echo(f"No such profile: {name}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    config.current_profile = name
    save_config(config)
    _print({"current": name})


@profiles_app.command("delete")
def delete(name: str = typer.Argument(..., help="Profile name.")) -> None:
    """Delete a profile and its keyring entries."""
    config = load_config()
    if name not in config.profiles:
        typer.echo(f"No such profile: {name}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    del config.profiles[name]
    for backend in BACKENDS:
        keyring_delete(name, backend)
    if config.current_profile == name:
        config.current_profile = next(iter(config.profiles), None)
    save_config(config)
    _print({"deleted": name, "current": config.current_profile})


@profiles_app.command("set-password")
def set_password(
    name: str = typer.Argument(..., help="Profile name."),
    backend: str = typer.Argument(..., help="vsphere or nsx."),
    password: str = typer.Option(..., "--password", prompt=True, hide_input=True),
    store_in_file: bool = typer.Option(False, "--store-in-file"),
) -> None:
    """Set/replace the password for a profile backend."""
    if backend not in BACKENDS:
        typer.echo(f"backend must be one of {BACKENDS}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    config = load_config()
    profile = config.profiles.get(name)
    if profile is None or profile.backend(backend) is None:
        typer.echo(f"No {backend} config in profile {name!r}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    stored = _store_password(name, backend, password, store_in_file)
    creds = profile.backend(backend)
    assert creds is not None
    creds.password = stored
    config.profiles[name] = profile
    save_config(config)
    _print({"updated": name, "backend": backend, "in_file": stored is not None})
