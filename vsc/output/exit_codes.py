"""Documented, stable process exit codes.

These are part of the CLI's public contract for scripts and agents. Values are
frozen; add new codes rather than renumbering existing ones.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable exit codes returned by ``vsc``."""

    OK = 0
    """Success."""

    ERROR = 1
    """Generic/unexpected failure."""

    USAGE = 2
    """Invalid arguments or usage (Typer/Click default)."""

    AUTH = 3
    """Authentication or authorization failure."""

    NOT_FOUND = 4
    """A requested resource does not exist."""

    CONNECTION = 5
    """Could not reach or negotiate with the target (vCenter/NSX)."""

    CONFIG = 6
    """Missing or invalid configuration/profile."""

    CONFLICT = 7
    """Resource conflict (already exists, in use, wrong state, concurrent change)."""

    UNAVAILABLE = 8
    """Target temporarily unavailable, busy, or the request timed out."""
