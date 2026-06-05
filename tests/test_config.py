"""Profile config: schema, store, resolution precedence, and CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vsc.cli import profiles as profiles_cli
from vsc.cli.app import app
from vsc.config.schema import BackendCreds, Config, Profile
from vsc.config.store import ConfigError, load_config, save_config
from vsc.connect import targets
from vsc.output.exit_codes import ExitCode

runner = CliRunner()


def _profile(server: str, password: str | None = None, insecure: bool = False) -> Config:
    return Config(
        current_profile="prod",
        profiles={
            "prod": Profile(
                vsphere=BackendCreds(
                    server=server, username="u", password=password, insecure=insecure
                )
            )
        },
    )


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


# --------------------------------------------------------------------------- #
# Review fixes
# --------------------------------------------------------------------------- #


def test_save_is_atomic_0600_even_with_permissive_umask(isolated_config: Path) -> None:
    old = os.umask(0o000)
    try:
        save_config(_profile("h", password="secret"))
    finally:
        os.umask(old)
    assert (isolated_config.stat().st_mode & 0o777) == 0o600


def test_save_tightens_preexisting_loose_file(isolated_config: Path) -> None:
    isolated_config.write_text("current_profile: x\nprofiles: {}\n")
    isolated_config.chmod(0o644)
    save_config(_profile("h", password="secret"))
    assert (isolated_config.stat().st_mode & 0o777) == 0o600


def test_malformed_config_raises_config_error(isolated_config: Path) -> None:
    isolated_config.write_text("garbage_key: true\n")
    with pytest.raises(ConfigError):
        load_config()


def test_malformed_config_profiles_list_clean_exit(isolated_config: Path) -> None:
    isolated_config.write_text("- not\n- a\n- mapping\n")
    result = runner.invoke(app, ["profiles", "list"])
    assert result.exit_code == int(ExitCode.CONFIG)
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_malformed_config_generated_command_clean_exit(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_config.write_text("garbage_key: true\n")
    monkeypatch.setenv("VSC_VSPHERE_SERVER", "h")
    monkeypatch.setenv("VSC_VSPHERE_USERNAME", "u")
    monkeypatch.setenv("VSC_VSPHERE_PASSWORD", "p")
    targets.reset_cache()
    result = runner.invoke(app, ["vsphere", "vm", "get", "vm-1"])
    assert result.exit_code == int(ExitCode.CONFIG)
    assert json.loads(result.stderr)["error"]["kind"] == "ConfigError"


@pytest.mark.parametrize(
    ("value", "expected_verify"),
    [("yes", False), ("false", True), ("", False)],  # empty string is NOT an override
)
def test_env_insecure_precedence(
    value: str, expected_verify: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_config(_profile("h", password="p", insecure=True))  # profile wants insecure
    monkeypatch.setenv("VSC_VSPHERE_INSECURE", value)
    assert targets.resolve_target("vsphere").verify is expected_verify


def test_profile_flag_overrides_env_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    save_config(
        Config(
            current_profile="prod",
            profiles={
                "prod": Profile(vsphere=BackendCreds(server="prod-h", username="u", password="p")),
                "alt": Profile(vsphere=BackendCreds(server="alt-h", username="u", password="p")),
            },
        )
    )
    monkeypatch.setenv("VSC_PROFILE", "prod")
    targets.set_active_profile("alt")  # --profile wins over VSC_PROFILE
    assert targets.resolve_target("vsphere").server == "alt-h"


def test_ghost_profile_raises_target_not_configured() -> None:
    save_config(Config(current_profile="ghost", profiles={}))
    with pytest.raises(targets.TargetNotConfigured) as exc:
        targets.resolve_target("vsphere")
    assert "ghost" in str(exc.value)


def test_delete_current_profile_reassigns_to_survivor() -> None:
    runner.invoke(
        app,
        [
            "profiles",
            "add",
            "a",
            "--vsphere-server",
            "ha",
            "--vsphere-username",
            "u",
            "--store-in-file",
        ],
    )
    runner.invoke(
        app,
        [
            "profiles",
            "add",
            "b",
            "--vsphere-server",
            "hb",
            "--vsphere-username",
            "u",
            "--store-in-file",
        ],
    )
    runner.invoke(app, ["profiles", "use", "a"])
    deleted = runner.invoke(app, ["profiles", "delete", "a"])
    assert json.loads(deleted.stdout)["current"] == "b"


def test_add_without_keyring_backend_exits_config_but_saves_profile(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(profiles_cli, "keyring_set", lambda *_a: False)
    result = runner.invoke(
        app,
        [
            "profiles",
            "add",
            "p",
            "--vsphere-server",
            "h",
            "--vsphere-username",
            "u",
            "--vsphere-password",
            "pw",
        ],
    )
    assert result.exit_code == int(ExitCode.CONFIG)
    assert "p" in load_config().profiles  # profile still persisted (no orphan/loss)
