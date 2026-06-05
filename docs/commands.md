# Commands

The `vsphere` and `nsx` command trees are **generated from the `vcf-sdk` vAPI
bindings**, so `vsc --help` (and each sub-`--help`) is always the authoritative,
version-accurate reference. This page is an overview.

Generated leaves expose both **read** and **write** verbs:

- `list` — list resources (optional `--filter '<json>'`)
- `get <id>` — fetch one resource by id, **where the SDK provides a by-id GET**
  (e.g. `vm`, `cluster`, `datacenter`, `datastore`; some leaves such as `host`,
  `folder`, and `network` are `list`-only)
- writes — `create`, `delete`, `set` (PUT upsert), `patch`, and action verbs
  (e.g. `start`/`stop`/`reset` under `power`). **Writes are dry-run by default and
  require `--apply`** — see [Writes](writes.md).

## `vsc vsphere …` (vCenter)

Generated from `com.vmware.vcenter`:

| Group | Examples |
|-------|----------|
| `vm` | `vsc vsphere vm list`, `vsc vsphere vm get <vm>`, `vsc vsphere vm delete <vm> --apply` |
| `host` | `vsc vsphere host list`, `vsc vsphere host disconnect <host> --apply` |
| `cluster` | `vsc vsphere cluster list` |
| `datacenter` | `vsc vsphere datacenter list` |
| `datastore` | `vsc vsphere datastore list` |
| `folder` | `vsc vsphere folder list` |
| `network` | `vsc vsphere network list` |
| `resource-pool` | `vsc vsphere resource-pool create --spec '<json>' --apply` |
| `power` | `vsc vsphere power start\|stop\|reset\|suspend <vm> --apply` |
| `cpu` / `memory` / `disk` / `ethernet` | VM hardware reads + writes, e.g. `vsc vsphere cpu update <vm> --spec '<json>' --apply` |

## `vsc nsx …` (NSX Policy)

Generated from `vcf.nsx.policy`:

| Group | Examples |
|-------|----------|
| `segments` | `vsc nsx segments list`, `vsc nsx segments set <id> --segment '<json>' --apply` |
| `tier0s` / `tier1s` | `vsc nsx tier1s list`, `vsc nsx tier1s set <id> --tier1 '<json>' --apply` |
| `services` | `vsc nsx services list` |
| `groups` | `vsc nsx groups list`, `vsc nsx groups delete <domain> <group> --apply` |
| `security-policies` | `vsc nsx security-policies list` |
| `gateway-policies` | `vsc nsx gateway-policies list` |
| `ip-pools` | `vsc nsx ip-pools set <id> --ip-address-pool '<json>' --apply` |
| `dhcp-server-configs` / `dhcp-relay-configs` | DHCP config reads + writes |
| `locale-services` | Tier-1 locale services reads + writes |

## Curated commands

- `vsc profiles …` — manage connection profiles (see [Profiles](profiles.md))
- `vsc skill export <dir> [--apply]` — export the bundled agent Skill
- `vsc --version`

## Filtering

`list` accepts the SDK filter spec as JSON:

```sh
vsc --profile prod vsphere vm list --filter '{"power_states": ["POWERED_ON"]}'
```

Per-field flags for filters are on the v0.3 roadmap.
