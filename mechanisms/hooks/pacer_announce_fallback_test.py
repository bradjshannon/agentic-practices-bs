#!/usr/bin/env python3
"""Exercise pacer_announce.py's status-link resolution for real, in a sandboxed HOME.

Runs the ACTUAL hook as a subprocess (stdin payload -> stdout injection) three times, to show the
whole fallback chain still behaves as designed after the scrub:
  A. pacer-armed.json carries status_url        -> that wins
  B. no status_url, CONDUCTOR_STATUS_URL set    -> env var wins
  C. neither                                    -> DEFAULT_LINK (the non-routable placeholder)
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOOK = Path(sys.argv[1]).resolve()


def run(case, status_url, env_url):
    home = Path(tempfile.mkdtemp(prefix=f"fakehome-{case}-"))
    (home / ".claude").mkdir(parents=True)
    cwd = home / "Documents" / "GitHub" / "conductor-bs"
    cwd.mkdir(parents=True)
    fires_at = datetime.now(timezone.utc).isoformat()
    state = {"fires_at": fires_at, "cwd": str(cwd)}
    if status_url:
        state["status_url"] = status_url
    (home / ".claude" / "pacer-armed.json").write_text(json.dumps(state), encoding="utf-8")

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("CONDUCTOR_STATUS_URL", None)
    if env_url:
        env["CONDUCTOR_STATUS_URL"] = env_url

    p = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"session_id": "exercise", "prompt": "x"}),
        capture_output=True, text=True, env=env,
    )
    print(f"--- case {case} (exit {p.returncode}) ---")
    print(p.stdout.strip() or "(no stdout)")
    if p.stderr.strip():
        print("STDERR:", p.stderr.strip())
    return p.stdout


a = run("A-state", "https://from-state.example:1234/", None)
b = run("B-env", None, "https://from-env.example:5678/")
c = run("C-default", None, None)

ok = (
    "https://from-state.example:1234/" in a
    and "https://from-env.example:5678/" in b
    and "https://conductor-status.invalid:9443/" in c
)
print()
print("FALLBACK CHAIN INTACT" if ok else "FALLBACK CHAIN BROKEN")
sys.exit(0 if ok else 1)
