"""Error envelope + exit-code mapping tests."""

from __future__ import annotations

import com.vmware.vapi.std.errors_client as verr
import requests
from com.vmware.vapi.std_client import LocalizableMessage

from vsc.output.errors import (
    envelope_for_transport,
    envelope_for_vapi,
    is_vapi_error,
)
from vsc.output.exit_codes import ExitCode


def _err(cls: type, message: str = "msg") -> object:
    lm = LocalizableMessage(id="x.y", default_message=message, args=[])
    return cls(messages=[lm], data=None)


def test_not_found_maps_to_not_found() -> None:
    env, code = envelope_for_vapi(_err(verr.NotFound, "vm gone"))
    assert code is ExitCode.NOT_FOUND
    assert env["error"]["kind"] == "NOT_FOUND"
    assert env["error"]["message"] == "vm gone"
    assert env["error"]["code"] == int(ExitCode.NOT_FOUND)


def test_auth_errors() -> None:
    _, code = envelope_for_vapi(_err(verr.Unauthenticated))
    assert code is ExitCode.AUTH
    _, code2 = envelope_for_vapi(_err(verr.Unauthorized))
    assert code2 is ExitCode.AUTH


def test_unavailable_and_usage_and_conflict() -> None:
    assert envelope_for_vapi(_err(verr.ServiceUnavailable))[1] is ExitCode.UNAVAILABLE
    assert envelope_for_vapi(_err(verr.InvalidArgument))[1] is ExitCode.USAGE
    assert envelope_for_vapi(_err(verr.AlreadyExists))[1] is ExitCode.CONFLICT


def test_unknown_vapi_error_is_generic() -> None:
    _, code = envelope_for_vapi(_err(verr.InternalServerError))
    assert code is ExitCode.ERROR


def test_transport_errors() -> None:
    _, conn = envelope_for_transport(requests.exceptions.ConnectionError("down"))
    assert conn is ExitCode.CONNECTION
    env, ssl = envelope_for_transport(requests.exceptions.SSLError("bad cert"))
    assert ssl is ExitCode.CONNECTION  # TLS trust failure is a connection problem
    assert "INSECURE" in env["error"]["message"]


def test_is_vapi_error() -> None:
    assert is_vapi_error(_err(verr.NotFound))
    assert not is_vapi_error(ValueError("nope"))
