# Commands

The `vsphere` and `nsx` command trees are **generated from the `vcf-sdk` vAPI
bindings**, so `vsc --help` (and each sub-`--help`) is always the authoritative,
version-accurate reference. This page is an overview.

Generated leaves expose read verbs:

- `list` — list resources (optional `--filter '<json>'`)
- `get <id>` — fetch one resource by id, **where the SDK provides a by-id GET**
  (e.g. `vm`, `cluster`, `datacenter`, `datastore`; some leaves such as `host`,
  `folder`, and `network` are `list`-only)

## `vsc vsphere …` (vCenter)

Generated from `com.vmware.vcenter`:

| Group | Examples |
|-------|----------|
| `vm` | `vsc vsphere vm list`, `vsc vsphere vm get <vm>` |
| `host` | `vsc vsphere host list` |
| `cluster` | `vsc vsphere cluster list` |
| `datacenter` | `vsc vsphere datacenter list` |
| `datastore` | `vsc vsphere datastore list` |
| `folder` | `vsc vsphere folder list` |
| `network` | `vsc vsphere network list` |

## `vsc nsx …` (NSX Policy)

Generated from `vcf.nsx.policy`:

| Group | Examples |
|-------|----------|
| `segments` | `vsc nsx segments list`, `vsc nsx segments get <id>` |
| `tier0s` / `tier1s` | `vsc nsx tier1s list` |
| `services` | `vsc nsx services list` |
| `groups` | `vsc nsx groups list` |
| `security-policies` | `vsc nsx security-policies list` |
| `gateway-policies` | `vsc nsx gateway-policies list` |

## Curated commands

- `vsc profiles …` — manage connection profiles (see [Profiles](profiles.md))
- `vsc skill export <dir> [--apply]` — export the bundled agent Skill
- `vsc --version`

## Filtering

`list` accepts the SDK filter spec as JSON:

```sh
vsc --profile prod vsphere vm list --filter '{"power_states": ["POWERED_ON"]}'
```

Per-field flags for filters are on the v0.2 roadmap.
