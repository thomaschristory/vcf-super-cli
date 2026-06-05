"""Load/save the config file and broker passwords through the OS keyring."""

from __future__ import annotations

import io
import os
from pathlib import Path

import keyring
import platformdirs
import structlog
from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from vsc.config.schema import Config

log = structlog.get_logger(__name__)

_KEYRING_SERVICE = "vcf-super-cli"
_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


class ConfigError(Exception):
    """The configuration file exists but is malformed or invalid."""


def config_path() -> Path:
    """Location of the config file (``VSC_CONFIG_FILE`` overrides the default)."""
    override = os.environ.get("VSC_CONFIG_FILE")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("vcf-super-cli", appauthor=False)) / "config.yaml"


def load_config() -> Config:
    """Read the config file, returning an empty Config if it does not exist.

    Raises :class:`ConfigError` (never a raw parse/validation error) if the file
    exists but is malformed, so callers can map it to a clean exit code.
    """
    path = config_path()
    if not path.exists():
        return Config()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh) or {}
        return Config.model_validate(data)
    except (YAMLError, ValidationError, TypeError) as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


def save_config(config: Config) -> Path:
    """Atomically write the config file at mode 0600 and return its path.

    The file is created with 0600 from the start (never a looser intermediate
    mode) and swapped in via an atomic rename, so a cleartext password is never
    momentarily world/group-readable.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    data = config.model_dump(exclude_none=True)
    buffer = io.StringIO()
    _yaml.dump(data, buffer)

    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, buffer.getvalue().encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
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
