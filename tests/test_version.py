"""The package version lives in three hand-synced places (``vsc/_version.py`` as
the source of truth, ``[project].version`` in ``pyproject.toml`` which stamps the
built artifact, and ``uv.lock``). ``release.yml`` validates the git tag against
``vsc._version`` and the built wheel filename against the tag, so a partial bump
fails the release safely — but this test catches the drift far earlier, in CI.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from vsc import __version__
from vsc._version import __version__ as version_module

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_init_reexports_version_module() -> None:
    assert __version__ == version_module


def test_pyproject_version_matches_version_module() -> None:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["version"] == version_module
