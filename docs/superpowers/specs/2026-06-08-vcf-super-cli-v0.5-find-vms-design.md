# v0.5 — find VMs by attribute

**Milestone:** v0.5 — find VMs · **Issue:** #54 · **Date:** 2026-06-08

## Problem

You can `vsc vsphere vm list` and filter on what the vAPI `VM.FilterSpec` exposes
(names, power states, hosts, clusters, datacenters, folders, resource pools).
None of the **guest/runtime network fields** are filterable there, so the everyday
question *"which VM has `10.20.3.41`?"* is unanswerable from the CLI. Guest
networking lives only on the pyVmomi `guest.*` properties; the per-VM REST guest
API needs the moid first, useless for a reverse lookup.

## Command

```
vsc vsphere inventory find [--ip ...] [--name ...] [--hostname ...] [--mac ...]
                           [--guest-os ...] [--power-state ...] [--props ...] [-o ...]
```

Third command under `inventory_app`, next to `vm`/`host`. VM-focused for v1.

### Match semantics

- Flags **AND** together; a repeated flag **ORs** within that field.
- `--ip` matches any address across `guest.ipAddress` + every `guest.net[].ipAddress`,
  as an **exact IP or CIDR** via stdlib `ipaddress` (IPv4 and IPv6). An exact IP is
  just a `/32` (or `/128`) network, so one code path covers both.
- `--name`, `--hostname`, `--guest-os` are case-insensitive **substring**, or
  **glob** when the pattern has `*?[`. `--name` is fully client-side (one matcher).
- `--mac` exact, case-insensitive, against `guest.net[].macAddress`.
- `--power-state` ∈ {poweredOn, poweredOff, suspended} against `runtime.powerState`.
- **No match flag → usage error** (exit 2); we refuse to dump the whole inventory.
  `--props`/`-o` alone do not count.

### `--props` passthrough (output only)

Repeatable; mirrors `inventory vm --props`. Appends arbitrary property paths to the
single PropertyCollector retrieve so each **matched** VM also surfaces them under a
`properties` sub-dict — bridging search→inspect in one call. Never a match criterion.

## Implementation

`vsc/pyvmomi/find.py`:

- **Pure matcher** (`Criteria`, `matches`, `summarize`, `validate_criteria`, plus
  `_ip_match`/`_text_match`/`_addresses`/`_macs`) — operates only on a plain
  props dict, no pyVmomi import in the hot path, so it unit-tests in isolation.
- **One round-trip** (`find_matches` → `_retrieve_all_vms`): a
  `CreateContainerView(rootFolder, [vim.VirtualMachine], recursive=True)` plus a
  single `RetrieveContents` with a `TraversalSpec` pulling the fixed search paths
  **plus** any `--props`. The container view is **always destroyed** in a `finally`.

`vsc/pyvmomi/inventory.py` adds the thin `find` command: builds `Criteria` from the
flags, rejects an empty criteria set and malformed `--ip`/`--power-state` as usage
errors, and emits through the shared `run_read` runner (same JSON / error envelope /
exit codes as the other pyVmomi reads).

### Per-hit shape

```json
{ "obj": {"type": "VirtualMachine", "value": "vm-101"},
  "name": "web-1", "power_state": "poweredOn",
  "ip_addresses": ["10.20.3.41"], "hostname": "web-1.corp",
  "guest_os": "Ubuntu Linux (64-bit)",
  "properties": { "config.version": "vmx-19" } }   // only with --props
```

No matches → empty array, exit 0.

## Scope / non-goals (v1)

- vSphere/pyVmomi only; NSX has its own search surface.
- VMs only (no host/network/datastore search yet).
- Single `RetrieveContents` (no paging). Very large inventories may later want
  `RetrievePropertiesEx` + `maxObjects` paging — a scaling follow-up.
- VMs without VMware Tools / powered-off report no (or stale) guest IP and won't
  match `--ip`; expected, noted in the docs.
