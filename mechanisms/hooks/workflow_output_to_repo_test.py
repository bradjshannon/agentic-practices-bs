#!/usr/bin/env python3
"""Tests for workflow_output_to_repo.py.

The benign cases are the point: a guard that fires on ordinary turns gets disabled and
takes its true positives with it. So every "must NOT fire" case below is as load-bearing
as the one "must fire" case.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_output_to_repo.py")

# Fictional paths on purpose. These assert PATH LOGIC -- "does this fragment match, is
# this one rejected as non-durable" -- which never needed a real project name, and the
# real ones leaked into a public repo until 2026-07-29. The durable-repo fragments come
# from a TEMP config written below, never from the operator's real
# ~/.claude/workflow-output-repos.conf: a test that reads the live config would pass or
# fail for reasons that have nothing to do with this file.
REPO = "C:/Users/example/github/example-project/docs/reviews/x.md"
SCRATCH = ("C:/Users/example/AppData/Local/Temp/claude/C--github-example-project"
           "/abc/scratchpad/notes.md")

# A repo the temp config does NOT list -- used to prove the config is what decides.
UNLISTED = "C:/Users/example/github/some-other-repo/docs/x.md"

_CONF = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8")
_CONF.write("# temp config for the test\n/github/example-project/\n\n# a family:\n"
            "/github/example-platform-\n")
_CONF.close()
CONF_PATH = _CONF.name


def entry(role, blocks):
    return json.dumps({"type": role, "message": {"content": blocks}})


def user_msg(text):
    return json.dumps({"type": "user", "message": {"content": text}})


def run(entries, stop_active=False, conf=CONF_PATH):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("\n".join(entries))
        path = fh.name
    env = dict(os.environ)
    if conf is None:
        # Point at a path that cannot exist, to exercise the no-config fallback.
        env["WORKFLOW_OUTPUT_REPOS_CONF"] = os.path.join(path + ".absent")
    else:
        env["WORKFLOW_OUTPUT_REPOS_CONF"] = conf
    try:
        payload = {"transcript_path": path, "stop_hook_active": stop_active}
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        out = (p.stdout or "").strip()
        return json.loads(out) if out else None
    finally:
        os.unlink(path)


def check(name, got_block, want_block):
    ok = bool(got_block) == want_block
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return ok


results = []

# MUST FIRE: workflow ran, nothing written to a repo.
r = run([
    user_msg("audit the codebase"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "Found 19 findings."}]),
])
results.append(check("workflow + no repo write -> BLOCKS", r, True))

# MUST NOT FIRE: workflow ran and its product was written to the repo.
r = run([
    user_msg("audit the codebase"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": REPO}}]),
])
results.append(check("workflow + repo write -> quiet", r, False))

# MUST NOT FIRE: no workflow at all (the overwhelmingly common turn).
r = run([
    user_msg("fix the bug"),
    entry("assistant", [{"type": "tool_use", "name": "Edit",
                         "input": {"file_path": "C:/tmp/whatever.py"}}]),
])
results.append(check("no workflow -> quiet", r, False))

# MUST NOT FIRE: a plain Agent subagent is not a Workflow.
r = run([
    user_msg("look something up"),
    entry("assistant", [{"type": "tool_use", "name": "Agent", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "The answer is 4."}]),
])
results.append(check("Agent (not Workflow) -> quiet", r, False))

# MUST FIRE: scratchpad write does not count as banking the output.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": SCRATCH}}]),
])
results.append(check("workflow + scratchpad-only write -> BLOCKS", r, True))

# MUST NOT FIRE: explicit escape hatch.
r = run([
    user_msg("quick question"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text",
                         "text": "workflow-output:ok - throwaway count, no product."}]),
])
results.append(check("escape hatch -> quiet", r, False))

# MUST NOT FIRE: already blocked once this stop.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
], stop_active=True)
results.append(check("stop_hook_active -> quiet (no loop)", r, False))

# MUST NOT FIRE: workflow in a PREVIOUS turn, this turn is unrelated.
r = run([
    user_msg("run an audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    user_msg("now just tell me the time"),
    entry("assistant", [{"type": "text", "text": "It is 3pm."}]),
])
results.append(check("workflow in a previous turn -> quiet", r, False))

# ── The config-loading path (added 2026-07-29 with the fragment list) ────────────────
# The list of durable repos is machine-local config, not a literal in the hook. These
# cases assert that the CONFIG is what decides -- otherwise a config that silently
# failed to load would look exactly like a working one in every case above.

# MUST NOT FIRE: a fragment written with a family prefix in the temp config.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path":
                                   "C:/Users/example/github/example-platform-config/a.md"}}]),
])
results.append(check("config family fragment matches -> quiet", r, False))

# MUST FIRE: a real repo write that the config does NOT list. This is the positive
# control on the loader: if the config were ignored and something broad matched
# everything, this case would go quiet and the suite would be measuring nothing.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": UNLISTED}}]),
])
results.append(check("repo absent from config -> BLOCKS", r, True))

# MUST NOT FIRE with NO config file at all: the fallback must leave a usable hook, not
# an empty fragment list. An empty list would make every workflow turn block -- the
# cry-wolf failure that gets a guard disabled.
r = run([
    user_msg("audit"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "tool_use", "name": "Write",
                         "input": {"file_path": REPO}}]),
], conf=None)
results.append(check("no config -> fallback still recognises a repo write", r, False))

# ── The EFFECT check (added 2026-07-22): "did the repo change on disk", not "did a
# Write/Edit tool_use with a repo file_path appear in THIS transcript". Proves the git-
# status path is actually wired, not merely present -- a subagent write or a Bash
# heredoc never shows up as a tracked Write/Edit block, which is exactly what the old
# transcript-only scan missed (see the module docstring's FALSE POSITIVE/NEGATIVE case).
# WORKFLOW_OUTPUT_REPO_ROOTS pins the roots directly so these cases test repo_changed()
# itself, not the cwd/blob mining that finds roots in the first place.
import subprocess as _sp


def _git(*args, cwd):
    _sp.run(["git", "-C", cwd] + list(args), capture_output=True, check=True)


EFFECT_REPO = tempfile.mkdtemp(prefix="wotr-effect-")
_git("init", "-q", cwd=EFFECT_REPO)
_git("config", "user.email", "test@example.com", cwd=EFFECT_REPO)
_git("config", "user.name", "test", cwd=EFFECT_REPO)
with open(os.path.join(EFFECT_REPO, "seed.txt"), "w") as fh:
    fh.write("seed\n")
_git("add", "-A", cwd=EFFECT_REPO)
_git("commit", "-q", "-m", "seed", cwd=EFFECT_REPO)


def run_with_roots(entries, roots, stop_active=False):
    env_extra = {"WORKFLOW_OUTPUT_REPO_ROOTS": roots}
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("\n".join(entries))
        path = fh.name
    env = dict(os.environ)
    env.update(env_extra)
    env["WORKFLOW_OUTPUT_REPOS_CONF"] = CONF_PATH
    try:
        payload = {"transcript_path": path, "stop_hook_active": stop_active}
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        out = (p.stdout or "").strip()
        return json.loads(out) if out else None
    finally:
        os.unlink(path)


# MUST NOT FIRE: no Write/Edit tool_use at all, but the pinned repo root has an
# UNCOMMITTED change on disk -- exactly what a Bash heredoc or a subagent write leaves
# behind and the old transcript-only scan could never see.
with open(os.path.join(EFFECT_REPO, "seed.txt"), "a") as fh:
    fh.write("changed by the effect check test\n")
r = run_with_roots([
    user_msg("audit via bash heredoc"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "Wrote findings via a heredoc, no Edit "
                         "tool_use block for it."}]),
], roots=EFFECT_REPO)
results.append(check("effect check: uncommitted repo change with NO tracked write -> quiet", r,
                     False))

# Reset the repo to clean (revert the change above) before the negative control.
_git("checkout", "--", "seed.txt", cwd=EFFECT_REPO)

# MUST FIRE: same pinned repo root, but genuinely clean -- the effect check must not
# invent a change that is not there.
r = run_with_roots([
    user_msg("audit via bash heredoc"),
    entry("assistant", [{"type": "tool_use", "name": "Workflow", "input": {}}]),
    entry("assistant", [{"type": "text", "text": "Ran the audit, wrote nothing anywhere."}]),
], roots=EFFECT_REPO)
results.append(check("effect check: repo genuinely clean -> BLOCKS", r, True))

os.unlink(CONF_PATH)

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
