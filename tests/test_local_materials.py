#!/usr/bin/env python3
"""Checks for evidence_auditor.py's local-materials rules (assets/evidence_log.schema.json 1.4).

1. E-KEY-USERSUP: a user-supplied key figure must say so in claim or verification.note
2. check_floors: a cluster whose evidence is all user_supplied counts at most once per KQ
   toward the independent-source floor, so local materials alone cannot clear it
"""
import importlib.util
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

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  OK   {label}")
    else:
        print(f"  NG   {label} {detail}")
        FAILURES.append(label)


def codes(findings, code):
    return [f for f in findings if f["code"] == code]


def base_evidence(eid, cluster, is_key_figure=False, user_supplied=False, url=None):
    return {
        "id": eid, "kq_ids": ["KQ1"], "claim": "the figure reads as stated in the source",
        "claim_type": "fact", "verbatim_quote": "a verbatim passage from the source",
        "source": {"publisher": "a publisher", "title": "a title",
                   "url": url or f"https://example.com/{cluster}",
                   "published": "2026", "grade": "B", "origin_cluster": cluster,
                   "user_supplied": user_supplied},
        "accessed": "2026-09-21", "is_key_figure": is_key_figure,
        "corroboration": "single_source", "corroborating_ids": [],
        "verification": {"status": "plausible", "note": "a single source, recorded here"},
    }


def build_log(mode, evidence):
    return {
        "schema": "research-evidence-1.4", "topic": "the topic", "as_of": "2026-09-21",
        "mode": mode, "key_questions": [{"id": "KQ1", "text": "does it hold?"}],
        "evidence": evidence, "search_log": [], "gaps": [],
    }


# ---------------------------------------------------------------- E-KEY-USERSUP

def test_key_usersup():
    print("[E-KEY-USERSUP] a user-supplied key figure must say so in claim or verification.note")

    unmarked = base_evidence("E1", "src-a", is_key_figure=True, user_supplied=True,
                             url="file:///C:/materials/filing.pdf")
    findings = ea.Auditor(build_log("STANDARD", [unmarked])).run()
    hits = codes(findings, "E-KEY-USERSUP")
    check("an unmarked user-supplied key figure fails",
          len(hits) == 1 and hits[0]["severity"] == "FAIL", str(hits))

    marked = base_evidence("E1", "src-a", is_key_figure=True, user_supplied=True,
                           url="file:///C:/materials/filing.pdf")
    marked["claim"] = "the user-supplied filing states the figure directly"
    findings = ea.Auditor(build_log("STANDARD", [marked])).run()
    check("a claim naming it user-supplied clears the check", not codes(findings, "E-KEY-USERSUP"),
          str(codes(findings, "E-KEY-USERSUP")))

    marked_note = base_evidence("E1", "src-a", is_key_figure=True, user_supplied=True,
                                url="file:///C:/materials/filing.pdf")
    marked_note["verification"]["note"] = "user-supplied; the reader handed this file over directly"
    findings = ea.Auditor(build_log("STANDARD", [marked_note])).run()
    check("a verification.note naming it user-supplied clears the check too",
          not codes(findings, "E-KEY-USERSUP"), str(codes(findings, "E-KEY-USERSUP")))

    # A user-supplied figure that is not a key figure is exempt; the rule targets what the
    # report can rest its conclusion on.
    minor = base_evidence("E1", "src-a", is_key_figure=False, user_supplied=True,
                          url="file:///C:/materials/filing.pdf")
    findings = ea.Auditor(build_log("STANDARD", [minor])).run()
    check("a user-supplied figure that is not a key figure is exempt",
          not codes(findings, "E-KEY-USERSUP"), str(codes(findings, "E-KEY-USERSUP")))


# ------------------------------------------------------- user_supplied clusters count once

def test_user_supplied_cluster_counted_once():
    print("[E-FLOOR-SOURCE] a cluster whose evidence is all user_supplied counts once per KQ")

    # DEEP's independent_sources floor is 5. Five local materials, five distinct clusters,
    # every one user_supplied: they collapse to one cluster and the floor still fails.
    five_local = [base_evidence(f"E{i}", f"local-{i}", user_supplied=True,
                                url=f"file:///C:/materials/doc{i}.pdf")
                  for i in range(1, 6)]
    findings = ea.Auditor(build_log("DEEP", five_local)).run()
    hits = codes(findings, "E-FLOOR-SOURCE")
    check("five user-supplied-only clusters still fail the floor of 5",
          len(hits) == 1 and hits[0]["severity"] == "FAIL", str(hits))

    # Four independently collected (non-user-supplied) clusters plus the same five local
    # materials: 4 web clusters + 1 collapsed local cluster clears the floor of 5.
    four_web = [base_evidence(f"W{i}", f"web-{i}") for i in range(1, 5)]
    findings = ea.Auditor(build_log("DEEP", four_web + five_local)).run()
    check("4 independent clusters plus the collapsed local cluster clear the floor",
          not codes(findings, "E-FLOOR-SOURCE"), str(codes(findings, "E-FLOOR-SOURCE")))

    # A mixed cluster - one collector source and one local material sharing an origin_cluster
    # - is not "all user_supplied", so it still counts on its own.
    mixed_cluster = [
        base_evidence("M1", "mixed-a", user_supplied=False),
        base_evidence("M2", "mixed-a", user_supplied=True, url="file:///C:/materials/doc.pdf"),
    ]
    four_more_web = [base_evidence(f"W{i}", f"web2-{i}") for i in range(1, 5)]
    findings = ea.Auditor(build_log("DEEP", mixed_cluster + four_more_web)).run()
    check("a mixed cluster (not all user_supplied) counts like any other cluster",
          not codes(findings, "E-FLOOR-SOURCE"), str(codes(findings, "E-FLOOR-SOURCE")))


if __name__ == "__main__":
    test_key_usersup()
    test_user_supplied_cluster_counted_once()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
        sys.exit(1)
    print("all passed")
