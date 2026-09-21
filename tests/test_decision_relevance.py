#!/usr/bin/env python3
"""Regression tests for decision relevance, the early stop, and the verification cap.

They cover the change that scales collection and verification by what a key question
contributes to the conclusion (collection_standards.md §1, and the narrowing and the cap
in select_verification_targets.py): that it bites where it should and nowhere else.
"""
import importlib.util
import json
import os
import sys
import tempfile

SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")


def load(name):
    path = os.path.join(SKILL_SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # for the cross-import validate_fragment -> evidence_auditor
    spec.loader.exec_module(mod)
    return mod


ea = load("evidence_auditor")
mf = load("merge_fragments")
vf = load("validate_fragment")
svt = load("select_verification_targets")
rpl = load("research_plan_linter")
rs = load("render_scaffold")
ra = load("report_auditor")


# ------------------------------------------------------------- shared material

def slog(kq, role, kind, n):
    return [{"query": f"{kq}-{role}-{kind}-{i}", "tool": "WebSearch",
             "kind": kind, "adopted": 0, "kq_id": kq, "role": role} for i in range(n)]


def rows_for(role, queries, counter, kq="KQ1"):
    """A search log of that many queries, with counter of them disconfirming."""
    return (slog(kq, role, "normal", queries - counter)
            + slog(kq, role, "counter", counter))


def floor_log(mode, rows, statuses, relevance=None, kq="KQ1"):
    question = {"id": kq, "text": "Does it hold?"}
    if relevance:
        question["relevance"] = relevance
    return {
        "schema": "research-evidence-1.3", "topic": "The topic", "as_of": "2026-07-25",
        "mode": mode,
        "key_questions": [question],
        "evidence": [], "search_log": rows, "gaps": [], "floor_status": statuses,
        "disconfirmation": [{"hypothesis": "H1", "expected_if_false": "x",
                             "queries": ["q"], "found": "nothing of the kind"}],
    }


def query_findings(findings):
    return [f for f in findings if f["code"] == "E-FLOOR-QUERY"]


def code_findings(findings, code):
    return [f for f in findings if f["code"] == code]


EARLY_STOP_OK = {"independent_sources": 3, "consecutive_zero_new": 2,
                 "conclusion_confidence": "likely", "note": "stopped once the search saturated"}


# --------------------------------------------------- floors by decision relevance

def test_background_kq_uses_standard_floor():
    """A background KQ in DEEP gets STANDARD's floors; a decision KQ gets DEEP's."""
    status = {"kq_id": "KQ1", "role": "collector", "met": True}
    rows = rows_for("collector", queries=6, counter=1)   # clears STANDARD; short of DEEP

    findings = ea.Auditor(floor_log("DEEP", rows, [status], relevance="background")).run()
    assert not query_findings(findings), \
        f"a background KQ was reported short: {query_findings(findings)}"

    findings = ea.Auditor(floor_log("DEEP", rows, [status], relevance="decision")).run()
    hits = query_findings(findings)
    assert hits and all(h["severity"] == "FAIL" for h in hits), \
        "DEEP's floors do not bite on a decision KQ"

    # A KQ with no relevance counts as a decision KQ, so leaving it out lowers nothing.
    findings = ea.Auditor(floor_log("DEEP", rows, [status])).run()
    assert query_findings(findings), "a KQ with no relevance was not treated as a decision KQ"


def test_invalid_relevance_is_rejected():
    status = {"kq_id": "KQ1", "role": "collector", "met": True}
    log = floor_log("DEEP", rows_for("collector", 12, 2), [status], relevance="critical")
    findings = ea.Auditor(log).run()
    assert code_findings(findings, "E-KQ-RELEVANCE"), "an invalid relevance went undetected"


# ------------------------------------------------------------------ the early stop

def test_early_stop_downgrades_to_warn():
    """With a record meeting the three conditions and STANDARD met, a shortfall is a WARN."""
    rows = rows_for("collector", queries=6, counter=1)
    with_stop = {"kq_id": "KQ1", "role": "collector", "met": False, "early_stop": EARLY_STOP_OK}
    findings = ea.Auditor(floor_log("DEEP", rows, [with_stop], relevance="decision")).run()
    hits = query_findings(findings)
    assert hits, "the shortfall itself went unreported"
    assert all(h["severity"] == "WARN" for h in hits), f"it did not drop to WARN: {hits}"
    assert code_findings(findings, "E-EARLYSTOP"), "the early stop went unreported"


def test_early_stop_below_standard_floor_still_fails():
    """Below STANDARD's own floors it stays a FAIL, record or no record."""
    rows = rows_for("collector", queries=3, counter=1)
    with_stop = {"kq_id": "KQ1", "role": "collector", "met": False, "early_stop": EARLY_STOP_OK}
    findings = ea.Auditor(floor_log("DEEP", rows, [with_stop], relevance="decision")).run()
    hits = query_findings(findings)
    assert hits and any(h["severity"] == "FAIL" for h in hits), \
        f"below STANDARD and still no FAIL: {hits}"


def test_early_stop_record_must_meet_three_conditions():
    rows = rows_for("collector", queries=6, counter=1)
    for bad in ({"independent_sources": 2, "consecutive_zero_new": 2,
                 "conclusion_confidence": "likely"},
                {"independent_sources": 3, "consecutive_zero_new": 1,
                 "conclusion_confidence": "likely"},
                {"independent_sources": 3, "consecutive_zero_new": 2,
                 "conclusion_confidence": "roughly even chance"}):
        status = {"kq_id": "KQ1", "role": "collector", "met": False, "early_stop": bad}
        findings = ea.Auditor(floor_log("DEEP", rows, [status], relevance="decision")).run()
        assert code_findings(findings, "E-EARLYSTOP-FORM"), f"a bad record passed: {bad}"
        assert any(h["severity"] == "FAIL" for h in query_findings(findings)), \
            f"a bad record still dropped the shortfall to WARN: {bad}"


def test_validate_fragment_early_stop_and_relevance():
    """A fragment checking itself applies the background floors and the early stop too."""
    fragment = {
        "kq_id": "KQ1",
        "evidence": [{"kq_ids": ["KQ1"], "claim": "The claim states a fact",
                      "claim_type": "fact",
                      "verbatim_quote": "the quoted passage", "accessed": "2026-07-25",
                      "is_key_figure": False, "corroboration": "single_source",
                      "source": {"publisher": "P", "title": "T",
                                 "url": "https://example.com/a", "published": "2026-01",
                                 "grade": "B"}}],
        "search_log": rows_for("collector", queries=6, counter=1),
        "disconfirmation": [{"hypothesis": "H1", "queries": ["q"],
                             "found": "nothing of the kind"}],
        "floor_status": {"met": True},
    }
    findings = vf.validate(fragment, "DEEP", "collector", relevance="background")
    assert not [f for f in findings if f["code"].startswith("F-FLOOR")], \
        f"a background KQ was reported short: {findings}"

    findings = vf.validate(fragment, "DEEP", "collector", relevance="decision")
    assert [f for f in findings
            if f["code"] == "F-FLOOR-QUERY" and f["severity"] == "FAIL"], \
        "the floors do not bite on a decision KQ"

    fragment["floor_status"] = {"met": False, "early_stop": EARLY_STOP_OK}
    findings = vf.validate(fragment, "DEEP", "collector", relevance="decision")
    floor_hits = [f for f in findings if f["code"].startswith("F-FLOOR")]
    assert floor_hits and all(f["severity"] == "WARN" for f in floor_hits), \
        f"the early stop did not drop it to WARN: {floor_hits}"


# ------------------------------------------------------------- the plan's notation

def test_parse_brief_relevance():
    body = "\n".join([
        "## Key questions",
        "- KQ1: Is the market growing? [decision]",
        "- KQ2: What does the regulation presuppose? [background]",
        "- KQ3: What are the competitors doing?",
    ])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "research_brief.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        kqs = mf.parse_brief_kqs(path)
    assert [k["id"] for k in kqs] == ["KQ1", "KQ2", "KQ3"]
    assert kqs[0]["relevance"] == "decision"
    assert kqs[1]["relevance"] == "background"
    assert "relevance" not in kqs[2], "an untagged KQ was given a relevance"
    assert "[decision]" not in kqs[0]["text"], "the tag was left in the text"


BRIEF = """# Research plan

- Mode: DEEP
- as_of: 2026-08-08

## Purpose
State the decision this feeds.

## Key questions
{KQS}

## Competing hypotheses
- H1: It is growing.
- H2: It has levelled off.

## Disconfirmation plan
| Hypothesis | Observable if false |
|---|---|
| H1 | A decline |
| H2 | A rise |

## Source plan
- Role assignment: KQ1=collector, KQ2=collector, KQ3=collector, KQ4=collector, KQ5=collector

## Stopping rules
- The floors are met, or the three early-stop conditions hold.

## Out of scope
- Markets outside the region.
"""


def lint_brief(kq_lines):
    return rpl.lint(BRIEF.replace("{KQS}", "\n".join(kq_lines)), "DEEP")[0]


def test_plan_linter_requires_relevance():
    findings = lint_brief(["- KQ1: Is it growing?", "- KQ2: What does it presuppose?"])
    assert [f for f in findings if f["code"] == "P-KQ-RELEVANCE"], \
        "a plan with no decision relevance passed"

    findings = lint_brief(["- KQ1: Is it growing? [decision]",
                           "- KQ2: What does it presuppose? [background]"])
    assert not [f for f in findings if f["code"] == "P-KQ-RELEVANCE"]


def test_plan_linter_caps_decision_kqs():
    five = [f"- KQ{i}: Does proposition {i} hold? [decision]" for i in range(1, 6)]
    findings = lint_brief(five)
    assert [f for f in findings if f["code"] == "P-KQ-DECISION-MAX"], "five decision KQs passed"

    four = ([f"- KQ{i}: Does proposition {i} hold? [decision]" for i in range(1, 5)]
            + ["- KQ5: Does proposition 5 hold? [background]"])
    findings = lint_brief(four)
    assert not [f for f in findings if f["code"] == "P-KQ-DECISION-MAX"]


def test_plan_linter_cost_budget():
    """Moving a KQ to background lowers the estimated tool calls."""
    mixed = ([f"- KQ{i}: Does proposition {i} hold? [decision]" for i in range(1, 3)]
             + [f"- KQ{i}: Does proposition {i} hold? [background]" for i in range(3, 5)])
    assert [f for f in lint_brief(mixed) if f["code"] == "P-COST"], "P-COST was not reported"

    heavy = rpl.estimate_cost("DEEP", 4, {str(i): ["collector"] for i in range(1, 5)},
                              {str(i): "decision" for i in range(1, 5)})
    light = rpl.estimate_cost("DEEP", 4, {str(i): ["collector"] for i in range(1, 5)},
                              {"1": "decision", "2": "decision",
                               "3": "background", "4": "background"})
    assert light[1] < heavy[1], "a background KQ did not lower the estimated tool calls"
    assert light[0] == heavy[0], "the agent count must not move with decision relevance"


# ----------------------------------------------------- narrowing the verification

def ledger(evidence, relevance_map):
    return {
        "schema": "research-evidence-1.3", "topic": "The topic", "as_of": "2026-07-25",
        "mode": "DEEP",
        "key_questions": [{"id": k, "text": "Does it hold?", "relevance": v}
                          for k, v in relevance_map.items()],
        "evidence": evidence, "search_log": [],
    }


def unit(eid, kq, **kwargs):
    base = {"id": eid, "kq_ids": [kq], "claim": "The claim states a fact", "claim_type": "fact",
            "verbatim_quote": "the quoted passage", "accessed": "2026-07-25",
            "is_key_figure": False, "corroboration": "corroborated",
            "source": {"publisher": "P", "title": "T", "url": "https://example.com/a",
                       "published": "2026-01", "grade": "B", "origin_cluster": "c1"}}
    base.update(kwargs)
    return base


def test_single_source_and_estimate_scoped_to_decision_kq():
    evidence = [
        unit("E1", "KQ1", corroboration="single_source"),
        unit("E2", "KQ2", corroboration="single_source"),
        unit("E3", "KQ2", claim_type="estimate"),
        unit("E4", "KQ2", is_key_figure=True),
        unit("E5", "KQ2", corroboration="conflicting"),
    ]
    log = ledger(evidence, {"KQ1": "decision", "KQ2": "background"})
    signals = svt.ledger_signals(log)
    assert "E1" in signals, "a decision KQ's single source fell out of scope"
    assert "E2" not in signals, "a background KQ's single source came into scope"
    assert "E3" not in signals, "a background KQ's estimate came into scope"
    assert "key_figure" in signals.get("E4", []), \
        "every key figure is in scope whatever the relevance"
    assert "conflicting" in signals.get("E5", []), \
        "every conflict is in scope whatever the relevance"


def test_batch_cap_drops_lowest_priority():
    evidence = ([unit(f"E{i}", "KQ1", is_key_figure=True) for i in range(1, 4)]
                + [unit(f"E{i}", "KQ1", corroboration="single_source") for i in range(4, 13)])
    log = ledger(evidence, {"KQ1": "decision"})
    with tempfile.TemporaryDirectory() as d:
        summary = svt.select(log, None, d, wave=1, max_batches=2)
    assert len(summary["batches"]) == 2
    # 12 evidence units; the 2 surviving batches hold 3 (opus, the key figures) and 5
    # (sonnet, the first 5 of 9 single-source claims) = 8, so 4 are cut.
    assert summary["dropped"]["count"] == 4, summary["dropped"]
    kept = summary["expected_ids"].split(",")
    assert all(f"E{i}" in kept for i in (1, 2, 3)), "a key figure was dropped"
    assert summary["target_count"] == len(kept)


def test_fragment_selfcheck_matches_ledger_audit():
    """The fragment self-check and the post-merge audit apply the same floors to a group.

    DEEP applies its floors per role (collection_standards.md §1). If the fragment side
    alone passed on the per-role minimum of two queries, a fragment that cleared its own
    check would fail the audit and send collection round again.
    """
    def fragment(queries):
        return {
            "kq_id": "KQ1",
            "evidence": [{"kq_ids": ["KQ1"], "claim": "The claim states a fact",
                          "claim_type": "fact",
                          "verbatim_quote": "the quoted passage", "accessed": "2026-07-25",
                          "is_key_figure": False, "corroboration": "single_source",
                          "source": {"publisher": "P", "title": "T",
                                     "url": "https://example.com/a", "published": "2026-01",
                                     "grade": "B"}}],
            "search_log": rows_for("collector", queries=queries, counter=1),
            "disconfirmation": [{"hypothesis": "H1", "queries": ["q"], "found": "nothing"}],
            "floor_status": {"met": True},
        }

    status = {"kq_id": "KQ1", "role": "collector", "met": True}
    for queries, expect_fail in ((3, True), (6, False)):
        frag_fail = bool([f for f in vf.validate(fragment(queries), "DEEP", "collector",
                                                 relevance="background")
                          if f["code"].startswith("F-FLOOR") and f["severity"] == "FAIL"])
        rows = rows_for("collector", queries=queries, counter=1)
        ledger_fail = bool([f for f in query_findings(
            ea.Auditor(floor_log("DEEP", rows, [status], relevance="background")).run())
            if f["severity"] == "FAIL"])
        assert frag_fail == ledger_fail == expect_fail, \
            f"{queries} queries: fragment={frag_fail} ledger={ledger_fail} " \
            f"expected={expect_fail}"


def test_floor_shortfall_is_not_excused_by_gaps():
    """A record in gaps does not on its own drop a shortfall to WARN.

    gaps is a required output of collection and almost every study has one, so relaxing
    the floors on its presence would disable the gate.
    """
    status = {"kq_id": "KQ1", "role": "collector", "met": False}
    log = floor_log("DEEP", rows_for("collector", queries=3, counter=1), [status],
                    relevance="decision")
    log["gaps"] = [{"claim": "a claim left uncorroborated", "tried_queries": ["q"],
                    "recommended": "further research"}]
    hits = query_findings(ea.Auditor(log).run())
    assert hits and all(h["severity"] == "FAIL" for h in hits), \
        f"a gaps entry alone dropped it to WARN: {hits}"


def test_batch_cap_is_per_run_not_per_wave():
    """The batch cap is per study. A second wave subtracts what the first wave used."""
    evidence = [unit(f"E{i}", "KQ1", is_key_figure=True) for i in range(1, 40)]
    log = ledger(evidence, {"KQ1": "decision"})
    citation = {"results": [{"id": f"E{i}", "severity": "CRITICAL"} for i in range(1, 40)]}
    with tempfile.TemporaryDirectory() as d:
        first = svt.select(log, None, d, wave=1, max_batches=4)
        os.makedirs(os.path.join(d, "verification"), exist_ok=True)
        for b in first["batches"]:
            with open(b["targets_path"], "w", encoding="utf-8") as f:
                json.dump({"batch_id": b["batch_id"]}, f)
        second = svt.select(log, citation, d, wave=2, max_batches=4)
    assert len(first["batches"]) == 4
    assert second["batches_used_by_other_waves"] == 4, second
    assert len(second["batches"]) == 0, f"the second wave went over the cap: {second['batches']}"


def test_confidence_ceiling_needs_verification():
    """A KQ with no confirmed evidence is capped, however strong its sources."""
    a_sources = [unit("E1", "KQ1", source={"publisher": "P1", "title": "T", "grade": "A",
                                           "url": "https://a.example", "published": "2026-01",
                                           "origin_cluster": "c1"}),
                 unit("E2", "KQ1", source={"publisher": "P2", "title": "T", "grade": "A",
                                           "url": "https://b.example", "published": "2026-01",
                                           "origin_cluster": "c2"})]
    for e in a_sources:
        e.pop("verification", None)
    label, band, reason = rs.confidence_ceiling(a_sources)
    assert label == "likely", f"unverified evidence reached {label} ({reason})"
    assert band, "the probability band is empty"

    for e in a_sources:
        e["verification"] = {"status": "confirmed"}
    label, _, _ = rs.confidence_ceiling(a_sources)
    assert label == "almost certain", f"confirmed evidence stayed capped at {label}"


def test_header_metrics_exclude_dead_evidence():
    """Refuted and superseded evidence does not count towards the header metrics."""
    log = {"evidence": [
        unit("E1", "KQ1", verification={"status": "confirmed"}),
        unit("E2", "KQ1", verification={"status": "refuted"},
             source={"publisher": "P2", "title": "T", "grade": "B",
                     "url": "https://b.example", "published": "2026-01", "origin_cluster": "c2"}),
        unit("E3", "KQ1", superseded_by="E1",
             source={"publisher": "P3", "title": "T", "grade": "B",
                     "url": "https://c.example", "published": "2026-01", "origin_cluster": "c3"}),
    ]}
    m = rs.header_metrics(log)
    assert m["evidence_units"] == 1 and m["excluded_units"] == 2, m
    assert m["independent_sources"] == 1, m
    assert m["verified_claims"] == 1, m


def test_batch_cap_default_from_mode():
    evidence = [unit(f"E{i}", "KQ1", is_key_figure=True) for i in range(1, 40)]
    log = ledger(evidence, {"KQ1": "decision"})
    with tempfile.TemporaryDirectory() as d:
        summary = svt.select(log, None, d, wave=1)
    assert summary["max_batches"] == svt.MAX_BATCHES["DEEP"]
    assert len(summary["batches"]) == svt.MAX_BATCHES["DEEP"]


# ------------------------------------------------------- the shape of the report

REPORT = """# Report

as_of: 2026-07-25

{DECISION}## Summary
The figure stands at 12,000 cases [E1].

## Disconfirmation and conflicting evidence
The disconfirming search returned nothing.

## Limitations and evidence gaps
Self-verification is unstable without an outside check.

## KQ coverage
| KQ | Key evidence |
|---|---|
| KQ1 | E1 |

## Search log
| Query | Language |
|---|---|
| q | en |

## Sources
- [E1] P. T. 2026-01. https://example.com/a
"""

DECISION_SECTION = """## Answer to the decision
- Answer: the figure is holding at 12,000 cases [E1]
- Recommendation: keep to the current course
- Confidence: likely (65-80%)
- What would overturn it: the figure falling below 10,000

"""


def test_report_requires_decision_section():
    log = {"key_questions": [{"id": "KQ1", "text": "?"}],
           "evidence": [{"id": "E1", "corroboration": "corroborated",
                         "corroborating_ids": ["E2"], "verification": {"status": "confirmed"}}],
           "gaps": []}
    findings, _ = ra.audit(REPORT.replace("{DECISION}", ""), log)
    assert [f for f in findings if f["code"] == "R-SEC-DECISION"], \
        "a report missing the answer to the decision passed"

    findings, _ = ra.audit(REPORT.replace("{DECISION}", DECISION_SECTION), log)
    assert not [f for f in findings if f["code"] == "R-SEC-DECISION"]


def test_scaffold_transcribes_early_stop():
    log = {"topic": "The topic", "as_of": "2026-07-25", "mode": "DEEP",
           "key_questions": [{"id": "KQ1", "text": "Does it hold?", "relevance": "decision"}],
           "evidence": [], "search_log": [], "gaps": [],
           "floor_status": [{"kq_id": "KQ1", "role": "collector",
                             "early_stop": dict(EARLY_STOP_OK)}]}
    scaffold = rs.build_scaffold(log)
    assert "## Answer to the decision" in scaffold, "the decision section was not generated"
    assert rs.EARLY_STOP_BEGIN in scaffold and rs.EARLY_STOP_END in scaffold
    assert "stopped once the search saturated" in scaffold, \
        "the early stop was not transcribed into the limitations section"

    log["floor_status"] = [{"kq_id": "KQ1", "role": "collector"}]
    assert "(no early stop)" in rs.build_scaffold(log)


def test_scaffold_passes_the_required_section_check():
    """What the generator writes is what the auditor accepts as the required sections."""
    log = {"topic": "Topic", "as_of": "2026-07-25", "mode": "DEEP",
           "key_questions": [{"id": "KQ1", "text": "Does X hold?", "relevance": "decision"}],
           "evidence": [], "search_log": [], "gaps": [], "floor_status": []}
    scaffold = rs.build_scaffold(log)
    for heading in ("## Answer to the decision", "## Summary", "## Search log", "## Sources"):
        assert heading in scaffold, f"the skeleton is missing {heading}"

    findings, _ = ra.audit(scaffold + "\n\n[E1] and a limitations note.\n", {"evidence": []})
    missing = [f["code"] for f in findings if f["code"].startswith("R-SEC-")]
    assert not missing, f"the skeleton failed the required-section check: {missing}"


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK   {name}")
            except AssertionError as exc:
                print(f"  NG   {name}: {exc}")
                failures.append(name)
    if failures:
        print(f"\n{len(failures)} failed: {failures}")
        sys.exit(1)
    print("\nall passed")
