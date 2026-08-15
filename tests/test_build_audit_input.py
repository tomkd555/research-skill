#!/usr/bin/env python3
"""build_audit_input.py checked.

Covers the digest carrying only what the audit needs, the sampling being an even spacing
over the evidence IDs, and only the body's citations counting.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")
PY = sys.executable
FAILURES = []


def check(label, cond, detail=""):
    print(("  OK   " if cond else "  NG   ") + label + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(label)


def run(log_path, report_path, run_dir, mode):
    cp = subprocess.run(
        [PY, os.path.join(SCRIPTS, "build_audit_input.py"), log_path,
         "--report", report_path, "--run-dir", run_dir, "--mode", mode, "--json"],
        capture_output=True, text=True, encoding="utf-8")
    return cp.returncode, json.loads(cp.stdout)


def ev(n, key=False):
    return {
        "id": f"E{n}", "kq_ids": ["KQ1"], "claim": f"a falsifiable proposition (E{n})",
        "claim_type": "fact", "verbatim_quote": f"quote {n}",
        "source": {"publisher": "Publisher", "title": f"t{n}", "url": f"https://example.com/{n}",
                   "published": "2025", "grade": "A", "origin_cluster": f"c{n}"},
        "accessed": "2026-07-25", "is_key_figure": key, "corroboration": "single_source",
        "corroborating_ids": [],
    }


def main():
    tmp = tempfile.mkdtemp(prefix="rt-audit-input-")
    run_dir = os.path.join(tmp, "run")
    os.makedirs(run_dir)
    try:
        log = {
            "topic": "the topic", "as_of": "2026-07-25", "mode": "DEEP",
            "languages": ["ja", "en"],
            "key_questions": [{"id": "KQ1", "text": "the question"}],
            "evidence": [ev(i, key=(i in (1, 2))) for i in range(1, 21)],
            "disconfirmation": [{"hypothesis": "H1", "expected_if_false": "x",
                                 "queries": ["q"], "found": "nothing was found"}],
            "search_log": [{"query": f"q{i}", "language": "ja", "tool": "WebSearch",
                            "kind": "normal", "adopted": 0} for i in range(200)],
            "gaps": [{"claim": "unresolved", "tried_queries": ["q"],
                      "recommended": "further research"}],
        }
        log_path = os.path.join(run_dir, "evidence_log.json")
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(log, fh, ensure_ascii=False)

        body = "\n".join(f"A fact about KQ1 [E{i}]." for i in range(1, 21))
        report = ("# Report\n\n## Summary\n\n" + body
                  + "\n\n## Sources\n\n"
                  + "\n".join(f"- [E{i}] Publisher. https://example.com/{i}"
                              for i in range(1, 21)))
        report_path = os.path.join(run_dir, "report.md")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report)

        print("[digest]")
        rc, res = run(log_path, report_path, run_dir, "DEEP")
        check("it exits cleanly", rc == 0, f"rc={rc}")
        digest = json.load(open(os.path.join(run_dir, "audit_digest.json"), encoding="utf-8"))
        check("the search log is left out", "search_log" not in digest, str(sorted(digest)))
        check("the whole evidence list is left out", "evidence" not in digest,
              str(sorted(digest)))
        check("the key figures are listed",
              [k["id"] for k in digest["key_figures"]] == ["E1", "E2"],
              str(digest["key_figures"]))
        check("the disconfirmation records and the gaps are carried",
              len(digest["disconfirmation"]) == 1 and len(digest["gaps"]) == 1)
        check("only the search-log count survives", digest["counts"]["search_log"] == 200)

        print("[sampling]")
        sample = json.load(open(os.path.join(run_dir, "audit_sample.json"), encoding="utf-8"))
        check("DEEP samples 10", sample["picked"] == 10, str(sample["picked"]))
        check("the spacing over the evidence IDs is even",
              [i["id"] for i in sample["items"]]
              == ["E1", "E3", "E5", "E7", "E9", "E11", "E13", "E15", "E17", "E19"],
              str([i["id"] for i in sample["items"]]))
        check("the evidence unit comes through in full",
              sample["items"][0]["evidence"]["verbatim_quote"] == "quote 1")
        check("the report line citing it comes too",
              sample["items"][0]["report_lines"][0]["text"].endswith("[E1].")
              and len(sample["items"][0]["report_lines"]) == 1,
              str(sample["items"][0]["report_lines"]))

        rc, res = run(log_path, report_path, run_dir, "STANDARD")
        sample = json.load(open(os.path.join(run_dir, "audit_sample.json"), encoding="utf-8"))
        check("STANDARD samples 5", sample["picked"] == 5, str(sample["picked"]))

        print("[only the body's citations count]")
        thin = ("# Report\n\n## Summary\n\nA fact about KQ1 [E1].\n\n## Sources\n\n"
                + "\n".join(f"- [E{i}] Publisher. https://example.com/{i}"
                            for i in range(1, 21)))
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(thin)
        rc, res = run(log_path, report_path, run_dir, "DEEP")
        check("a reference from the source list is not counted", res["cited_total"] == 1,
              str(res["cited_total"]))
        check("short of the sample size it exits 1", rc == 1, f"rc={rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
