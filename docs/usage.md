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

## Read-only in v0.1

v0.1 exposes only read (`GET`) operations. Write verbs arrive in v0.2 and will be
**dry-run by default**, requiring `--apply`.
