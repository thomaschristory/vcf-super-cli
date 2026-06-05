---
name: vcf-super-cli
description: Use when querying VMware Cloud Foundation 9 (vSphere/vCenter inventory or NSX Policy objects) from the command line via `vsc`. The command tree is generated from the vcf-sdk; v0.1 is read-only.
---

# vcf-super-cli (`vsc`)

`vsc` is a CLI for VMware Cloud Foundation 9. Its command tree is generated from
the `vcf-sdk` vAPI bindings and split into two product groups:

- `vsc vsphere …` — vCenter inventory (vm, host, cluster, datacenter, datastore, folder, network)
- `vsc nsx …` — NSX Policy objects (segments, tier0s, tier1s, services, groups, security-policies, gateway-policies)

Discover the live surface with `vsc --help`, `vsc vsphere --help`, `vsc nsx --help`,
and `vsc vsphere vm --help`. Each leaf command has `get` (by id) and `list` verbs.

## Status

v0.1 is **read-only**. Write verbs (create/update/delete) arrive in v0.2 and will
be **dry-run by default**, requiring `--apply`.

## Conventions for agents

- **Output is JSON by default** — parse `stdout`. Use `--output table` / `-o table`
  only for human display.
- **Errors** go to `stderr` as `{ "error": { "code", "kind", "message", "details" } }`.
  `stdout` is data only; logs/diagnostics go to `stderr`.
- **Exit codes** are stable — branch on these, not on message text:
  `0` ok · `1` generic · `2` usage · `3` auth · `4` not-found · `5` connection ·
  `6` config · `7` conflict · `8` unavailable.

## Targeting an environment

Configure once, then select per command with `--profile/-p`:

```sh
vsc profiles add prod --vsphere-server vc.example --vsphere-username administrator@vsphere.local
vsc profiles set-password prod vsphere          # prompts; stored in the OS keyring
vsc --profile prod vsphere vm list
```

Environment variables override the profile (useful in CI):
`VSC_VSPHERE_SERVER`, `VSC_VSPHERE_USERNAME`, `VSC_VSPHERE_PASSWORD`,
`VSC_VSPHERE_INSECURE`, and the `VSC_NSX_*` equivalents; `VSC_PROFILE` selects a profile.

## Examples

```sh
vsc --profile prod vsphere vm list
vsc --profile prod vsphere vm get vm-42
vsc --profile prod vsphere host list -o table
vsc --profile prod nsx segments list
vsc --profile prod nsx tier1s get <tier1-id>
```

> This Skill ships with the package. Refresh an exported copy with
> `vsc skill export <dir> --apply`.
