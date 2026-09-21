#!/usr/bin/env python3
"""validate_fragment.py checked.

Covers the required-field check a fragment runs on itself, and the per-mode branch that
decides which floors apply.
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


def run(path, mode, extra=()):
    cp = subprocess.run(
        [PY, os.path.join(SCRIPTS, "validate_fragment.py"), path, "--mode", mode, "--json", *extra],
        capture_output=True, text=True, encoding="utf-8")
    return cp.returncode, json.loads(cp.stdout)


def codes(result):
    return sorted({f["code"] for f in result["findings"]})


def ev(n):
    return {
        "id": f"tmp-{n}", "kq_ids": ["KQ1"],
        "claim": f"a falsifiable proposition ({n})", "claim_type": "fact",
        "verbatim_quote": f"quote {n}",
        "source": {"publisher": "Publisher", "title": f"Title {n}",
                   "url": f"https://example.com/{n}", "published": "2025-04",
                   "grade": "A", "origin_cluster": f"KQ1-{n}"},
        "accessed": "2026-07-25", "is_key_figure": False, "corroboration": "single_source",
    }


def rows(kind, n):
    return [{"query": f"{kind}-{i}", "tool": "WebSearch",
             "kind": kind, "adopted": 0} for i in range(n)]


def fragment(search_log, floor_status=None, evidence=None):
    return {
        "kq_id": "KQ1",
        "evidence": evidence if evidence is not None else [ev(1), ev(2)],
        "search_log": search_log,
        "disconfirmation": [{"hypothesis": "H1", "expected_if_false": "a disconfirming fact",
                             "queries": ["qc"], "found": "nothing was found"}],
        "gaps": [],
        "floor_status": floor_status if floor_status is not None else {"met": True},
    }


def write(tmp, name, data):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="rt-fragment-")
    try:
        deep_ok = rows("normal", 10) + rows("counter", 2)

        print("[DEEP applies the per-role floors as they stand]")
        p = write(tmp, "kq1_collector.json", fragment(deep_ok))
        rc, res = run(p, "DEEP")
        check("a fragment meeting the floors passes", res["verdict"] == "PASS" and rc == 0,
              str(codes(res)))
        check("the role comes from the file name", res["role"] == "collector", res["role"])

        thin = rows("normal", 6) + rows("counter", 2)
        p = write(tmp, "kq1_collector.json", fragment(thin))
        rc, res = run(p, "DEEP")
        check("below 12 queries it fails",
              "F-FLOOR-QUERY" in codes(res) and rc == 1, str(codes(res)))

        print("[STANDARD applies the per-role minimum allocation]")
        rc, res = run(p, "STANDARD")
        check("the same fragment passes under STANDARD", res["verdict"] == "PASS", str(codes(res)))

        minimal = rows("normal", 2)
        p = write(tmp, "kq1_collector.json", fragment(minimal))
        rc, res = run(p, "STANDARD")
        check("below the per-role minimum of 3 queries it fails",
              "F-FLOOR-QUERY" in codes(res), str(codes(res)))
        check("below 1 disconfirmation query it fails", "F-FLOOR-COUNTER" in codes(res),
              str(codes(res)))

        print("[search-facet coverage]")
        facet_log = [dict(r, facet=f) for r, f in
                     zip(deep_ok, ["definition", "data", "practice"] + ["data"] * 9)]
        p = write(tmp, "kq1_collector.json", fragment(facet_log))
        rc, res = run(p, "DEEP")
        check("a missing facet among recorded ones warns", "F-FACET" in codes(res), str(codes(res)))
        check("a missing facet does not fail", res["verdict"] == "PASS" and rc == 0, str(codes(res)))

        full_facets = [dict(r, facet=f) for r, f in
                       zip(deep_ok, ["definition", "data", "practice", "counter"] + ["data"] * 8)]
        p = write(tmp, "kq1_collector.json", fragment(full_facets))
        rc, res = run(p, "DEEP")
        check("all four facets covered, no warning", "F-FACET" not in codes(res), str(codes(res)))

        p = write(tmp, "kq1_collector.json", fragment(deep_ok))
        rc, res = run(p, "DEEP")
        check("a log with no facet is not judged", "F-FACET" not in codes(res), str(codes(res)))

        print("[required fields]")
        broken = fragment(deep_ok, evidence=[ev(1), {"id": "tmp-x", "claim": "broken"}])
        p = write(tmp, "kq1_collector.json", broken)
        rc, res = run(p, "DEEP")
        check("a missing required field fails", "F-EVIDENCE" in codes(res), str(codes(res)))

        print("[required field values]")

        def broken(field, value, base_id=1):
            e = ev(base_id)
            if "." in field:
                obj, key = field.split(".")
                e[obj][key] = value
            else:
                e[field] = value
            return fragment(deep_ok, evidence=[e, ev(2)])

        def messages(res, code):
            return [f["message"] for f in res["findings"] if f["code"] == code]

        p = write(tmp, "kq1_collector.json", broken("claim_type", "rumor"))
        rc, res = run(p, "DEEP")
        check("an out-of-enum claim_type fails", "F-EVIDENCE" in codes(res), str(codes(res)))
        check("the message names the field and the value",
              any("claim_type" in m and "'rumor'" in m for m in messages(res, "F-EVIDENCE")),
              messages(res, "F-EVIDENCE"))

        p = write(tmp, "kq1_collector.json",
                 broken("corroboration", {"status": "corroborated"}))
        rc, res = run(p, "DEEP")
        check("a dict corroboration fails cleanly (no crash)",
              "F-EVIDENCE" in codes(res) and rc == 1, str(codes(res)))

        p = write(tmp, "kq1_collector.json", broken("source.grade", "D"))
        rc, res = run(p, "DEEP")
        check("an out-of-enum source.grade fails", "F-EVIDENCE" in codes(res), str(codes(res)))
        check("the message names source.grade and the value",
              any("source.grade" in m and "'D'" in m for m in messages(res, "F-EVIDENCE")),
              messages(res, "F-EVIDENCE"))

        p = write(tmp, "kq1_collector.json", broken("source.url", "example.com/no-scheme"))
        rc, res = run(p, "DEEP")
        check("a source.url with no scheme fails", "F-EVIDENCE" in codes(res), str(codes(res)))

        p = write(tmp, "kq1_collector.json", broken("source.published", "25-04"))
        rc, res = run(p, "DEEP")
        check("a malformed source.published fails", "F-EVIDENCE" in codes(res), str(codes(res)))

        p = write(tmp, "kq1_collector.json", broken("is_key_figure", "false"))
        rc, res = run(p, "DEEP")
        check("a string is_key_figure fails (a bool is required)",
              "F-EVIDENCE" in codes(res), str(codes(res)))

        p = write(tmp, "kq1_collector.json",
                 broken("verbatim_quote", "the first part ... the joined-in second part"))
        rc, res = run(p, "DEEP")
        check("a verbatim_quote holding an ellipsis fails",
              "F-EVIDENCE" in codes(res), str(codes(res)))

        p = write(tmp, "kq1_collector.json",
                 broken("verbatim_quote", "the first part … second part"))
        rc, res = run(p, "DEEP")
        check("a verbatim_quote holding the ellipsis character fails",
              "F-EVIDENCE" in codes(res), str(codes(res)))

        print("[gap shape at intake]")
        with_gaps = fragment(deep_ok)
        with_gaps["gaps"] = [
            "a plain-string gap with no structure",
            {"claim": "already the schema shape", "tried_queries": ["q1"], "recommended": "r"},
            {"claim": "renamed keys", "queries_tried": "q1", "would_settle_it": "an interview"},
        ]
        p = write(tmp, "kq1_collector.json", with_gaps)
        rc, res = run(p, "DEEP")
        shape_msgs = messages(res, "F-GAP-SHAPE")
        check("a plain-string gap warns", len(shape_msgs) == 2, shape_msgs)
        flagged = any("already the schema shape" in m for m in shape_msgs)
        check("the already-shaped gap raises no warning", flagged is False, shape_msgs)
        check("the renamed keys are named in the warning",
              any("queries_tried -> tried_queries" in m for m in shape_msgs)
              and any("would_settle_it -> recommended" in m for m in shape_msgs), shape_msgs)
        check("a gap warning does not fail the fragment", res["verdict"] == "PASS", codes(res))

        print("[disconfirmation and floor_status are required]")
        no_disc = fragment(deep_ok)
        no_disc["disconfirmation"] = []
        no_disc.pop("floor_status")
        p = write(tmp, "kq1_collector.json", no_disc)
        rc, res = run(p, "DEEP")
        check("an empty disconfirmation fails", "F-DISC" in codes(res), str(codes(res)))
        check("a missing floor_status fails", "F-FLOORSTATUS" in codes(res), str(codes(res)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
