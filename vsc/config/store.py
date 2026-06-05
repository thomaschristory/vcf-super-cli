"""Load/save the config file and broker passwords through the OS keyring."""

from __future__ import annotations

import io
import os
from pathlib import Path

import keyring
import platformdirs
import structlog
from ruamel.yaml import YAML

from vsc.config.schema import Config

log = structlog.get_logger(__name__)

_KEYRING_SERVICE = "vcf-super-cli"
_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


def config_path() -> Path:
    """Location of the config file (``VSC_CONFIG_FILE`` overrides the default)."""
    override = os.environ.get("VSC_CONFIG_FILE")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("vcf-super-cli", appauthor=False)) / "config.yaml"


def load_config() -> Config:
    """Read the config file, returning an empty Config if it does not exist."""
    path = config_path()
    if not path.exists():
        return Config()
    with path.open("r", encoding="utf-8") as fh:
        data = _yaml.load(fh) or {}
    return Config.model_validate(data)


def save_config(config: Config) -> Path:
    """Write the config file (mode 0600) and return its path."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(exclude_none=True)
    buffer = io.StringIO()
    _yaml.dump(data, buffer)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    path.chmod(0o600)
    return path


# --------------------------------------------------------------------------- #
# Keyring (best-effort; a missing backend degrades gracefully)
# --------------------------------------------------------------------------- #


def keyring_get(profile: str, backend: str) -> str | None:
    try:
        return keyring.get_password(_KEYRING_SERVICE, f"{profile}:{backend}")
    except Exception as exc:
        log.debug("keyring.get_failed", error=str(exc))
        return None


def keyring_set(profile: str, backend: str, password: str) -> bool:
    try:
        keyring.set_password(_KEYRING_SERVICE, f"{profile}:{backend}", password)
        return True
    except Exception as exc:
        log.debug("keyring.set_failed", error=str(exc))
        return False


def keyring_delete(profile: str, backend: str) -> None:
    try:
        keyring.delete_password(_KEYRING_SERVICE, f"{profile}:{backend}")
    except Exception as exc:
        log.debug("keyring.delete_failed", error=str(exc))
