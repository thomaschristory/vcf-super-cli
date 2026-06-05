"""Named profiles and configuration for ``vsc``.

A profile bundles per-backend connection details (server, username, optional
password, TLS verification). Profiles live in a YAML file under the platform
config dir; passwords are kept in the OS keyring by default. Environment
variables (``VSC_*``) always override the stored profile.
"""
