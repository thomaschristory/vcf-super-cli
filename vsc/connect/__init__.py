"""Connections, sessions, and authentication for vCenter and NSX.

The generator is connection-agnostic: it asks a ``connect_for_backend`` callable
for an authenticated ``StubConfiguration`` only when a command actually runs, so
``--help`` and tree assembly stay fully offline.
"""
