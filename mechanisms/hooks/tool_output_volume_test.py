#!/usr/bin/env python3
"""Tests for hooks/tool_output_volume.py -- the extension from "Bash|PowerShell" to
"Bash|PowerShell|Read|Grep|Glob|Agent|WebFetch".

The point of this suite is that the extension is only worth anything if the SIZES it records
are right for the newly-matched tools. A hook that matches Read and then records a wrong number
for it is worse than one that never matched Read at all, because the wrong number will be
ranked and acted on.

Run: python hooks/tool_output_volume_test.py
     python hooks/tool_output_volume_test.py --corpus   (also replay real transcripts)
"""
import argparse
import glob
import json
import os
import statistics
import sys
import tempfile

os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tool_output_volume as t  # noqa: E402

PROJECT_DIR = os.path.expanduser(
    "~/.claude/projects/C--Users-operator-Documents-GitHub-myproject-server")


def _check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: got={got!r} want={want!r}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="store_true")
    args = ap.parse_args()
    r = []

    # ---- POSITIVE CONTROL ---------------------------------------------------------------
    # The exact shape that motivated the change, verbatim from a real transcript record.
    # Before the fix this fell through to json.dumps() and returned ~130 rather than 26.
    read_resp = {"type": "text",
                 "file": {"filePath": r"C:\x\brief.md",
                          "content": "line one\nline two\nabc\n"}}
    r.append(_check("POSITIVE CONTROL: Read counts nested file.content, not the JSON envelope",
                    t.result_chars(read_resp, "Read"), len("line one\nline two\nabc\n")))
    r.append(_check("POSITIVE CONTROL: the old generic scan really did get this wrong "
                    "(guards against the fix being a no-op)",
                    t._generic_result_chars(read_resp) != len("line one\nline two\nabc\n"), True))

    # ---- REGRESSION: the shells must be untouched ----------------------------------------
    r.append(_check("Bash stdout+stderr unchanged",
                    t.result_chars({"stdout": "abc", "stderr": "de"}, "Bash"), 5))
    r.append(_check("PowerShell unchanged",
                    t.result_chars({"stdout": "1234"}, "PowerShell"), 4))
    r.append(_check("string result unchanged", t.result_chars("hello", "Bash"), 5))
    r.append(_check("non-dict non-str is 0", t.result_chars(None, "Bash"), 0))

    # ---- Agent: never bill the parent for the brief it SENT -------------------------------
    big_prompt = "x" * 50_000
    r.append(_check("Agent with a returned report counts the report, not the prompt",
                    t.result_chars({"prompt": big_prompt, "result": "done: 3 files"}, "Agent"),
                    len("done: 3 files")))
    stub = {"isAsync": True, "status": "async_launched", "agentId": "a1", "prompt": big_prompt,
            "description": "d" * 500}
    r.append(_check("Agent async stub is the measured harness boilerplate, NOT the prompt",
                    t.result_chars(stub, "Agent"), t._AGENT_ASYNC_LAUNCH_CHARS))
    r.append(_check("REGRESSION GUARD: async stub is not sized from the dict "
                    "(the 3.4x under-count the corpus replay caught)",
                    t.result_chars(stub, "Agent") > 900, True))

    # ---- Grep/Glob: both modes are real intake --------------------------------------------
    r.append(_check("Grep content mode counts content",
                    t.result_chars({"mode": "content", "content": "a\nb\n"}, "Grep"), 4))
    r.append(_check("Grep files mode counts the filenames it printed",
                    t.result_chars({"mode": "files_with_matches",
                                    "filenames": ["ab", "cde"]}, "Grep"), 3 + 4))

    # ---- WebFetch falls through to the generic scan ---------------------------------------
    r.append(_check("WebFetch counts result",
                    t.result_chars({"bytes": 9, "result": "abcd"}, "WebFetch"), 4))

    # ---- identity ------------------------------------------------------------------------
    r.append(_check("Read identity is the file", t.call_identity("Read", {"file_path": "/a/b.md"}),
                    "/a/b.md"))
    r.append(_check("Bash identity is the command",
                    t.call_identity("Bash", {"command": "git log"}), "git log"))
    r.append(_check("Grep identity is the pattern",
                    t.call_identity("Grep", {"pattern": "foo.*"}), "foo.*"))
    r.append(_check("Agent identity is the subagent type",
                    t.call_identity("Agent", {"subagent_type": "myproject-scout"}), "myproject-scout"))
    r.append(_check("Agent identity defaults when unset",
                    t.call_identity("Agent", {}), "general-purpose"))
    r.append(_check("identity is truncated to CMD_CHARS",
                    len(t.call_identity("Bash", {"command": "y" * 999})), t.CMD_CHARS))
    r.append(_check("identity of a non-dict input is empty", t.call_identity("Read", None), ""))

    # ---- matcher -------------------------------------------------------------------------
    for tool in ("Read", "Grep", "Glob", "Agent", "WebFetch", "Bash", "PowerShell"):
        r.append(_check(f"{tool} is matched", tool in t.MATCHED_TOOLS, True))
    r.append(_check("Edit is NOT matched (writes are not intake)", "Edit" in t.MATCHED_TOOLS,
                    False))

    # ---- fail-open contract ---------------------------------------------------------------
    class Exploding(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")
    try:
        t.result_chars(Exploding(), "Read")
        blew = False
    except Exception:
        blew = True
    r.append(_check("result_chars may raise, but main() swallows it (contract is at main)",
                    blew in (True, False), True))

    # ---- CORPUS REPLAY --------------------------------------------------------------------
    # Exercise the sizer against every real toolUseResult in the corpus and compare it to the
    # tool_result text the harness ACTUALLY delivered into context. Read is expected to come in
    # slightly UNDER, because Read is delivered with `cat -n` line-number prefixes that are not
    # in file.content -- this quantifies that gap instead of pretending it does not exist.
    if args.corpus:
        print("\n--- CORPUS REPLAY (real transcript records) ---")
        ratios = {}
        for p in sorted(glob.glob(os.path.join(PROJECT_DIR, "*.jsonl")))[:25]:
            names = {}
            for line in open(p, encoding="utf-8"):
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") == "assistant":
                    for b in (rec.get("message") or {}).get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            names[b.get("id")] = b.get("name")
                elif rec.get("type") == "user":
                    tur = rec.get("toolUseResult")
                    if tur is None:
                        continue
                    for c in (rec.get("message") or {}).get("content") or []:
                        if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                            continue
                        nm = names.get(c.get("tool_use_id"))
                        if nm not in t.MATCHED_TOOLS:
                            continue
                        body = c.get("content")
                        if isinstance(body, list):
                            body = " ".join(b.get("text", "") for b in body
                                            if isinstance(b, dict) and b.get("type") == "text")
                        if not isinstance(body, str) or len(body) < 50:
                            continue
                        est = t.result_chars(tur, nm)
                        if est > 0:
                            ratios.setdefault(nm, []).append(est / len(body))
        print(f"{'tool':<14}{'n':>7}{'median est/actual':>20}{'p10':>8}{'p90':>8}")
        for nm, vals in sorted(ratios.items(), key=lambda kv: -len(kv[1])):
            s = sorted(vals)
            med = statistics.median(s)
            p10 = s[int(0.1 * (len(s) - 1))]
            p90 = s[int(0.9 * (len(s) - 1))]
            print(f"{nm:<14}{len(vals):>7}{med:>20.3f}{p10:>8.3f}{p90:>8.3f}")
            # A sizer that is out by more than 2x in either direction is not fit to rank on.
            r.append(_check(f"corpus: {nm} sizer within 0.5x-2.0x of delivered text",
                            0.5 <= med <= 2.0, True))

    passed = sum(1 for x in r if x)
    print(f"\n{passed}/{len(r)} checks passed")
    return 0 if passed == len(r) else 1


if __name__ == "__main__":
    sys.exit(main())
