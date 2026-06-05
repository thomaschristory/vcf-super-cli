"""Profile config: schema, store, resolution precedence, and CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vsc.cli.app import app
from vsc.config.schema import BackendCreds, Config, Profile
from vsc.config.store import load_config, save_config
from vsc.connect import targets

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setenv("VSC_CONFIG_FILE", str(cfg_file))
    for var in list(os.environ):
        if var.startswith("VSC_") and var != "VSC_CONFIG_FILE":
            monkeypatch.delenv(var, raising=False)
    targets.set_active_profile(None)
    targets.reset_cache()
    return cfg_file


def test_save_and_load_roundtrip() -> None:
    cfg = Config(
        current_profile="prod",
        profiles={
            "prod": Profile(
                vsphere=BackendCreds(server="vc.example", username="admin", insecure=True)
            )
        },
    )
    save_config(cfg)
    loaded = load_config()
    assert loaded.current_profile == "prod"
    assert loaded.profiles["prod"].vsphere is not None
    assert loaded.profiles["prod"].vsphere.server == "vc.example"


def test_save_sets_restrictive_permissions(isolated_config: Path) -> None:
    save_config(Config(current_profile="x", profiles={"x": Profile()}))
    assert (isolated_config.stat().st_mode & 0o777) == 0o600


def test_resolve_target_prefers_env_over_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    save_config(
        Config(
            current_profile="prod",
            profiles={
                "prod": Profile(
                    vsphere=BackendCreds(server="profile-host", username="puser", password="ppw")
                )
            },
        )
    )
    monkeypatch.setenv("VSC_VSPHERE_SERVER", "env-host")
    target = targets.resolve_target("vsphere")
    assert target.server == "env-host"  # env overrides profile
    assert target.username == "puser"  # falls back to profile


def test_resolve_target_uses_keyring_when_password_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    save_config(
        Config(
            current_profile="prod",
            profiles={"prod": Profile(vsphere=BackendCreds(server="h", username="u"))},
        )
    )
    monkeypatch.setattr(targets, "keyring_get", lambda profile, backend: "from-keyring")
    target = targets.resolve_target("vsphere")
    assert target.password == "from-keyring"


def test_resolve_target_raises_when_unconfigured() -> None:
    with pytest.raises(targets.TargetNotConfigured):
        targets.resolve_target("vsphere")


def test_profiles_add_list_show_use_delete() -> None:
    add = runner.invoke(
        app,
        [
            "profiles",
            "add",
            "prod",
            "--vsphere-server",
            "vc.example",
            "--vsphere-username",
            "admin",
            "--vsphere-password",
            "secret",
            "--store-in-file",
        ],
    )
    assert add.exit_code == 0, add.stdout
    assert json.loads(add.stdout)["current"] == "prod"

    listed = runner.invoke(app, ["profiles", "list"])
    assert json.loads(listed.stdout) == {"current": "prod", "profiles": ["prod"]}

    shown = runner.invoke(app, ["profiles", "show", "prod"])
    body = json.loads(shown.stdout)
    assert body["vsphere"]["server"] == "vc.example"
    assert "secret" not in shown.stdout  # password never printed

    deleted = runner.invoke(app, ["profiles", "delete", "prod"])
    assert deleted.exit_code == 0
    assert json.loads(deleted.stdout)["current"] is None


def test_profiles_show_missing_is_not_found() -> None:
    result = runner.invoke(app, ["profiles", "show", "ghost"])
    assert result.exit_code == 4  # ExitCode.NOT_FOUND
