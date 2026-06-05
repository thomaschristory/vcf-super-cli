"""vcf-super-cli (`vsc`) — a modern CLI for VMware Cloud Foundation 9.

The command tree is generated dynamically by introspecting the ``vcf-sdk`` vAPI
bindings. See ``docs/superpowers/specs`` for the design.
"""

from __future__ import annotations

from vsc._version import __version__

__all__ = ["__version__"]
