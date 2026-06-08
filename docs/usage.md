# Output, errors & exit codes

`vsc` is built to be scriptable and agent-friendly: **stdout is data**, stderr is
diagnostics, and exit codes are a stable contract.

## Output formats

JSON is the default; `--output/-o table` renders a Rich table for humans.

```sh
vsc --profile prod vsphere vm list            # JSON (default)
vsc --profile prod vsphere vm list -o table   # table
```

Only `json` and `table` are accepted; anything else is rejected with exit code `2`.

## Shell completion

Install completion for your shell once:

```sh
vsc --install-completion          # bash, zsh, fish, PowerShell
vsc --show-completion             # print the script instead of installing
```

Completion is **fully offline** — it never opens a connection. It suggests:

- enum option choices (e.g. `--power-states <TAB>` → `POWERED_ON`, `POWERED_OFF`),
- output formats (`-o <TAB>` → `json`, `table`),
- configured profile names (`--profile <TAB>`),
- and per-field `list` filter enum choices.

### Live resource-id completion (opt-in)

Completing a real id (e.g. `<vm>` from the live inventory) does require a network
call, so it is **opt-in** and off by default:

```sh
export VSC_COMPLETE_DYNAMIC=1
vsc vsphere vm get <TAB>          # → vm-101  vm-102 …  (real ids, names as help)
```

When enabled, pressing `<TAB>` on an id-typed argument or option suggests live
ids for that resource type (VMs, hosts, clusters, datacenters, datastores,
resource pools), showing each resource's name as completion help.

It is built to never get in your way:

- **Off by default.** Without `VSC_COMPLETE_DYNAMIC`, `<TAB>` stays fully offline
  (the suggestions above are all you get).
- **Cached.** Results are cached per profile/backend/resource-type under the
  platform cache dir with a short TTL (default 60s; override with
  `VSC_COMPLETE_TTL=<seconds>`), so repeated presses don't re-hit the API.
- **Bounded and fail-soft.** The fetch is abandoned after a short timeout
  (`VSC_COMPLETE_TIMEOUT`, default 2s); any error, missing auth, or timeout
  yields no suggestions — `<TAB>` never hangs or prints a traceback.
- **`--help` is always offline.** Only the shell-completion subprocess ever
  fetches; `--help` and command execution are unaffected.

This is a convenience only. The agent contract is unchanged: don't rely on
completion for correctness — list commands remain the source of truth for ids.

## Error envelope

Errors are written to **stderr** as a stable JSON object:

```json
{
  "error": {
    "code": 4,
    "kind": "NOT_FOUND",
    "message": "...",
    "details": { }
  }
}
```

`kind` is the vAPI error type (or the exception class for transport/config errors).
Branch on `code`/`kind`, never on `message` text.

## Exit codes

| Code | Name | Meaning |
|-----:|------|---------|
| 0 | OK | Success |
| 1 | ERROR | Generic / unexpected failure |
| 2 | USAGE | Invalid arguments or usage |
| 3 | AUTH | Authentication / authorization failure |
| 4 | NOT_FOUND | Requested resource does not exist |
| 5 | CONNECTION | Could not reach or negotiate with the target (incl. TLS) |
| 6 | CONFIG | Missing or invalid configuration/profile |
| 7 | CONFLICT | Already exists / in use / wrong state / concurrent change |
| 8 | UNAVAILABLE | Target busy, timed out, or temporarily unavailable |

## Writes are dry-run by default

Write commands (`create`, `delete`, `set`, `patch`, power actions, …) **preview the
request and change nothing unless `--apply` is passed** — a dry-run never opens a
connection. See [Writes](writes.md) for the full model and the request/response
envelope. Write failures use the same error envelope and exit codes above (notably
`7` CONFLICT and `8` UNAVAILABLE).
