#!/usr/bin/env python3
"""Regression tests for the checks added to evidence_auditor.py and report_auditor.py.

Each code is exercised twice: on the smallest ledger or report that violates it, and on
the pair that does not, so a check that fires on everything fails here.
"""
import copy
import importlib.util
import json
import os
import sys

SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")


def load(name):
    path = os.path.join(SKILL_SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ea = load("evidence_auditor")
ra = load("report_auditor")

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  OK   {label}")
    else:
        print(f"  NG   {label} {detail}")
        FAILURES.append(label)


def codes(findings, code):
    return [f for f in findings if f["code"] == code]


# ---------------------------------------------------------------- evidence_auditor

def test_key_cluster():
    print("[E-KEY-CLUSTER] a key figure needs two independent clusters")
    base = copy.deepcopy(ea.SAMPLE)

    good = ea.Auditor(base, base.get("mode", "STANDARD")).run()
    check("two independent clusters pass", not codes(good, "E-KEY-CLUSTER"),
          detail=str(codes(good, "E-KEY-CLUSTER")))

    bad = copy.deepcopy(base)
    # Put E2 in E1's origin cluster: a reprint counted as corroboration.
    for e in bad["evidence"]:
        if e["id"] == "E2":
            e["source"]["origin_cluster"] = "src-a"
    found = ea.Auditor(bad, bad.get("mode", "STANDARD")).run()
    hits = codes(found, "E-KEY-CLUSTER")
    check("one cluster only fails", len(hits) == 2 and all(h["severity"] == "FAIL" for h in hits),
          detail=f"{len(hits)} hits")


def slog(kq, role, kind, n):
    return [{"query": f"{kq}-{role}-{kind}-{i}", "tool": "WebSearch",
             "kind": kind, "adopted": 0, "kq_id": kq, "role": role} for i in range(n)]


def full_role_rows(role):
    """One role's search log, meeting DEEP's floors exactly (12 queries, 2 disconfirming)."""
    return slog("KQ1", role, "normal", 10) + slog("KQ1", role, "counter", 2)


def floor_log(mode, rows, statuses):
    return {
        "schema": "research-evidence-1.2", "topic": "The topic", "as_of": "2026-07-25",
        "mode": mode,
        "key_questions": [{"id": "KQ1", "text": "Does it hold?"}],
        "evidence": [], "search_log": rows, "gaps": [], "floor_status": statuses,
        "disconfirmation": [{"hypothesis": "H1", "expected_if_false": "x",
                             "queries": ["q"], "found": "nothing of the kind"}],
    }


def floor_codes(findings):
    return sorted({f["code"] for f in findings if f["code"].startswith("E-FLOOR")
                   and f["code"] != "E-FLOOR-SOURCE"})


def test_floor_units():
    print("[E-FLOOR-*] the unit the floors apply to, per mode")
    both = {"kq_id": "KQ1", "role": "collector", "met": True}
    scholar_status = {"kq_id": "KQ1", "role": "scholar", "met": True}

    rows = full_role_rows("collector") + full_role_rows("scholar")
    f = ea.Auditor(floor_log("DEEP", rows, [both, scholar_status])).run()
    check("DEEP: both roles meeting their own floors pass", not floor_codes(f), str(floor_codes(f)))

    # The scholar ran no query at all; only its fragment's floor_status is left.
    only_collector = full_role_rows("collector")
    f = ea.Auditor(floor_log("DEEP", only_collector, [both, scholar_status])).run()
    hits = [x for x in f if x["code"] == "E-FLOOR-QUERY" and "scholar" in x["message"]]
    check("DEEP: a scholar on zero queries fails per role",
          hits and all(x["severity"] == "FAIL" for x in hits), str(floor_codes(f)))

    f = ea.Auditor(floor_log("STANDARD", only_collector, [both, scholar_status])).run()
    check("STANDARD: the total across roles meets the floor",
          not [x for x in f if x["code"] == "E-FLOOR-QUERY"], str(floor_codes(f)))
    check("STANDARD: a scholar on zero queries fails the per-role minimum",
          [x for x in f if x["code"] == "E-FLOOR-ROLE-QUERY" and "scholar" in x["message"]],
          str(floor_codes(f)))

    # One query short of the floor is still short.
    short = slog("KQ1", "scholar", "normal", 9) + slog("KQ1", "scholar", "counter", 2)
    f = ea.Auditor(floor_log("DEEP", full_role_rows("collector") + short,
                             [both, scholar_status])).run()
    check("DEEP: a role one query short fails",
          [x for x in f if x["code"] == "E-FLOOR-QUERY" and "scholar" in x["message"]],
          str(floor_codes(f)))


# ---------------------------------------------------------------- report_auditor

def build_log():
    """The ledger for report_auditor: E1/E2 corroborated, E3 thin, E4/E5 conflicting."""
    return {
        "key_questions": [{"id": "KQ1", "text": "?"}],
        "evidence": [
            {"id": "E1", "corroboration": "corroborated", "corroborating_ids": ["E2"],
             "verification": {"status": "confirmed"}},
            {"id": "E2", "corroboration": "corroborated", "corroborating_ids": ["E1"],
             "verification": {"status": "confirmed"}},
            {"id": "E3", "corroboration": "single_source", "corroborating_ids": [],
             "verification": {"status": "plausible"}},
            {"id": "E4", "corroboration": "conflicting", "corroborating_ids": ["E5"],
             "verification": {"status": "confirmed"}},
            {"id": "E5", "corroboration": "conflicting", "corroborating_ids": ["E4"],
             "verification": {"status": "confirmed"}},
        ],
        "gaps": [],
    }


CLEAN_REPORT = """# Research report

as_of: 2026-07-25

## Answer to the decision
- Answer: the figure is holding at 12,000 cases [E1]
- Recommendation: keep to the current course
- Confidence: likely (65-80%)
- What would overturn it: the second series staying below the current level

## Summary
The headline figure is holding at 12,000 cases [E1]. We put that at likely (65-80%).

## KQ1 conclusion
On KQ1, the figure stands at 12,000 cases [E1][E2].
A second series puts it at 9,000 cases [E4]. The gap comes from a difference of definition [E5].
The supplementary figure is reportedly 62% [E3].

## Disconfirmation and conflicting evidence
No report showing the opposite turned up. Three disconfirming queries were run.

## Limitations and evidence gaps
Self-verification is unstable without an outside check.

## KQ coverage
| KQ | Key evidence | Verification |
|---|---|---|
| KQ1 | E1, E2 | confirmed |

## Search log
| Query | Language |
|---|---|
| q1 | en |

## Sources
- [E1] Publisher. https://example.com/a
"""


def run_report(text, log=None, citation=None):
    return ra.audit(text, log or build_log(), citation)[0]


def test_clean():
    print("[baseline] a report that violates nothing")
    f = run_report(CLEAN_REPORT)
    for code in ("R-THIN", "R-CONFLICT-PAIR", "R-COUNTER-EMPTY", "R-POINT", "R-KQ2"):
        check(f"{code} is not raised", not codes(f, code), detail=str(codes(f, code)))
    fails = [x for x in f if x["severity"] == "FAIL"]
    check("no FAIL at all", not fails, detail=str([x["code"] for x in fails]))


def test_thin():
    print("[R-THIN] a claim on thin evidence stated as fact")
    bad = CLEAN_REPORT.replace("The supplementary figure is reportedly 62% [E3].",
                               "The supplementary figure is 62% [E3].")
    f = run_report(bad)
    check("stated as fact fails", len(codes(f, "R-THIN")) == 1, detail=str(codes(f, "R-THIN")))
    check("a qualifier clears it", not codes(run_report(CLEAN_REPORT), "R-THIN"))

    labelled = CLEAN_REPORT.replace(
        "The supplementary figure is reportedly 62% [E3].",
        "The supplementary figure is 62%, which we put at likely (65-80%) [E3].")
    check("a confidence label clears it", not codes(run_report(labelled), "R-THIN"))


def test_conflict_pair():
    print("[R-CONFLICT-PAIR] both sides of a conflict")
    bad = CLEAN_REPORT.replace(" The gap comes from a difference of definition [E5].", "")
    f = run_report(bad)
    check("citing one side alone fails", len(codes(f, "R-CONFLICT-PAIR")) == 1,
          detail=str(codes(f, "R-CONFLICT-PAIR")))


def test_counter_empty():
    print("[R-COUNTER-EMPTY] the disconfirmation section has a body")
    bad = CLEAN_REPORT.replace(
        "No report showing the opposite turned up. Three disconfirming queries were run.\n", "")
    f = run_report(bad)
    check("a heading with nothing under it fails", len(codes(f, "R-COUNTER-EMPTY")) == 1,
          detail=str(codes(f, "R-COUNTER-EMPTY")))


def test_point_and_band():
    print("[R-POINT / R-BAND] point estimates and probability bands")
    bad = CLEAN_REPORT.replace("We put that at likely (65-80%).",
                               "We put the confidence at 75%.")
    f = run_report(bad)
    check("a point estimate fails", len(codes(f, "R-POINT")) == 1, detail=str(codes(f, "R-POINT")))

    nb = CLEAN_REPORT.replace("We put that at likely (65-80%).", "We put that at likely.")
    f2 = run_report(nb)
    check("a label with no band warns", any(x["severity"] == "WARN" for x in codes(f2, "R-BAND")),
          detail=str(codes(f2, "R-BAND")))


def test_kq2():
    print("[R-KQ2] a heading and a coverage row per KQ")
    no_head = CLEAN_REPORT.replace("## KQ1 conclusion", "## Conclusion")
    check("no KQ heading fails", len(codes(run_report(no_head), "R-KQ2")) == 1,
          detail=str(codes(run_report(no_head), "R-KQ2")))
    no_row = CLEAN_REPORT.replace("| KQ1 | E1, E2 | confirmed |", "| — | — | — |")
    check("no coverage row fails", len(codes(run_report(no_row), "R-KQ2")) == 1,
          detail=str(codes(run_report(no_row), "R-KQ2")))


def test_citecomp():
    print("[R-CITECOMP] citation_check completeness and CRITICAL")
    full = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 6)]}
    check("complete and no CRITICAL passes",
          not codes(run_report(CLEAN_REPORT, citation=full), "R-CITECOMP"))

    partial = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 4)]}
    check("a missing result fails",
          len(codes(run_report(CLEAN_REPORT, citation=partial), "R-CITECOMP")) == 1)

    crit = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 5)]
                       + [{"id": "E5", "severity": "CRITICAL"}]}
    check("a CRITICAL fails",
          len(codes(run_report(CLEAN_REPORT, citation=crit), "R-CITECOMP")) == 1)

    check("no --citation raises nothing",
          not codes(run_report(CLEAN_REPORT), "R-CITECOMP"))


if __name__ == "__main__":
    test_key_cluster()
    test_floor_units()
    test_clean()
    test_thin()
    test_conflict_pair()
    test_counter_empty()
    test_point_and_band()
    test_kq2()
    test_citecomp()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        sys.exit(1)
    print("\nall passed")
