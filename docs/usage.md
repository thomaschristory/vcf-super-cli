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

Completing a live resource id (e.g. `<vm>` from a real inventory) would require a
network call and is deliberately **not** done in this release.

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
