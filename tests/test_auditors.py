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
    """The ledger for report_auditor: E1/E2 corroborated, E3 thin, E4/E5 conflicting,
    E6 a self-reported single-source figure no fixture report cites by default."""
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
            {"id": "E6", "corroboration": "single_source", "corroborating_ids": [],
             "self_reported": True, "verification": {"status": "plausible"}},
        ],
        "gaps": [],
    }


CLEAN_REPORT = """# Research report

as_of: 2026-07-25

- Question type: descriptive

## Answer to the decision
- Answer: the figure is holding at 12,000 cases [E1]
- Recommendation: keep to the current course
- Confidence: likely (65-80%)
- What would overturn this: the second series staying below the current level

## Summary
The headline figure is holding at 12,000 cases [E1]. We put that at likely (65-80%).

## KQ1 conclusion
On KQ1, the figure stands at 12,000 cases [E1][E2].
A second series puts it at 9,000 cases [E4]. The gap comes from a difference of definition [E5].
The supplementary figure is reportedly 62% [E3].

## Analysis

### Source incentives

| Evidence | Publisher | Who benefits if this figure is believed | self_reported | Corroborated by |
|---|---|---|---|---|
| E1 | Publisher | the publisher, if the figure supports its own position | false | E2 |

No source in the ledger is a party to the decision, so the incentive picture is clean.

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


def test_conf_labels_english():
    print("[R-CONF] the confidence labels are not translated")
    check("English labels pass", not codes(run_report(CLEAN_REPORT), "R-CONF"))

    translated = (CLEAN_REPORT
                  .replace("- Confidence: likely (65-80%)", "- 確度: 高い見込み（65%以上80%未満）")
                  .replace("We put that at likely (65-80%).", "確度は高い見込み（65%以上80%未満）。"))
    f = run_report(translated)
    check("translated labels fail", len(codes(f, "R-CONF")) == 1, detail=str(codes(f, "R-CONF")))


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
    full = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 7)]}
    check("complete and no CRITICAL passes",
          not codes(run_report(CLEAN_REPORT, citation=full), "R-CITECOMP"))

    partial = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 4)]}
    check("a missing result fails",
          len(codes(run_report(CLEAN_REPORT, citation=partial), "R-CITECOMP")) == 1)

    crit = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 5)]
                       + [{"id": "E5", "severity": "CRITICAL"}, {"id": "E6", "severity": "PASS"}]}
    check("a CRITICAL fails",
          len(codes(run_report(CLEAN_REPORT, citation=crit), "R-CITECOMP")) == 1)

    check("no --citation raises nothing",
          not codes(run_report(CLEAN_REPORT), "R-CITECOMP"))


JP_LOG = build_log()


def jp_report(kq1_line):
    """A minimal Japanese-prose report over JP_LOG's ledger, its structure (headings,
    the confidence label, the question type) held in English as the pipeline requires."""
    return f"""# 研究レポート

as_of: 2026-07-25

- Question type: descriptive

## Answer to the decision
- Answer: X holds[E1]
- Confidence: likely (65-80%)

## Summary
概要。

## KQ1 conclusion
{kq1_line}

## Disconfirmation and conflicting evidence
特になし。

## Limitations and evidence gaps
特になし。

## KQ coverage
| KQ | Key evidence | Verification |
|---|---|---|
| KQ1 | E3 | plausible |

## Search log
| Query |
|---|
| q1 |

## Sources
- [E1] Publisher. https://example.com/a
"""


def test_thin_japanese():
    print("[R-THIN] a Japanese claim on thin evidence, hedged or bare")
    hedged = jp_report("補足的な数値は62%とされる[E3]。")
    check("とされる clears it", not codes(run_report(hedged, log=JP_LOG), "R-THIN"),
          detail=str(codes(run_report(hedged, log=JP_LOG), "R-THIN")))

    bare = jp_report("補足的な数値は62%です[E3]。")
    check("no hedge fails", len(codes(run_report(bare, log=JP_LOG), "R-THIN")) == 1,
          detail=str(codes(run_report(bare, log=JP_LOG), "R-THIN")))

    two_sentences = jp_report("第一の値は62%です[E3]。第二の値は62%とされる[E3]。")
    f = run_report(two_sentences, log=JP_LOG)
    check("two 。 sentences: only the unhedged first one fails",
          len(codes(f, "R-THIN")) == 1, detail=str(codes(f, "R-THIN")))


def test_coverage_placeholder():
    print("[R-COVERAGE-PLACEHOLDER] a coverage row still carrying the scaffold's placeholder")
    check("the filled fixture passes", not codes(run_report(CLEAN_REPORT), "R-COVERAGE-PLACEHOLDER"))
    bad = CLEAN_REPORT.replace(
        "| KQ1 | E1, E2 | confirmed |",
        "| KQ1 | {one line} | {label} | E1, E2 | confirmed |")
    f = run_report(bad)
    check("an unfilled placeholder row warns",
          len(codes(f, "R-COVERAGE-PLACEHOLDER")) == 1,
          detail=str(codes(f, "R-COVERAGE-PLACEHOLDER")))


def test_citecomp_cleared():
    print("[R-CITECOMP] a CRITICAL record a verifier already judged is cleared")
    crit = {"results": [{"id": f"E{i}", "severity": "PASS"} for i in range(1, 5)]
                       + [{"id": "E5", "severity": "CRITICAL"}, {"id": "E6", "severity": "PASS"}]}
    check("an unjudged CRITICAL fails",
          len(codes(run_report(CLEAN_REPORT, citation=crit), "R-CITECOMP")) == 1)

    quote_checked = copy.deepcopy(build_log())
    e5 = next(e for e in quote_checked["evidence"] if e["id"] == "E5")
    e5["verification"]["quote_check"] = "found"
    check("cleared when the unit's quote_check is 'found'",
          not codes(run_report(CLEAN_REPORT, log=quote_checked, citation=crit), "R-CITECOMP"))

    refuted = copy.deepcopy(build_log())
    e5b = next(e for e in refuted["evidence"] if e["id"] == "E5")
    e5b["verification"]["status"] = "refuted"
    check("cleared when the unit's status is 'refuted'",
          not codes(run_report(CLEAN_REPORT, log=refuted, citation=crit), "R-CITECOMP"))


def test_analysis_type():
    print("[R-ANALYSIS-TYPE] the header names a recognised question type")
    check("a recognised type passes", not codes(run_report(CLEAN_REPORT), "R-ANALYSIS-TYPE"))
    bad = CLEAN_REPORT.replace("- Question type: descriptive", "- Question type: unsure")
    check("an unrecognised type fails", len(codes(run_report(bad), "R-ANALYSIS-TYPE")) == 1,
          detail=str(codes(run_report(bad), "R-ANALYSIS-TYPE")))
    no_line = CLEAN_REPORT.replace("- Question type: descriptive\n", "")
    check("no line at all fails", len(codes(run_report(no_line), "R-ANALYSIS-TYPE")) == 1,
          detail=str(codes(run_report(no_line), "R-ANALYSIS-TYPE")))


def test_analysis_block():
    print("[R-ANALYSIS-BLOCK] a required block has a heading under Analysis")
    check("the required heading passes", not codes(run_report(CLEAN_REPORT), "R-ANALYSIS-BLOCK"))
    bad = CLEAN_REPORT.replace("### Source incentives", "### Something else")
    f = run_report(bad)
    check("a missing heading fails", len(codes(f, "R-ANALYSIS-BLOCK")) == 1,
          detail=str(codes(f, "R-ANALYSIS-BLOCK")))
    check("emptiness is not raised twice for a heading that is not there",
          not codes(f, "R-ANALYSIS-EMPTY"), detail=str(codes(f, "R-ANALYSIS-EMPTY")))


def test_analysis_empty():
    print("[R-ANALYSIS-EMPTY] a required block needs a line free of {…} placeholders")
    check("the writer's sentence clears the descriptive fixture's Source incentives",
          not codes(run_report(CLEAN_REPORT), "R-ANALYSIS-EMPTY"))
    filled = ra.audit(render_ach(), ACH_LOG)[0]
    check("a filled Mechanism block clears it", not codes(filled, "R-ANALYSIS-EMPTY"),
          detail=str(codes(filled, "R-ANALYSIS-EMPTY")))
    f = ra.audit(render_ach(mech=MECH_PLACEHOLDER), ACH_LOG)[0]
    check("the unedited {…} placeholder block fails", len(codes(f, "R-ANALYSIS-EMPTY")) == 1,
          detail=str(codes(f, "R-ANALYSIS-EMPTY")))


def test_selfreport():
    print("[R-SELFREPORT] the Answer/Summary must not rest on a self-reported single-source figure")
    check("E6 uncited passes", not codes(run_report(CLEAN_REPORT), "R-SELFREPORT"))
    bad = CLEAN_REPORT.replace(
        "- Answer: the figure is holding at 12,000 cases [E1]",
        "- Answer: the figure is holding at 12,000 cases [E1][E6]")
    f = run_report(bad)
    check("citing it in the Answer fails", len(codes(f, "R-SELFREPORT")) == 1,
          detail=str(codes(f, "R-SELFREPORT")))


def test_overturn():
    print("[R-OVERTURN] the decision section names what would overturn it")
    check("the label with text passes", not codes(run_report(CLEAN_REPORT), "R-OVERTURN"))
    no_text = CLEAN_REPORT.replace(
        "- What would overturn this: the second series staying below the current level",
        "- What would overturn this:")
    check("the label with no text after the colon warns",
          len(codes(run_report(no_text), "R-OVERTURN")) == 1,
          detail=str(codes(run_report(no_text), "R-OVERTURN")))
    removed = CLEAN_REPORT.replace(
        "- What would overturn this: the second series staying below the current level\n", "")
    check("no line at all warns", len(codes(run_report(removed), "R-OVERTURN")) == 1,
          detail=str(codes(run_report(removed), "R-OVERTURN")))


# A separate small report for the checks that need a diagnostic question type (the
# Hypothesis matrix and a rival reading), so CLEAN_REPORT stays the minimal descriptive
# fixture the other checks share.
ACH_LOG = {
    "key_questions": [{"id": "KQ1", "text": "?"}],
    "evidence": [
        {"id": "E1", "corroboration": "corroborated", "corroborating_ids": ["E2"],
         "verification": {"status": "confirmed"}},
        {"id": "E2", "corroboration": "corroborated", "corroborating_ids": ["E1"],
         "verification": {"status": "confirmed"}},
    ],
    "gaps": [],
}

ACH_REPORT = """# Research report

as_of: 2026-07-25

- Question type: diagnostic
- Overall confidence: {CONF}

## Answer to the decision
- Answer: X holds [E1]
- Recommendation: proceed
- Confidence: likely (65-80%)
- What would overturn this: a contradicting confirmed source

## Summary
X holds on the evidence [E1]. We put that at likely (65-80%).

## KQ1 conclusion
On KQ1, X holds [E1][E2].

## Analysis

### Hypothesis matrix

| Evidence | H1: X | H2: not X | Diagnosticity |
|---|---|---|---|
| E1 | + | − | {DIAG} |

The matrix eliminates H2 on E1.

### Mechanism

{MECH}

### Source incentives

| Evidence | Publisher | Who benefits | self_reported | Corroborated by |
|---|---|---|---|---|
| E1 | Publisher | nobody | false | E2 |

No incentive concern.

### Rival reading

- Rival's answer: X does not hold
- Reconciliation: {RECON}
- Where it differs: the mechanism
- What would settle it: a third source
- Evidence the rival names as missing: none

## Disconfirmation and conflicting evidence
Nothing turned up against it.

## Limitations and evidence gaps
None material.

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
- [E2] Publisher. https://example.com/b
"""

# The Mechanism block filled in versus left as the scaffold's own {…} placeholders.
MECH_FILLED = "- Chain: A[E1] -> B[E2]\n\nThe chain holds with no unevidenced link."
MECH_PLACEHOLDER = ("- Chain: {A}[E#] → {B}[E#] → {C}[E#]\n"
                    "- Weakest link: {which arrow}\n"
                    "- Unevidenced links: {which arrows rest on reasoning alone, or none}")


def render_ach(diag="high", recon="agree", conf="likely (65-80%)", mech=MECH_FILLED):
    return (ACH_REPORT.replace("{DIAG}", diag).replace("{RECON}", recon)
                       .replace("{CONF}", conf).replace("{MECH}", mech))


def test_ach_diag():
    print("[R-ACH-DIAG] the matrix carries a high-diagnosticity row, ignoring placeholder rows")
    f = ra.audit(render_ach(diag="low"), ACH_LOG)[0]
    check("no high row warns", len(codes(f, "R-ACH-DIAG")) == 1, detail=str(codes(f, "R-ACH-DIAG")))
    f2 = ra.audit(render_ach(diag="high"), ACH_LOG)[0]
    check("a high row clears it", not codes(f2, "R-ACH-DIAG"), detail=str(codes(f2, "R-ACH-DIAG")))

    scaffold_row = render_ach(diag="high").replace("| E1 | + | − | high |", "| E# | + | − | high |")
    f3 = ra.audit(scaffold_row, ACH_LOG)[0]
    check("the scaffold's own \"E#\" example row does not satisfy it",
          len(codes(f3, "R-ACH-DIAG")) == 1, detail=str(codes(f3, "R-ACH-DIAG")))


def test_rival():
    print("[R-RIVAL] a Rival reading heading with a reconciliation line, when --rival is given")
    text = render_ach()
    check("no --rival raises nothing", not codes(ra.audit(text, ACH_LOG)[0], "R-RIVAL"))
    f = ra.audit(text, ACH_LOG, rival={})[0]
    check("a heading with Reconciliation clears it", not codes(f, "R-RIVAL"),
          detail=str(codes(f, "R-RIVAL")))
    no_head = text.replace("### Rival reading", "### Something else")
    f2 = ra.audit(no_head, ACH_LOG, rival={})[0]
    check("no Rival reading heading fails", len(codes(f2, "R-RIVAL")) == 1,
          detail=str(codes(f2, "R-RIVAL")))


def test_rival_cap():
    print("[R-RIVAL-CAP] a 'differs' reconciliation needs the settle line and a capped confidence")
    ok = render_ach(recon="differs")
    f = ra.audit(ok, ACH_LOG, rival={})[0]
    check("a settle line and a capped confidence pass",
          not codes(f, "R-RIVAL-CAP"), detail=str(codes(f, "R-RIVAL-CAP")))

    no_settle = ok.replace("- What would settle it: a third source\n", "")
    f2 = ra.audit(no_settle, ACH_LOG, rival={})[0]
    check("no settle line fails", len(codes(f2, "R-RIVAL-CAP")) == 1,
          detail=str(codes(f2, "R-RIVAL-CAP")))

    too_strong = render_ach(recon="differs", conf="almost certain (90-100%)")
    f3 = ra.audit(too_strong, ACH_LOG, rival={})[0]
    check("a confidence stronger than the cap fails", len(codes(f3, "R-RIVAL-CAP")) == 1,
          detail=str(codes(f3, "R-RIVAL-CAP")))

    agrees = render_ach(recon="agree")
    f4 = ra.audit(agrees, ACH_LOG, rival={})[0]
    check("an 'agree' reconciliation raises nothing", not codes(f4, "R-RIVAL-CAP"),
          detail=str(codes(f4, "R-RIVAL-CAP")))


if __name__ == "__main__":
    test_key_cluster()
    test_floor_units()
    test_clean()
    test_thin()
    test_conflict_pair()
    test_counter_empty()
    test_point_and_band()
    test_conf_labels_english()
    test_kq2()
    test_citecomp()
    test_citecomp_cleared()
    test_thin_japanese()
    test_coverage_placeholder()
    test_analysis_type()
    test_analysis_block()
    test_analysis_empty()
    test_selfreport()
    test_overturn()
    test_ach_diag()
    test_rival()
    test_rival_cap()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        sys.exit(1)
    print("\nall passed")
