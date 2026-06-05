"""Unit tests for the offline-constructible parts of the connect layer."""

from __future__ import annotations

from vsc.connect.session import _session


def test_session_verify_toggle() -> None:
    assert _session(verify=True).verify is True
    # verify=False also disables urllib3 warnings; must not raise offline.
    assert _session(verify=False).verify is False
