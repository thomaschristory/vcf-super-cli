# Profiles & configuration

A **profile** bundles the connection details for a vCenter and/or an NSX manager.
Profiles live in a YAML file under your platform config dir (written mode `0600`);
passwords are stored in the OS **keyring** by default and are never printed.

## Create a profile

```sh
vsc profiles add prod \
  --vsphere-server vc.example.com \
  --vsphere-username administrator@vsphere.local \
  --nsx-server nsx.example.com \
  --nsx-username admin
```

Set passwords (prompted, stored in the keyring):

```sh
vsc profiles set-password prod vsphere
vsc profiles set-password prod nsx
```

Or pass them inline at create time (`--vsphere-password` / `--nsx-password`).
Use `--store-in-file` to keep a password in the config file instead of the keyring.

## Manage profiles

```sh
vsc profiles list
vsc profiles show prod        # passwords are never printed
vsc profiles use prod         # set the default profile
vsc profiles delete old
```

## Selecting a profile

Resolution order for each field (later wins):

1. the active profile — chosen by `--profile/-p`, else `VSC_PROFILE`, else the config default
2. environment variables (always override the profile)

```sh
vsc --profile prod vsphere vm list
VSC_PROFILE=prod vsc nsx segments list
```

## Environment variables

| Variable | Meaning |
|----------|---------|
| `VSC_PROFILE` | Active profile name |
| `VSC_VSPHERE_SERVER` / `VSC_NSX_SERVER` | Server host |
| `VSC_VSPHERE_USERNAME` / `VSC_NSX_USERNAME` | Username |
| `VSC_VSPHERE_PASSWORD` / `VSC_NSX_PASSWORD` | Password |
| `VSC_VSPHERE_INSECURE` / `VSC_NSX_INSECURE` | `1`/`true` to skip TLS verification (lab/self-signed) |
| `VSC_CONFIG_FILE` | Override the config file location |
| `VSC_LOG_LEVEL` | Log level on stderr (default `WARNING`) |
| `VSC_COMPLETE_DYNAMIC` | `1`/`true` to enable [live resource-id completion](usage.md#live-resource-id-completion-opt-in) (off by default) |
| `VSC_COMPLETE_TTL` | Live-completion cache TTL in seconds (default `60`) |
| `VSC_COMPLETE_TIMEOUT` | Hard timeout for a live-completion fetch in seconds (default `2`) |
| `VSC_CACHE_DIR` | Override the cache directory (where live-completion results are cached) |

!!! warning "TLS"
    Verification is **on by default**. Only set `VSC_*_INSECURE` (or
    `--vsphere-insecure`) for lab/self-signed certificates.
