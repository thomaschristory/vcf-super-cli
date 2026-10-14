"""Build authenticated vAPI ``StubConfiguration`` objects.

vCenter uses session-id auth: username/password is exchanged for a session id
(one network round-trip), then every call carries that session. NSX uses HTTP
basic auth applied per request — no session to create or delete.
"""

from __future__ import annotations

from typing import Any

import requests
import structlog
import urllib3
from com.vmware.cis_client import Session
from vmware.vapi.bindings.stub import StubConfiguration
from vmware.vapi.lib.connect import get_requests_connector
from vmware.vapi.security.client.security_context_filter import (
    LegacySecurityContextFilter,
)
from vmware.vapi.security.session import create_session_security_context
from vmware.vapi.security.user_password import (
    create_user_password_security_context,
)
from vmware.vapi.stdlib.client.factories import StubConfigurationFactory

log = structlog.get_logger(__name__)


def _warn_insecure(backend: str, server: str) -> None:
    """Warn (to stderr) that a connection is running with TLS verification off."""
    log.warning(
        "insecure_tls",
        backend=backend,
        server=server,
        detail="TLS verification disabled; credentials traverse an unverified channel",
    )


def _session(verify: bool | str) -> requests.Session:
    sess = requests.Session()
    sess.verify = verify
    if verify is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return sess


def connect_vsphere(
    server: str, username: str, password: str, *, verify: bool | str = True
) -> StubConfiguration:
    """Authenticate to vCenter and return a session-backed StubConfiguration."""
    if verify is False:
        _warn_insecure("vsphere", server)
    sess = _session(verify)
    url = f"https://{server}/api"
    login_cfg = StubConfigurationFactory.new_std_configuration(
        get_requests_connector(
            session=sess,
            url=url,
            provider_filter_chain=[
                LegacySecurityContextFilter(
                    security_context=create_user_password_security_context(username, password)
                )
            ],
        )
    )
    session_id: str = Session(login_cfg).create()
    return StubConfigurationFactory.new_std_configuration(
        get_requests_connector(
            session=sess,
            url=url,
            provider_filter_chain=[
                LegacySecurityContextFilter(
                    security_context=create_session_security_context(session_id)
                )
            ],
        )
    )


def connect_nsx(
    server: str, username: str, password: str, *, verify: bool | str = True
) -> StubConfiguration:
    """Return a basic-auth StubConfiguration for the NSX Policy API."""
    if verify is False:
        _warn_insecure("nsx", server)
    sess = _session(verify)
    connector: Any = get_requests_connector(session=sess, url=f"https://{server}")
    connector.set_security_context(create_user_password_security_context(username, password))
    return StubConfiguration(connector)
