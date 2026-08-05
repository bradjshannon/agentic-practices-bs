# `gh run list --limit N` silently caps at 1000 regardless of N

**Symptom:** Pulled a full month of GitHub Actions run history for a repo with `gh run list
--created 2026-07-01..2026-07-31 --limit 5000 --json ...` to compute a per-workflow run-count
breakdown. Got back exactly 1000 rows both times (`--limit 1000` and `--limit 5000` returned
byte-identical output). Nothing errored; nothing warned.

**What actually happened:** `gh run list` (and the underlying GH REST list-runs-for-repo
endpoint it wraps) has a hard result cap around 1000 regardless of the `--limit`/`per_page`
values requested. For a repo running 1000+ workflow runs in a 31-day window, the oldest ~10 days
of the window were silently dropped — the returned rows' `createdAt` range started 10 days into
the query window, not at its start. A cursory read (`wc -l`, "got some rows back") reads as
success.

**The rule:** when pulling a date-ranged list from `gh run list` (or any list endpoint with an
undocumented practical cap), check the actual min/max of the returned timestamps against the
requested range before trusting the count. If the returned range doesn't cover the request,
split into narrower sub-windows (e.g. weekly) until no sub-window itself returns exactly the cap
value, then dedupe by `databaseId` across windows.

**Why it generalises:** the same shape — "the tool returned *something*, so I assumed it returned
*everything*" — is the estate's own §6a/§6d failure mode (a green signal that doesn't prove what
it claims) applied to a CLI tool instead of a service health check. Any list-style API/CLI call
with a `--limit`/`per_page` parameter should be treated as advisory, not authoritative, until the
returned population is checked against the requested one.
