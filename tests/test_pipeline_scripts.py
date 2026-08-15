#!/usr/bin/env python3
"""merge_fragments.py / apply_verdicts.py / render_scaffold.py checked.

Runs the whole way through from mock fragments: build the ledger, apply the verdicts,
and generate the report skeleton.
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

# What render_scaffold.py leaves in an analysis section for the writer (labels.py's
# "placeholder"). Filling it in is what clears R-NOEVIDENCE.
PLACEHOLDER = "<!-- Write here. Take every fact from the slices under kq_slices/, re-read. -->"


def check(label, cond, detail=""):
    print(("  OK   " if cond else "  NG   ") + label + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(label)


def run(script, *args):
    cp = subprocess.run([PY, os.path.join(SCRIPTS, script), *args],
                        capture_output=True, text=True, encoding="utf-8")
    return cp.returncode, cp.stdout, cp.stderr


def evidence(tmp_id, kq, cluster, url, key=False, corr="single_source", cids=None):
    return {
        "id": tmp_id, "kq_ids": [kq],
        "claim": f"a falsifiable proposition about {kq} ({tmp_id})",
        "claim_type": "fact", "verbatim_quote": f"quote for {tmp_id}",
        "source": {"publisher": "Publisher", "title": f"Title {tmp_id}", "url": url,
                   "published": "2025-04-01", "grade": "A", "origin_cluster": cluster},
        "accessed": "2026-07-25", "is_key_figure": key, "corroboration": corr,
        "corroborating_ids": cids or [],
    }


def make_fragments(run_dir):
    frag_dir = os.path.join(run_dir, "evidence_fragments")
    os.makedirs(frag_dir, exist_ok=True)
    f1 = {
        "kq_id": "KQ1",
        "evidence": [
            evidence("tmp-1", "KQ1", "KQ1-1", "https://a.example/1",
                     key=True, corr="corroborated", cids=["tmp-2"]),
            evidence("tmp-2", "KQ1", "KQ1-2", "https://b.example/1",
                     key=True, corr="corroborated", cids=["tmp-1"]),
            # required fields missing
            {"id": "tmp-broken", "kq_ids": ["KQ1"], "claim": "a broken evidence unit"},
        ],
        "search_log": [{"query": "q1", "tool": "WebSearch", "kind": "normal", "adopted": 2},
                       {"query": "q1c", "tool": "WebSearch", "kind": "counter", "adopted": 0}],
        "disconfirmation": [{"hypothesis": "H1", "expected_if_false": "a disconfirming fact",
                             "queries": ["q1c"], "found": "nothing was found"}],
        "gaps": [{"claim": "an unresolved point", "tried_queries": ["q9"],
                  "recommended": "further research"}],
        "floor_status": {"met": True},
    }
    f2 = {
        "kq_id": "KQ2",
        "evidence": [evidence("tmp-1", "KQ2", "KQ2-1", "https://c.example/1")],
        "search_log": [{"query": "q2", "tool": "WebSearch", "kind": "normal", "adopted": 1}],
        "disconfirmation": [],
        "gaps": [],
        "floor_status": {"met": False, "reason": "short of the floor"},
    }
    for name, data in (("kq1_collector.json", f1), ("kq2_scholar.json", f2)):
        with open(os.path.join(frag_dir, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    brief = os.path.join(run_dir, "research_brief.md")
    with open(brief, "w", encoding="utf-8") as fh:
        fh.write("# Plan\n\n- KQ1: Is the market growing\n"
                 "- KQ2: What blocks it in practice\n")
    return brief


def main():
    tmp = tempfile.mkdtemp(prefix="rt-pipeline-")
    run_dir = os.path.join(tmp, "run")
    os.makedirs(run_dir)
    try:
        brief = make_fragments(run_dir)

        print("[merge_fragments]")
        rc, out, err = run("merge_fragments.py", "--run-dir", run_dir, "--brief", brief,
                           "--mode", "STANDARD", "--as-of", "2026-07-25",
                           "--topic", "test topic", "--json")
        check("a broken evidence unit makes it exit 1", rc == 1, f"rc={rc} err={err[:200]}")
        summary = json.loads(out)
        log = json.load(open(os.path.join(run_dir, "evidence_log.json"), encoding="utf-8"))
        ids = [e["id"] for e in log["evidence"]]
        check("the real IDs are numbered in arrival order", ids == ["E1", "E2", "E3"], str(ids))
        check("corroborating_ids are mapped onto the real IDs",
              log["evidence"][0]["corroborating_ids"] == ["E2"]
              and log["evidence"][1]["corroborating_ids"] == ["E1"],
              str([e["corroborating_ids"] for e in log["evidence"]]))
        check("every search_log row carries a kq_id",
              all(r.get("kq_id") for r in log["search_log"]) and len(log["search_log"]) == 3,
              str(log["search_log"]))
        check("the disconfirmation records are merged", len(log["disconfirmation"]) == 1)
        check("the gaps are merged", len(log["gaps"]) == 1)
        check("the KQs come from the brief",
              [k["id"] for k in log["key_questions"]] == ["KQ1", "KQ2"]
              and "market" in log["key_questions"][0]["text"], str(log["key_questions"]))
        unmerged = json.load(open(os.path.join(run_dir, "unmerged_report.json"), encoding="utf-8"))
        check("the broken unit goes to unmerged_report",
              len(unmerged["evidence"]) == 1
              and unmerged["evidence"][0]["tmp_id"] == "tmp-broken", str(unmerged))
        check("the rest is taken in", summary["evidence_merged"] == 3)

        # The same input a second time produces the same ledger
        run("merge_fragments.py", "--run-dir", run_dir, "--brief", brief,
            "--mode", "STANDARD", "--as-of", "2026-07-25", "--topic", "test topic", "--json")
        log2 = json.load(open(os.path.join(run_dir, "evidence_log.json"), encoding="utf-8"))
        check("a rerun produces the same ledger", log == log2)

        print("[evidence_auditor over the merged ledger]")
        rc, out, err = run("evidence_auditor.py", os.path.join(run_dir, "evidence_log.json"),
                           "--mode", "STANDARD", "--json")
        res = json.loads(out)
        bad = [f for f in res["findings"]
               if f["severity"] == "FAIL" and not f["code"].startswith("E-FLOOR")]
        check("no structural FAIL (the floors aside)", not bad,
              str([f["code"] for f in bad]))

        print("[apply_verdicts]")
        vdir = os.path.join(run_dir, "verification")
        os.makedirs(vdir, exist_ok=True)
        with open(os.path.join(vdir, "verdicts_1.json"), "w", encoding="utf-8") as fh:
            json.dump({"verdicts": [
                {"id": "E1", "verdict": "confirmed", "note": "corroborated independently",
                 "confidence_band": "almost certain (90-100%)",
                 "corroboration": {"status": "corroborated"}},
                {"id": "E2", "verdict": "disputed", "note": "the sources conflict",
                 "corroboration": {"status": "conflicting"}},
            ]}, fh, ensure_ascii=False)
        with open(os.path.join(vdir, "verdicts_2.json"), "w", encoding="utf-8") as fh:
            json.dump({"verdicts": [
                {"id": "E99", "verdict": "confirmed"},      # not in the ledger
                {"id": "E3", "verdict": "very good"},       # invalid status
            ]}, fh, ensure_ascii=False)

        rc, out, err = run("apply_verdicts.py", os.path.join(run_dir, "evidence_log.json"),
                           "--verdicts-dir", vdir, "--expected", "E1,E2,E3", "--json")
        r = json.loads(out)
        check("errors make it exit 1", rc == 1, f"rc={rc}")
        check("only the sound verdicts are applied",
              sorted(r["applied"]) == ["E1", "E2"], str(r["applied"]))
        check("an unknown ID and an invalid status go to errors",
              len(r["errors"]) == 2, str(r["errors"]))
        check("a target with no verdict goes to missing", r["missing"] == ["E3"],
              str(r["missing"]))
        check("a rewritten corroboration is recorded in changes",
              any(c["field"] == "corroboration" and c["id"] == "E2" for c in r["changes"]),
              str(r["changes"]))
        log3 = json.load(open(os.path.join(run_dir, "evidence_log.json"), encoding="utf-8"))
        e1 = next(e for e in log3["evidence"] if e["id"] == "E1")
        check("the verdict lands in verification",
              e1["verification"]["status"] == "confirmed"
              and e1["verification"]["confidence_band"] == "almost certain (90-100%)",
              str(e1["verification"]))

        rc, out, err = run("evidence_auditor.py", os.path.join(run_dir, "evidence_log.json"),
                           "--mode", "STANDARD", "--json")
        res = json.loads(out)
        bad = [f for f in res["findings"]
               if f["severity"] == "FAIL" and not f["code"].startswith("E-FLOOR")]
        check("the ledger still passes the structural check", not bad,
              str([f["code"] for f in bad]))

        print("[render_scaffold]")
        out_md = os.path.join(run_dir, "report.md")
        rc, out, err = run("render_scaffold.py", os.path.join(run_dir, "evidence_log.json"),
                           "--out", out_md, "--slices", os.path.join(run_dir, "kq_slices"),
                           "--json")
        check("it exits cleanly", rc == 0, f"rc={rc} err={err[:200]}")
        s = json.loads(out)
        text = open(out_md, encoding="utf-8").read()
        src_lines = [l for l in text.splitlines() if l.startswith("- [E")]
        check("the source list has one line per evidence unit",
              len(src_lines) == len(log3["evidence"]), f"{len(src_lines)} lines")
        log_rows = text.split("## Search log")[1].split("## Sources")[0]
        body_rows = [l for l in log_rows.splitlines()
                     if l.startswith("|") and not l.startswith("|---")
                     and "| Query |" not in l]
        check("the search-log table has one row per search_log row",
              len(body_rows) == len(log3["search_log"]), f"{len(body_rows)} rows")
        check("the independent-source count is filled in",
              f"Independent sources: {s['independent_sources']}" in text)
        check("the per-KQ slices and the cross-cutting slice are written",
              len(s["slices"]) == 3 and all(os.path.isfile(p) for p in s["slices"])
              and s["slices"][-1].endswith("cross_cutting.md"), str(s["slices"]))
        kq1 = open(s["slices"][0], encoding="utf-8").read()
        check("a slice's source line carries no URL and no cluster",
              "https://" not in kq1 and "cluster" not in kq1, kq1[:200])
        check("a slice carries only its own KQ's disconfirmation records",
              "## Disconfirmation recorded while collecting for this KQ" in kq1
              and "## Disconfirmation recorded while collecting for this KQ" not in
              open(s["slices"][1], encoding="utf-8").read())
        check("a KQ section gets the evidence table and the confidence ceiling",
              "| Evidence | Claim | Grade | Corroboration | Verification |" in text
              and "Confidence ceiling (computed)" in text)
        check("the generated region of the disconfirmation section is marked off",
              "<!-- generated:disconfirmation -->" in text
              and "<!-- /generated:disconfirmation -->" in text)
        check("the verification breakdown is in the header",
              "Verification breakdown: confirmed" in text)

        rc, out, err = run("report_auditor.py", out_md,
                           "--evidence", os.path.join(run_dir, "evidence_log.json"), "--json")
        f = json.loads(out)["findings"]
        sec = [x for x in f if x["code"].startswith("R-SEC")]
        check("the skeleton holds every required section", not sec,
              str([x["code"] for x in sec]))
        check("empty analysis sections raise R-NOEVIDENCE",
              any(x["code"] == "R-NOEVIDENCE" for x in f), str([x["code"] for x in f]))

        # A draft carrying only the generated table and no analysis keeps R-COUNTER-EMPTY
        check("the generated table alone does not satisfy the disconfirmation check",
              any(x["code"] == "R-COUNTER-EMPTY" for x in f), str([x["code"] for x in f]))

        # Filling the analysis sections clears R-NOEVIDENCE
        filled = text.replace(f"## Summary\n\n{PLACEHOLDER}",
                              "## Summary\n\nThe key figure was confirmed [E1].")
        filled = filled.replace("## Disconfirmation and conflicting evidence\n\n",
                                "## Disconfirmation and conflicting evidence\n\n"
                                "The disconfirmation search found nothing.\n\n", 1)
        with open(out_md, "w", encoding="utf-8") as fh:
            fh.write(filled)
        rc, out, err = run("report_auditor.py", out_md,
                           "--evidence", os.path.join(run_dir, "evidence_log.json"), "--json")
        f = json.loads(out)["findings"]
        check("filling it clears R-NOEVIDENCE",
              not any(x["code"] == "R-NOEVIDENCE" for x in f))
        check("the writer's own lines clear R-COUNTER-EMPTY",
              not any(x["code"] == "R-COUNTER-EMPTY" for x in f),
              str([x["code"] for x in f]))

        print("[render_scaffold does not overwrite]")
        before = open(out_md, encoding="utf-8").read()
        rc, out, err = run("render_scaffold.py", os.path.join(run_dir, "evidence_log.json"),
                           "--out", out_md, "--slices", os.path.join(run_dir, "kq_slices"))
        check("an existing output makes it exit 2", rc == 2, f"rc={rc}")
        check("the writing already done survives",
              open(out_md, encoding="utf-8").read() == before)
        rc, out, err = run("render_scaffold.py", os.path.join(run_dir, "evidence_log.json"),
                           "--out", out_md, "--slices", os.path.join(run_dir, "kq_slices"),
                           "--force")
        check("--force overwrites",
              rc == 0 and open(out_md, encoding="utf-8").read() != before, f"rc={rc}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
