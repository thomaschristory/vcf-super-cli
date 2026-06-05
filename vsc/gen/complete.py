"""Static, offline shell-completion helpers.

Every completer here derives its candidates from the introspected model or the
local config file — never from a network call. Completion must stay fast and
side-effect-free so ``<TAB>`` never opens a connection or prompts for auth.

Each factory returns a ``(incomplete: str) -> list[str]`` callable. Typer inspects
that signature and passes the partial word the user has typed; we return the
prefix-filtered candidates. Live resource-id completion (which *would* hit the API)
is deliberately out of scope for v0.3.
"""

from __future__ import annotations

from collections.abc import Callable

from vsc.config.store import load_config
from vsc.output.render import OutputFormat

Completer = Callable[[str], list[str]]


def _prefix(candidates: list[str], incomplete: str) -> list[str]:
    return [c for c in candidates if c.startswith(incomplete)]


def enum_completer(values: list[str]) -> Completer:
    """Complete an enum option from its fixed set of choices."""
    fixed = list(values)

    def complete(incomplete: str) -> list[str]:
        return _prefix(fixed, incomplete)

    return complete


def output_format_completer() -> Completer:
    """Complete ``--output`` from the supported output formats."""
    return enum_completer([fmt.value for fmt in OutputFormat])


def profile_completer() -> Completer:
    """Complete ``--profile`` from configured profile names.

    Reads the local config file only. Any failure (missing/unreadable config)
    yields no suggestions rather than raising — a broken config must never make
    tab-completion error out.
    """

    def complete(incomplete: str) -> list[str]:
        try:
            names = list(load_config().profiles)
        except Exception:
            return []
        return _prefix(names, incomplete)

    return complete
