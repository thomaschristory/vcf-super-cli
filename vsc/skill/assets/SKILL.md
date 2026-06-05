---
name: vcf-super-cli
description: Use when querying or changing VMware Cloud Foundation 9 (vSphere/vCenter and NSX Policy) from the command line via `vsc`. The command tree is generated from the vcf-sdk. Reads return JSON; writes are dry-run by default and require `--apply`.
---

# vcf-super-cli (`vsc`)

`vsc` is a CLI for VMware Cloud Foundation 9. Its command tree is generated from
the `vcf-sdk` vAPI bindings and split into two product groups:

- `vsc vsphere …` — vCenter (vm, host, cluster, datacenter, datastore, folder, network,
  resource-pool, and the VM power/hardware leaves: power, cpu, memory, disk, ethernet —
  each takes the VM id as an argument, e.g. `vsc vsphere power stop <vm>`)
- `vsc nsx …` — NSX Policy (segments, tier0s, tier1s, services, groups, security-policies,
  gateway-policies, ip-pools, dhcp-server-configs, dhcp-relay-configs, locale-services)

Discover the live surface with `vsc --help`, `vsc vsphere --help`, `vsc nsx --help`,
and `vsc vsphere vm --help`. Leaves expose `list`/`get <id>` reads and — where the SDK
provides them — write verbs (`create`, `delete`, `set`, `patch`, power actions, …).

## Writes are dry-run by default

**Every write command previews and changes nothing unless you pass `--apply`.** This is
the core safety contract — a write without `--apply` never opens a connection.

```sh
vsc --profile prod vsphere vm delete vm-42            # DRY-RUN: prints the plan, changes nothing
vsc --profile prod vsphere vm delete vm-42 --apply    # executes the delete
```

Dry-run emits the resolved request so you can see exactly what `--apply` would send:

```json
{ "applied": false,
  "request": { "method": "DELETE", "url": "/vcenter/vm/vm-42",
               "path_params": {"vm": "vm-42"}, "query": {}, "body": null,
               "backend": "vsphere", "service": "vm", "operation": "delete" },
  "apply_hint": "re-run with --apply to execute" }
```

With `--apply`, the same envelope carries `"applied": true` and a `"result"` field
(the SDK response) instead of `apply_hint`. Branch on `applied`.

Bodies/specs are passed as JSON to the relevant option and built into the SDK struct:

```sh
vsc --profile prod nsx segments set web --segment '{"display_name":"web"}'            # dry-run
vsc --profile prod nsx segments set web --segment '{"display_name":"web"}' --apply    # executes
```

Write failures use the same error envelope + exit codes — notably `7` CONFLICT
(already-exists / in-use / wrong-state / concurrent-change) and `8` UNAVAILABLE
(busy / timed-out / temporarily unavailable).

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
# Reads
vsc --profile prod vsphere vm list
vsc --profile prod vsphere vm get vm-42
vsc --profile prod vsphere host list -o table
vsc --profile prod nsx segments list
vsc --profile prod nsx tier1s get <tier1-id>

# Writes — preview first (dry-run), then --apply
vsc --profile prod vsphere power stop vm-42                    # preview
vsc --profile prod vsphere power stop vm-42 --apply            # execute
vsc --profile prod nsx tier1s set t1-web --tier1 '{"display_name":"web"}' --apply
```

> This Skill ships with the package. Refresh an exported copy with
> `vsc skill export <dir> --apply`.
