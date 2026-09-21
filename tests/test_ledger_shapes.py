#!/usr/bin/env python3
"""Regression tests for four shape defects an end-to-end run exposed:

1. evidence_auditor.py, given a wrong-typed enum value (an unhashable dict where a string
   is expected), reports a FAIL for it.
2. merge_fragments.py taking a gap in as a plain string or under aliased key names, which
   used to reach render_scaffold.py in a shape it could not read.
3. merge_fragments.py fusing a collector's and a scholar's provisional origin_cluster ids
   when the two roles happen to reuse the same id on one key question.
4. apply_verdicts.py dropping a verifier's own corroborating_source, and
   evidence_auditor.py then accepting it as a stand-in for a corroborating_ids entry.
"""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "plugins", "research-team", "skills", "research-team", "scripts")
PY = sys.executable
FAILURES = []


def check(label, cond, detail=""):
    print(("  OK   " if cond else "  NG   ") + label + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(label)


def load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ea = load("evidence_auditor")


def run(script, *args):
    cp = subprocess.run([PY, os.path.join(SCRIPTS, script), *args],
                        capture_output=True, text=True, encoding="utf-8")
    return cp.returncode, cp.stdout, cp.stderr


def codes(findings, code):
    return [f for f in findings if f["code"] == code]


def mk_evidence(tmp_id, kq, cluster, url, key=False, corr="single_source", cids=None):
    return {
        "id": tmp_id, "kq_ids": [kq],
        "claim": f"a falsifiable proposition about {kq} ({tmp_id})",
        "claim_type": "fact", "verbatim_quote": f"quote for {tmp_id}",
        "source": {"publisher": "Publisher", "title": f"Title {tmp_id}", "url": url,
                  "published": "2025-04-01", "grade": "A", "origin_cluster": cluster},
        "accessed": "2026-07-25", "is_key_figure": key, "corroboration": corr,
        "corroborating_ids": cids or [],
    }


# --------------------------------------------------------- 1. evidence_auditor crash guard

def test_wrong_typed_enum_reports_a_fail():
    print("[evidence_auditor.py: a wrong-typed enum reports a FAIL, no exception]")
    base = copy.deepcopy(ea.SAMPLE)
    for e in base["evidence"]:
        if e["id"] == "E3":
            e["corroboration"] = {"status": "corroborated"}
    findings = ea.Auditor(base, base.get("mode", "STANDARD")).run()
    check("a dict corroboration is caught as E-CORR", len(codes(findings, "E-CORR")) == 1,
          codes(findings, "E-CORR"))

    base2 = copy.deepcopy(ea.SAMPLE)
    for e in base2["evidence"]:
        if e["id"] == "E3":
            e["claim_type"] = ["fact"]
            e["source"]["grade"] = {"grade": "A"}
            e["verification"] = {"status": ["plausible"]}
    findings2 = ea.Auditor(base2, base2.get("mode", "STANDARD")).run()
    check("a list claim_type is caught as E-CLAIM-TYPE",
          len(codes(findings2, "E-CLAIM-TYPE")) == 1, codes(findings2, "E-CLAIM-TYPE"))
    check("a dict source.grade is caught as E-GRADE",
          len(codes(findings2, "E-GRADE")) == 1, codes(findings2, "E-GRADE"))
    check("a list verification.status is caught as E-VER",
          len(codes(findings2, "E-VER")) == 1, codes(findings2, "E-VER"))


# ----------------------------------------------------------------- 2. gap shape at merge

def test_gap_normalization_at_merge():
    print("[merge_fragments.py: a gap is taken in under the schema shape]")
    tmp = tempfile.mkdtemp(prefix="rt-ledgershapes-")
    try:
        run_dir = os.path.join(tmp, "run")
        frag_dir = os.path.join(run_dir, "evidence_fragments")
        os.makedirs(frag_dir)
        frag = {
            "kq_id": "KQ1",
            "evidence": [mk_evidence("tmp-1", "KQ1", "KQ1-1", "https://x.example/1")],
            "search_log": [{"query": "q1", "tool": "WebSearch", "kind": "normal", "adopted": 1}],
            "disconfirmation": [],
            "gaps": [
                "a plain-string gap",
                {"claim": "aliased keys", "queries_tried": "q1",
                 "would_settle_it": "an interview"},
                {"claim": "already shaped", "tried_queries": ["q2"], "recommended": "more"},
            ],
            "floor_status": {"met": True},
        }
        with open(os.path.join(frag_dir, "kq1_collector.json"), "w", encoding="utf-8") as f:
            json.dump(frag, f, ensure_ascii=False)

        rc, out, err = run("merge_fragments.py", "--run-dir", run_dir, "--topic", "t",
                           "--as-of", "2026-09-01", "--mode", "LIGHT")
        with open(os.path.join(run_dir, "evidence_log.json"), encoding="utf-8") as f:
            log = json.load(f)
        gaps = log["gaps"]
        check("all three gaps are taken in", len(gaps) == 3, gaps)
        check("every gap holds claim / tried_queries / recommended",
              all(set(g) >= {"claim", "tried_queries", "recommended"} for g in gaps), gaps)
        check("tried_queries is always a list",
              all(isinstance(g["tried_queries"], list) for g in gaps), gaps)

        plain = next(g for g in gaps if g["claim"] == "a plain-string gap")
        check("a plain string became the claim, with empty tried_queries/recommended",
              plain["tried_queries"] == [] and plain["recommended"] == "", plain)

        aliased = next(g for g in gaps if g["claim"] == "aliased keys")
        check("queries_tried/would_settle_it renamed, and the string became a list",
              aliased["tried_queries"] == ["q1"] and aliased["recommended"] == "an interview",
              aliased)

        shaped = next(g for g in gaps if g["claim"] == "already shaped")
        check("a gap already in shape passes through unchanged",
              shaped["tried_queries"] == ["q2"] and shaped["recommended"] == "more", shaped)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------- 3. origin_cluster collision across roles

def test_origin_cluster_renamed_across_roles():
    print("[merge_fragments.py: a collector/scholar origin_cluster collision is renamed]")
    tmp = tempfile.mkdtemp(prefix="rt-ledgershapes-")
    try:
        run_dir = os.path.join(tmp, "run")
        frag_dir = os.path.join(run_dir, "evidence_fragments")
        os.makedirs(frag_dir)
        collector = {
            "kq_id": "KQ1",
            "evidence": [mk_evidence("tmp-1", "KQ1", "KQ1-2", "https://collector.example/1")],
            "search_log": [{"query": "q1", "tool": "WebSearch", "kind": "normal", "adopted": 1}],
            "disconfirmation": [], "gaps": [], "floor_status": {"met": True},
        }
        scholar = {
            "kq_id": "KQ1",
            "evidence": [mk_evidence("tmp-1", "KQ1", "KQ1-2", "https://scholar.example/1")],
            "search_log": [{"query": "q2", "tool": "WebSearch", "kind": "normal", "adopted": 1}],
            "disconfirmation": [], "gaps": [], "floor_status": {"met": True},
        }
        with open(os.path.join(frag_dir, "kq1_collector.json"), "w", encoding="utf-8") as f:
            json.dump(collector, f, ensure_ascii=False)
        with open(os.path.join(frag_dir, "kq1_scholar.json"), "w", encoding="utf-8") as f:
            json.dump(scholar, f, ensure_ascii=False)

        rc, out, err = run("merge_fragments.py", "--run-dir", run_dir, "--topic", "t",
                           "--as-of", "2026-09-01", "--mode", "LIGHT")
        with open(os.path.join(run_dir, "evidence_log.json"), encoding="utf-8") as f:
            log = json.load(f)
        with open(os.path.join(run_dir, "id_map.json"), encoding="utf-8") as f:
            id_map = json.load(f)

        by_url = {e["source"]["url"]: e["source"]["origin_cluster"] for e in log["evidence"]}
        check("the collector's cluster id is unchanged",
              by_url["https://collector.example/1"] == "KQ1-2", by_url)
        check("the scholar's colliding cluster id was renamed",
              by_url["https://scholar.example/1"] == "KQ1-2-scholar", by_url)
        check("the rename is recorded in id_map.json",
              id_map.get("origin_cluster_renames") == {"KQ1-2": "KQ1-2-scholar"},
              id_map.get("origin_cluster_renames"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------- 4. apply_verdicts + the auditor's exception

def mk_key_figure_log(own_url):
    return {
        "schema": "research-evidence-1.4",
        "topic": "t", "as_of": "2026-09-01", "mode": "STANDARD",
        "key_questions": [{"id": "KQ1", "text": "a key question"}],
        "evidence": [{
            "id": "E1", "kq_ids": ["KQ1"],
            "claim": "the domestic market grew 12 percent in fiscal 2025",
            "claim_type": "fact",
            "verbatim_quote": "the domestic market grew 12 percent in fiscal 2025",
            "source": {"publisher": "Publisher A", "title": "Report A", "url": own_url,
                      "published": "2025-04", "grade": "B", "origin_cluster": "src-a"},
            "accessed": "2026-09-01", "is_key_figure": True,
            "corroboration": "single_source", "corroborating_ids": [],
            "verification": {"status": "unchecked"},
        }],
        "search_log": [], "gaps": [], "floor_status": [],
    }


def write_verdict(verdicts_dir, corroborating_url):
    os.makedirs(verdicts_dir, exist_ok=True)
    verdict = {"verdicts": [{
        "id": "E1", "verdict": "confirmed",
        "corroboration": {
            "status": "corroborated",
            "corroborating_source": {"publisher": "Publisher B", "url": corroborating_url,
                                     "value": "12 percent"},
        },
    }]}
    with open(os.path.join(verdicts_dir, "verdicts_1.json"), "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False)


def test_apply_verdicts_carries_corroborating_source():
    print("[apply_verdicts.py + evidence_auditor.py: a verifier's own source stands in "
          "for corroborating_ids]")
    tmp = tempfile.mkdtemp(prefix="rt-ledgershapes-")
    try:
        log_path = os.path.join(tmp, "evidence_log.json")
        verdicts_dir = os.path.join(tmp, "verification")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(mk_key_figure_log("https://a.example/report"), f, ensure_ascii=False)
        write_verdict(verdicts_dir, "https://b.example/other-report")

        rc, out, err = run("apply_verdicts.py", log_path, "--verdicts-dir", verdicts_dir)
        check("apply_verdicts.py applies the verdict cleanly", rc == 0, (out, err))
        with open(log_path, encoding="utf-8") as f:
            updated = json.load(f)
        e1 = updated["evidence"][0]
        check("corroboration.status was carried over", e1["corroboration"] == "corroborated",
              e1["corroboration"])
        check("verification.corroborating_source was carried over intact",
              e1["verification"].get("corroborating_source", {}).get("url")
              == "https://b.example/other-report", e1["verification"])

        findings = ea.Auditor(updated, "STANDARD").run()
        corr_empty = codes(findings, "E-CORR-EMPTY")
        key_cluster = codes(findings, "E-KEY-CLUSTER")
        check("a differing-domain corroborating_source clears E-CORR-EMPTY",
              corr_empty == [], corr_empty)
        check("a differing-domain corroborating_source clears E-KEY-CLUSTER",
              key_cluster == [], key_cluster)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_same_domain_corroborating_source_still_fails():
    print("[evidence_auditor.py: a corroborating_source on the unit's own domain earns no "
          "exception]")
    tmp = tempfile.mkdtemp(prefix="rt-ledgershapes-")
    try:
        log_path = os.path.join(tmp, "evidence_log.json")
        verdicts_dir = os.path.join(tmp, "verification")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(mk_key_figure_log("https://a.example/report"), f, ensure_ascii=False)
        write_verdict(verdicts_dir, "https://a.example/another-page")

        run("apply_verdicts.py", log_path, "--verdicts-dir", verdicts_dir)
        with open(log_path, encoding="utf-8") as f:
            updated = json.load(f)
        findings = ea.Auditor(updated, "STANDARD").run()
        check("a same-domain corroborating_source still fails E-CORR-EMPTY",
              len(codes(findings, "E-CORR-EMPTY")) == 1, codes(findings, "E-CORR-EMPTY"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_wrong_typed_enum_reports_a_fail()
    test_gap_normalization_at_merge()
    test_origin_cluster_renamed_across_roles()
    test_apply_verdicts_carries_corroborating_source()
    test_same_domain_corroborating_source_still_fails()

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        sys.exit(1)
    print("\nall passed")
    sys.exit(0)
