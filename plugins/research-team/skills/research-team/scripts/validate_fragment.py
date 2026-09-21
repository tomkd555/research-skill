#!/usr/bin/env python3
"""validate_fragment.py — one evidence fragment checking itself.

In research-team Step 2 a collection agent (research-collector / research-scholar) runs
this on its own fragment before returning it to the parent. It checks what a fragment can
work out alone — the required fields, and the floors for total queries and disconfirmation
queries — so that nothing comes back short.

The independent-source floor can only be worked out per key question, across both roles,
so evidence_auditor.py checks it after the merge and this script does not.

The floors that apply are the ones collection_standards.md §1 sets. DEEP applies its own
per-role floors as they stand; STANDARD applies the per-role minimum (three queries, one
disconfirmation query). A background KQ in DEEP (--relevance background) gets STANDARD's
floors. Where floor_status.early_stop records the three early-stop conditions (three or
more independent sources, two consecutive queries with nothing new, a conclusion at
"likely" or above) and STANDARD's floors are met, a shortfall is reported as WARN rather
than FAIL.

Examples:
    python validate_fragment.py evidence_fragments/kq1_collector.json --mode DEEP
    python validate_fragment.py kq2_scholar.json --mode STANDARD --json

Exit codes: 0 = PASS / 1 = at least one FAIL / 2 = usage or I/O error
"""

import argparse
import json
import os
import sys

from evidence_auditor import (BACKGROUND_FLOOR_MODE, BASE_FLOOR_MODE, FLOORS,
                              MIN_ROLE_ALLOCATION, ROLES,
                              VALID_RELEVANCE, _configure_stdout, validate_early_stop)
from merge_fragments import FRAGMENT_RE, normalize_gap, validate_evidence

SEARCH_FACETS = ("definition", "data", "counter", "practice")


def role_from_filename(path):
    m = FRAGMENT_RE.match(os.path.basename(path))
    return m.group(2).lower() if m else None


def kq_from_filename(path):
    m = FRAGMENT_RE.match(os.path.basename(path))
    return f"KQ{int(m.group(1))}" if m else None


def validate(frag, mode, role, relevance="decision"):
    """Check one fragment and return the findings."""
    findings = []

    def add(severity, code, message, location=""):
        findings.append({"severity": severity, "code": code,
                         "message": message, "location": location})

    evidence = frag.get("evidence") or []
    search_log = frag.get("search_log") or []
    floor_status = frag.get("floor_status")

    if not evidence:
        add("FAIL", "F-EMPTY", "evidence is empty")
    if not search_log:
        add("FAIL", "F-SEARCHLOG",
            "search_log is empty (a query that yielded nothing is recorded too)")
    if not isinstance(floor_status, dict):
        add("FAIL", "F-FLOORSTATUS",
            "floor_status is missing (a fragment reports on its own floors)")
        floor_status = {}
    if mode in ("STANDARD", "DEEP") and not (frag.get("disconfirmation") or []):
        add("FAIL", "F-DISC",
            "disconfirmation is empty (the disconfirmation search is a duty; where it finds "
            "nothing, record the queries run and that they found nothing)")

    for i, e in enumerate(evidence):
        reason = validate_evidence(e)
        if reason:
            tmp_id = e.get("id") if isinstance(e, dict) else None
            add("FAIL", "F-EVIDENCE", reason, f"evidence[{i}] (id={tmp_id})")

    for i, g in enumerate(frag.get("gaps") or []):
        _, notes = normalize_gap(g)
        if notes:
            add("WARN", "F-GAP-SHAPE",
                "the merge takes this gap in under a different shape: "
                + "; ".join(notes), f"gaps[{i}]")

    # The floors that apply: a background KQ in DEEP gets STANDARD's (collection_standards.md §1).
    effective_mode = BACKGROUND_FLOOR_MODE if (mode == "DEEP" and relevance == "background") else mode
    floors = FLOORS.get(effective_mode, FLOORS["STANDARD"])
    # The unit the floors apply to follows the mode (collection_standards.md §1). DEEP is
    # per role, so even a background KQ puts that KQ's floors on a single role. STANDARD
    # totals across roles per KQ, and all a fragment alone can see is the per-role minimum.
    # Diverging from evidence_auditor.py here would let a fragment pass its self-check and
    # then fail the audit after the merge, sending collection round again.
    if mode == "DEEP":
        need_queries = floors["queries"]
        need_counter = floors["counter_queries"]
    else:
        need_queries = min(floors["queries"], MIN_ROLE_ALLOCATION["queries"])
        need_counter = min(floors["counter_queries"],
                           MIN_ROLE_ALLOCATION["counter_queries"])

    # The early stop: with a record meeting all three conditions, a shortfall that still
    # clears STANDARD's floors is a WARN.
    early_ok, early_reason = validate_early_stop(floor_status.get("early_stop"))
    if early_reason:
        add("FAIL", "F-EARLYSTOP",
            f"the early_stop record misses one of the three conditions: {early_reason} "
            "(a shortfall with no record, or with a malformed one, counts as a shortfall)")
    base = FLOORS[BASE_FLOOR_MODE]
    base_queries = base["queries"] if early_ok else None
    base_counter = base["counter_queries"] if early_ok else None

    def report(code, message, actual, base_need):
        if base_need is not None and actual >= base_need:
            add("WARN", code,
                message + " (an early stop is recorded and STANDARD's floors are met)")
        else:
            add("FAIL", code, message)

    if need_queries > 0 and len(search_log) < need_queries:
        report("F-FLOOR-QUERY",
               f"{len(search_log)} queries, below the floor of {need_queries}",
               len(search_log), base_queries)
    n_counter = sum(1 for s in search_log if isinstance(s, dict) and s.get("kind") == "counter")
    if n_counter < need_counter:
        report("F-FLOOR-COUNTER",
               f"{n_counter} disconfirmation queries, below the floor of {need_counter}",
               n_counter, base_counter)

    # Coverage of the four search facets (collection_standards.md §2). facet is optional, so a
    # log that records none is not judged; only a log that records some and misses others warns.
    if any(isinstance(s, dict) and s.get("facet") for s in search_log):
        covered = {s.get("facet") for s in search_log if isinstance(s, dict)}
        missing = [f for f in SEARCH_FACETS if f not in covered]
        if missing:
            add("WARN", "F-FACET",
                f"no query covers the search facet(s): {', '.join(missing)}"
                " (definition / data / counter / practice; a skewed collection returns a"
                " skewed result)")

    return findings


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(description="One evidence fragment checking itself")
    parser.add_argument("fragment",
                        help="path to the fragment JSON (evidence_fragments/kq{N}_{role}.json)")
    parser.add_argument("--mode", required=True, choices=list(FLOORS))
    parser.add_argument("--role", choices=list(ROLES), default=None,
                        help="the collection role (otherwise taken from the file name)")
    parser.add_argument("--relevance", choices=list(VALID_RELEVANCE), default="decision",
                        help="this KQ's decision relevance (default decision). background in "
                             "DEEP is judged against STANDARD's floors")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()

    role = args.role or role_from_filename(args.fragment)
    if role is None:
        print("error: the role cannot be identified. Name the file "
              "kq{N}_{collector|scholar}.json, or pass --role", file=sys.stderr)
        return 2

    try:
        with open(args.fragment, encoding="utf-8") as f:
            frag = json.load(f)
    except OSError as e:
        print(f"error: cannot read the fragment: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: the fragment is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(frag, dict):
        print("error: the top level of the fragment is not an object", file=sys.stderr)
        return 2

    findings = validate(frag, args.mode, role, args.relevance)
    fails = [f for f in findings if f["severity"] == "FAIL"]
    verdict = "FAIL" if fails else "PASS"

    result = {
        "verdict": verdict, "mode": args.mode, "role": role, "relevance": args.relevance,
        "kq_id": frag.get("kq_id") or kq_from_filename(args.fragment),
        "evidence_count": len(frag.get("evidence") or []),
        "search_log_rows": len(frag.get("search_log") or []),
        "fail_count": len(fails), "findings": findings,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"verdict: {verdict} ({result['kq_id']} / {role} / mode {args.mode} / "
              f"{result['evidence_count']} evidence units / FAIL {len(fails)})")
        for f in findings:
            loc = f" @{f['location']}" if f.get("location") else ""
            print(f"  [{f['severity']}] {f['code']}{loc}: {f['message']}")
        if verdict == "PASS":
            print("  Every floor a fragment can check alone is met. It may go back to the parent.")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
