# Guard ledger

**A guard is not verified until it has been observed FIRING and observed STAYING SILENT.**
This file records which guards have had each direction actually demonstrated, and by what.

Copy this file into any repo that owns guards; keep one ledger per repo, next to the guards.

---

## Why one direction is not enough

A guard that has only ever been seen *not firing* is indistinguishable from a guard that
**cannot** fire. That is not hypothetical — it is how the worst failure in this system's
history hid:

> `archive-elf.ps1` uploaded debug symbols after every firmware build. The server rejected
> every upload (the version string exceeded a hard field limit). The wrapper ended in a bare
> `exit 0`, so every build reported success. Months later, two boards had firmware nobody
> could reproduce: one with permanently undecodable crash dumps, one with a 29 KB memory
> regression that could not be attributed. The guard-shaped thing in the middle had *never*
> been observed doing its job, and nobody noticed, because "no complaint" and "no capability"
> look identical.

The symmetric failure is a guard that only fires: it cries wolf, gets disabled, and takes its
true positives with it. **Both directions are load-bearing.** A ledger row with one column
filled is a row that is not done.

## What counts as a demonstration

| counts | does not count |
|---|---|
| The guard **blocked a real attempt** and the block was observed | "It should block that" |
| A test that **fails if the guard is removed** | A test that passes either way |
| A deliberately-injected violation, blocked, then reverted | Reading the source and agreeing with it |
| A benign case run through and observed passing | Assuming benign cases pass because none complained |

**The negative direction is the one people skip.** It is also the one that decides whether the
guard survives contact with daily use — a guard that fires on the correct form gets overridden
by reflex within a week.

## Retroactive entries

Fill rows in as guards are built. For guards that predate the ledger, fill retroactively where
the evidence exists — a test file that covers both directions *is* the evidence, cite it. Where
it does not exist, **write `NOT DEMONSTRATED` rather than leaving the cell blank**: an empty
cell reads as "not yet recorded", and `NOT DEMONSTRATED` reads as what it is, which is a guard
nobody has proven works.

## Columns

- **Guard** — file path, so the row is checkable.
- **Class** — from the enforcement table in `mechanisms/README.md`. A guard that is only
  *Voluntary* does not belong here; it belongs in `lessons/`.
- **Fires when it should** — the demonstration, specific enough to re-run.
- **Silent when it should be** — same, for the benign case.
- **Date** — when the *most recent* demonstration happened. A guard demonstrated once and then
  substantially rewritten is undemonstrated again.
- **Notes** — known gaps, false-positive history, what it cannot detect.

---

## Ledger

| Guard | Class | Fires when it should | Silent when it should be | Date | Notes |
|---|---|---|---|---|---|
| `mechanisms/hooks/lying_command_guard.py` (writer-tool substitution pattern) | Guard-at-the-action | 4 positive cases: backtick in double quotes, `$(…)` in double quotes, unquoted backtick, second tool name. All blocked. | 5 negative cases incl. the *recommended* form (quoted heredoc) and an unrelated tool carrying a backtick. All silent. | 2026-07-29 | Controls live in `lying_command_guard_test.py`, in a FILE not on a command line — the fixtures are themselves the shapes the guard matches, so passing them as argv makes the guard fire on its own test run. True positive on the text, false positive on the intent; the general blind spot of every text-matching guard. |
| `iotta-firmware/tools/flash-gate.ps1` | Guard-at-the-action | Untracked source file present → refused with the offending path named, never reached the archive step. | Only `dependencies.lock` modified (the documented live-tree side effect) → allowed through to a real flash. Also: `build` and `monitor` pass through with zero gate output. | 2026-07-29 | Escape hatch `-AllowUnreproducible "<reason>"` demonstrated: printed the waiver banner and proceeded. Lives in a TRACKED file because the local `idf.ps1` wrapper is gitignored with no history — each machine needs a one-line caller added. |
| `iotta-firmware/CMakeLists.txt` (PROJECT_VER length) | Structural | A 77-char version forced in → configure failed with the string, its length, the 31 limit and the reason. Then reverted and rebuilt clean. | Normal build produced a 27-char version and passed. Rebuild from a deleted `build/` on the same commit reproduced it identically. | 2026-07-29 | The limit it enforces (`esp_app_desc_t.version` = 31) had existed at the *consumer* for months and was swallowed there. Moving it to the producer is the whole point. Fallback path (`git` absent → `00000000-0000-nogit`) is **NOT DEMONSTRATED** — code-reviewed only. |
| `conductor-bs/tools/find_checks.py` (`http-json` kind) | Instrumented | Field present with a wrong value → FAILED. Absent field under `expect=yes` → FAILED. Server-name not on the allow-list → UNKNOWN. Path traversal → UNKNOWN. | Field present and matching → HOLDS. Server down → UNKNOWN, *not* FAILED (an instrument failure is not evidence the premise died). | 2026-07-29 | Two bugs found in its own first draft **only because positive and negative controls were run side by side**: a byte cap set below the real payload (every check silently UNKNOWN), and an absent field satisfying `expect=no` *vacuously* — a green verdict resting on a field nobody could find. |
| `mechanisms/hooks/evidence_with_claim.py` | Interrupt | `evidence_with_claim_test.py`, 6 positive cases: *kill-the-subagent (inferred from proxies, no quote)*, *ICAO false alarm (asserted from one directory)*, *verification claim with no quoted evidence*, *quote is present but did NOT come from this turn's tool output*, *span shorter than MIN_SPAN does not count as evidence*, *a bare 'proves' with no negation still needs evidence*. | Same file, 11 negative cases: claim **with** a verbatim quote; fenced block quoted verbatim; no tool calls this turn; no load-bearing claim at all; hedged verification; the word *unverified*; the human's words in a blockquote; a quoted doc containing "confirmed"; post-negation *proves nothing* / *confirmed nothing*; *should be verified* read as a plan. Plus 3 unit checks (`find_claims`, `code_spans` MIN_SPAN, blockquote stripping). Ran green here. | 2026-07-22 | Loads the hook **relative to the test file**, so it exercises this repo's copy. Known hole (from `mechanisms/README.md`): it cannot tell a *relevant* quote from an irrelevant one — it proves a check ran, not that it was the right check. |
| `mechanisms/hooks/requirement_before_mechanism.py` | Interrupt | `requirement_before_mechanism_test.py`, 2 BLOCK cases: *source edit, no requirement line* and *firmware source edit, no requirement*. | Same file, 10 ALLOW cases: source edit **with** a requirement line; requirement without bold markers; docs-only; markdown; test-only; changelog; scratchpad; no edits at all; explicit `requirement:ok` override; `stop_hook_active` loop guard. 12/12 passed here. | 2026-07-27 | **The test loads the hook from `~/.claude/hooks/`, not from this repo.** A green run therefore demonstrates the *installed* copy, not the banked one — the banked file could be broken and this suite would still pass. Same coupling as `repo_doc_guard_test.py` and both `lying_command_guard` tests. |
| `mechanisms/hooks/repo_doc_guard.py` | Guard-at-the-action | `repo_doc_guard_test.py`, 3 DENY cases: *parent never read*; *subagent never read, parent DID* (the silent false-ALLOW hole); *neither read*. | Same file, 3 ALLOW cases: *parent read*; *subagent read it itself, parent did NOT* (the false-DENY); *agent_id with no transcript file falls back to the parent's read*. | 2026-07-22 | **The suite does not currently pass: 1 FAIL, `actor_transcript should fall back to parent when the agent file is absent`.** Verified pre-existing (reproduced against the tree before this commit), not introduced here — recorded, not fixed. Two further caveats: it loads the hook from `~/.claude/hooks/`, and it `sys.exit(0)`s with a `SKIP` line if the real guidance doc it points at is missing — so on a machine without that repo it **exits green while demonstrating nothing**. Known gap already recorded in `lessons/`: it reads the *parent's* transcript, so a subagent cannot clear it itself. |
| `mechanisms/hooks/workflow_output_to_repo.py` | Interrupt | `workflow_output_to_repo_test.py`, 2 BLOCK cases: *workflow + no repo write* and *workflow + scratchpad-only write* (a scratchpad write does not count as banking). | Same file, 6 quiet cases: workflow + repo write; no workflow at all; a plain `Agent` (not `Workflow`); the `workflow-output:ok` escape hatch; `stop_hook_active`; a workflow in a **previous** turn. 8/8 passed here. | 2026-07-27 | Fixtures hardcode one machine's repo and scratchpad paths — these are the pre-existing `check_sanitized` findings on lines 17–18. On another machine the path-discriminating cases would not exercise the same branch, so the green is partly machine-local. |
| `mechanisms/hooks/stop_gate.py` | Interrupt | `stop_gate_test.py`, 7 objection-carrying cases: one objection is carried; *every* objection survives the merge; each is attributed to its check; several objections still produce ONE decision; an installed check still reports when others are absent; a raising check does not suppress the others; the crash is surfaced alongside a real block rather than swallowed. | Same file, 6 quiet cases: no check objects; a raising check does not block (fail-open); unparseable check output never blocks; a non-`block` decision is not treated as a block; a malformed payload never blocks the session; `stop_hook_active` honoured. 13/13 passed here. | 2026-07-27 | Drives a **temp directory of fake check scripts** (`HERE`/`CHECKS` repointed), never the real ones — so the result does not depend on which guards happen to be installed. That is why this is the most portable row here. |
| `mechanisms/hooks/data_validity_statement.py` | Interrupt | `data_validity_statement_test.py`, 6 BLOCK cases: 4 quantitative before/after comparisons with no validity statement; the same claim with the statement **inline** rather than on its own line; and a bare `Validity: fine` that names neither half. | Same file, 8 ALLOW cases: the claim with a properly-shaped `Validity:` line; single measurements with no comparison (bytes, `443 passed, 0 failed`, files changed, two mtimes); a test-count change that is not a measured population comparison; prose *about* the concept; a validity statement standing alone. 14/14 passed here. | 2026-07-28 | Loads the module **relative to the test file** — its own docstring says why: "a test that loads the module from `~/.claude` would pass while THIS repo's copy was broken." The rows above that do load from `~/.claude` are the ones that took that shortcut. |
| `mechanisms/hooks/pacer_armed.py` | Interrupt | Fired repeatedly in live use — refused turn-end with nothing scheduled to wake the run. | **NOT DEMONSTRATED** — no recorded case of it correctly staying silent when a pacer *was* armed. | 2026-07-29 | No test file. The silent direction is the one that matters here: if it fired unconditionally nobody would notice, because the remedy (arm a pacer) is cheap enough to comply with reflexively. |
| `mechanisms/hooks/turn_window.py` | Interrupt (shared boundary the Stop checks key on) | `turn_window_test.py`, boundary **recognised**: a genuine human message after a notification becomes the boundary (`start == 6`); a human message carrying attachments is human (`start == 1`) and `human_text_of` reads the attached question. | Same file, boundary **not** moved by machine traffic: `<task-notification>` does not start a turn (`start == 0`, the bug that produced 96 fake boundaries vs 87 real); `<system-reminder>`, `[SYSTEM NOTIFICATION - NOT USER INPUT]` and `Stop hook feedback:` all excluded; a `tool_result` entry yields `human_text_of → None`. 13/13 passed here. | 2026-07-29 | Test banked this run; **`turn_window.py` itself was updated to the machine's current revision at the same time** — the repo copy was an older one lacking `window()`/`human_start()`, so the test errored with `AttributeError` until it was refreshed. The refactor is additive (`turn()` now delegates to `window()`); no behaviour change was authored here. |
| `mechanisms/hooks/lying_command_guard.py` (CRLF-count + Git-Bash `/c/…`-in-JSON patterns) | Guard-at-the-action | `lying_command_guard_instrument_test.py`, 3 positive cases: `grep -c $'\r'` on a file, the same piped, and a `/c/Users/…` path embedded in a JSON string on a command line. All fired. | Same file, 5 negative cases deliberately built to look similar: an ordinary `grep -c`; grepping for the literal word `CRLF`; a Python `read_bytes().count(b'\r\n')` (the recommended replacement); a *native* `C:/…` path inside JSON; a URL inside JSON. All silent. 8/8 passed here. | 2026-07-29 | Test banked this run; the patterns it covers are newer than the writer-tool row above. **Loads the guard from `~/.claude/hooks/`**, matching the existing `lying_command_guard_test.py` — so like that row it demonstrates the installed copy, not the banked one. |
| `mechanisms/hooks/context_ledger.py` | Interrupt | `context_ledger_test.py`, 3 assertions on one real leak (60 identical ~1.2 KB stub errors, ~72 KB): it BLOCKS, it names the cause as a hook/plugin error, and it reports the count. | Same file, 4 quiet cases: one big legitimate 200 KB Read (count below the 50 floor); 60 *tiny* identical repeats (bytes below the 60 KB floor); `stop_hook_active`; and the fire-once property — the same leak re-run in the same session does **not** nag again. 7/7 passed here. | 2026-07-29 | Banked this run. Loads/executes the hook **relative to the test file**, so it exercises this repo's copy. Writes per-session dedup state to `mechanisms/hooks/.state/context_ledger/`; the test clears its own. Blind spot: it buckets on the first 400 normalized chars, so a flood that varies within that prefix (a per-line timestamp, a changing path) splits into many buckets and stays under both floors. |
| `mechanisms/hooks/output_budget.py` | Interrupt (now **advisory** by design) | **NOT DEMONSTRATED.** `output_budget_test.py` contains 4 firing cases (*3000-char wall*, *wall after an instruction*, *many messages summing over budget*, *instruction with attachments*) and **all 4 FAIL** — the hook was deliberately converted to advisory (records to `hook_log`, prints nothing, always returns 0) and its tests were never updated. 9/13 passed. Reproduced identically at the source install, so this is not a banking artifact. | `output_budget_test.py`, 9 passing quiet cases: a short status turn; a wall answering a `?` question and a wall answering *"explain …"* (the question exemption); `output-budget:asked` and `output-budget:artifact` overrides; a big tool result with small text; a wall in a **previous** turn; `stop_hook_active`; a question arriving with attachments. | 2026-07-29 | Banked this run **with its failures intact and not fixed** — this row is the point of the ledger. The hook's own file explains the conversion: blocking a Stop forced a rewrite of a message the human had already read, so a guard for reducing reading roughly doubled it. The consequence is that the *measurement* logic is still exercised only in the negative direction, and nothing now proves it can still detect an over-budget turn at all. `output_volume_preturn.py` is the successor mechanism. |
| `mechanisms/hooks/output_volume_preturn.py` | Instrumented | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | — | Banked this run. **No test file exists.** It is a UserPromptSubmit hook that prints one line when cumulative output since the human last spoke exceeds a budget and nothing otherwise — so its silent direction is its normal state, which is exactly the configuration the `archive-elf.ps1` failure at the top of this file describes: a control that has only ever been seen not-firing is indistinguishable from one that cannot fire. |
| `mechanisms/hooks/hook_log.py`, `hook_rollup.py` | Instrumented | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | — | Observability rather than enforcement; still worth a row, because a *logger* that silently stops logging is the same defect class as everything else here. |
| `iotta-bs/tools/check_docs.py` | Structural | Rejects a stale generated index and a work-item id in the wrong file — both observed in live use. | Passes on a correct tree; run many times per session. | 2026-07-28 | Its own docstring carries the doctrine this ledger rests on: *"a check with false positives gets bypassed with `--no-verify`, and a bypassed check is worse than no check."* |
| `iotta-bs/tools/failure_mode_hunt.py` (R1–R4) | Instrumented (advisory) | Each of the 4 rules has a **positive fixture** — reduced pre-fix source that must be flagged. | Each has **negative fixtures** — post-fix source that must not be. 19 tests total. | 2026-07-27 | The strongest row here, and the model for the rest: each fixture names the commit that fixed the defect it was derived from. **Known limit:** a fixture is a frozen snapshot and does not age with the codebase, so a rule can keep matching its fixture while ceasing to match how that pattern is written today. The positive control proves the matcher still RUNS, not that it still COVERS. |
| `tools/check_sanitized.py` | Structural | 4 positives: lowercase tailnet host in a URL, bare `*.ts.net` FQDN, the tailnet id alone, and the uppercase `VIDEO` label still caught. | 4 negatives: the ordinary word *video* mid-sentence and at sentence start, an unrelated `.net` domain, and plain prose. 8/8. | 2026-07-29 | **The case gap that motivated this row:** label patterns are uppercase (`VIDEO`) but the leaking form is a lowercase hostname inside a URL. Making the label `IGNORECASE` was the WRONG fix — it would fire on any lesson about audio/video. Matching the SHAPE (`*.ts.net`) instead also covers machines nobody has coined yet, which the file's own "add it the day it is coined" instruction cannot do, because that instruction requires remembering. Found only because a hook was hand-rejected for carrying a tailnet host the checker had passed clean. Adding the pattern surfaced **zero** new findings, so this closed the hole before anything went through it. |

---

## Rows that should exist and do not

Recording absence explicitly, because an unlisted guard is indistinguishable from a guard
nobody thought to list:

- `context_ledger.py`, `output_budget.py` and `output_volume_preturn.py` were on this list until
  2026-07-29; they are now banked in `mechanisms/hooks/` and have rows above.
- `pacer_announce.py` — still machine-local, and **deliberately not banked**. Its three
  load-bearing constants are all machine- or project-specific: a fallback status-page URL that is
  a real private tailnet host and port, a hardcoded inbox path under one operator's home, and a
  list of repo roots that gates whether the hook does anything at all. Sanitizing any of them
  changes what the hook does, which is the stated bar for declining to copy. It belongs in
  `conductor-bs`. Note that `tools/check_sanitized.py` would **not** have caught it — the
  relevant machine-name pattern is case-sensitive and the host appears lowercase — so this was a
  read, not a check result. Consider that a gap in the checker, recorded here rather than silently patched.
- `pacer_inbox_surface_test.py` — the only test for `pacer_announce._new_inbox_lines`
  (9 cases, both directions: unhandled entries surface, handled ones do not, a surfaced entry is
  never repeated, a later new entry still gets through, and two fail-open cases). Not banked
  either, because it imports the module above and would be inert here.
- Any guard that exists only inside a gitignored per-machine wrapper. `iotta-firmware/idf.ps1`
  was exactly this until 2026-07-29; the policy was moved to a tracked file precisely so it
  could appear here.
