---
name: vcf-super-cli
description: Use when querying VMware Cloud Foundation 9 (vSphere/vCenter inventory or NSX Policy objects) from the command line via `vsc`. The CLI's command tree is generated from the vcf-sdk; v0.1 is read-only.
---

# vcf-super-cli (`vsc`)

`vsc` is a CLI for VMware Cloud Foundation 9. Its command tree is generated from
the `vcf-sdk` vAPI bindings and split into two product groups:

- `vsc vsphere …` — vCenter inventory (vm, host, cluster, datastore, network, …)
- `vsc nsx …` — NSX Policy API objects (segments, gateways, groups, firewall, …)

## Status

v0.1 is **read-only**. Write verbs (create/update/delete) arrive in v0.2 and will
be **dry-run by default**, requiring `--apply`.

## Conventions for agents

- **Output is JSON by default** — parse `stdout`. Use `--output table` only for
  human display.
- **Errors** go to `stderr` as `{ "error": { "code", "message", "kind", "details" } }`.
- **Exit codes** are stable: `0` ok, `2` usage, `3` auth, `4` not-found,
  `5` connection, `6` config, `1` generic. Branch on these, not on message text.
- **Profiles**: target a named profile with `--profile <name>`; environment
  variables (`VSC_*`) override config.
- Discover structure with `vsc --help`, `vsc vsphere --help`, `vsc nsx --help`.

## Examples

```sh
vsc vsphere vm list --profile prod
vsc vsphere host get --host host-42
vsc nsx segment list
```

> This Skill ships with the package. Refresh it from an install with
> `vsc skill export <dir> --apply`.
