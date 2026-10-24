#!/usr/bin/env python3
"""Checks for check.py (lint and merge), all offline.

1. --lint passes a clean file and reports a quote absent from the cached page, an unknown
   enum value, a missing field, and a paper quote absent from its abstract
2. merge: ids E1..En in SQ order with web before academic, status per item, digests, gaps.json
3. merge: a web https item reads WARN offline and stays in the digest; a failed item stays
   out of the digest and lands in gaps.json
4. --only SQ2: the other items keep their ids, new ids follow the maximum
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_SCRIPTS = os.path.join(ROOT, "plugins", "research-team", "skills", "research-team", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
import citation_verifier as cv  # noqa: E402

CHECK = os.path.join(SKILL_SCRIPTS, "check.py")
BODY = ("Background filler sentence about the market. " * 20
        + "Domestic RPA market revenue reached 100 billion yen in fiscal 2025. "
        + "More filler sentence about the outlook. " * 20)
LOCAL = "file:///C:/tmp/material.txt"


def run(*args):
    p = subprocess.run([sys.executable, CHECK, *args], capture_output=True, text=True,
                       encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def item(sq="SQ1", url=LOCAL, quote="Domestic RPA market revenue reached 100 billion yen in fiscal 2025",
         **kw):
    base = {"sq": sq, "claim": "Revenue reached 100 billion yen.", "quote": quote, "url": url,
            "title": "T", "publisher": "P", "date": "2025", "grade": "B", "cluster": "example.com",
            "stance": "supports", "kind": "figure", "doi": None, "arxiv_id": None, "paper": None}
    base.update(kw)
    return base


def make_run(tmp, files, papers=None, name="run"):
    run_dir = os.path.join(tmp, name)
    os.makedirs(os.path.join(run_dir, "pages"))
    os.makedirs(os.path.join(run_dir, "collect"))
    index = {}
    for url in (LOCAL, "https://example.com/a"):
        name = cv.cache_name(url)
        with open(os.path.join(run_dir, "pages", name), "w", encoding="utf-8") as f:
            f.write(f"# url: {url}\n# accessed: 2026-10-24\n\n{BODY}\n")
        index[url] = {"path": name, "chars": len(BODY)}
    with open(os.path.join(run_dir, "pages", "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f)
    for name, items in files.items():
        with open(os.path.join(run_dir, "collect", name), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(i) for i in items) + "\n")
    for sq, db in (papers or {}).items():
        with open(os.path.join(run_dir, "collect", f"papers_{sq}.json"), "w", encoding="utf-8") as f:
            json.dump(db, f)
    return run_dir


def load_evidence(run_dir):
    with open(os.path.join(run_dir, "evidence.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_lint():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        paper = item(url="https://doi.org/10.1/x", paper="P1",
                     quote="Agents improved recall by 12 percent")
        bad = [
            item(),
            item(quote="a sentence that the page never contains at all, anywhere"),
            item(stance="maybe"),
            item(date="June 2025"),
            {k: v for k, v in item().items() if k != "publisher"},
            paper,
            dict(paper, quote="Agents ruined everything in the evaluation set"),
        ]
        db = {"papers": [{"id": "P1", "abstract": "Agents improved recall by 12 percent on the task."}]}
        run_dir = make_run(tmp, {"SQ1_web.jsonl": bad}, {"SQ1": db})
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        lines = out.strip().splitlines()
        assert rc == 1 and len(lines) == 5, out
        assert lines[0].startswith("line 2: quote not found in the cached page"), lines
        assert "unknown stance" in lines[1] and "bad date" in lines[2], lines
        assert "missing required field publisher" in lines[3], lines
        assert lines[4].startswith("line 7: quote not found in the abstract of P1"), lines
        good = make_run(os.path.join(tmp, "g"), {"SQ1_web.jsonl": [item(), paper]}, {"SQ1": db}) \
            if os.makedirs(os.path.join(tmp, "g")) is None else None
        rc, out, _ = run("--run-dir", good, "--lint", os.path.join(good, "collect", "SQ1_web.jsonl"))
        assert rc == 0 and out == "", out
        print("[1] lint: absent quote, unknown enum, bad date, missing field, paper quote; clean file passes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        files = {
            "SQ2_web.jsonl": [item("SQ2")],
            "SQ1_academic.jsonl": [item("SQ1", cluster="journal.org")],
            "SQ1_web.jsonl": [item("SQ1"), item("SQ1", quote="absent from the cached page entirely, really")],
            "SQ3_web.jsonl": [item("SQ3", url="https://example.com/a", cluster="example.com")],
            "SQ4_web.jsonl": [item("SQ4", quote="absent from the cached page entirely, really")],
        }
        run_dir = make_run(tmp, files)
        rc, out, err = run("--run-dir", run_dir, "--offline")
        assert rc == 0, (out, err)
        ev = load_evidence(run_dir)
        assert [(e["id"], e["sq"]) for e in ev] == [
            ("E1", "SQ1"), ("E2", "SQ1"), ("E3", "SQ1"), ("E4", "SQ2"), ("E5", "SQ3"), ("E6", "SQ4")], ev
        assert [e["check"]["status"] for e in ev] == ["pass", "fail", "pass", "pass", "warn", "fail"], \
            [e["check"] for e in ev]
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert gaps["empty_sq"] == ["SQ4"] and [f["id"] for f in gaps["failed"]] == ["E2", "E6"], gaps
        digest = open(os.path.join(run_dir, "digests", "SQ1.md"), encoding="utf-8").read()
        assert "### E1 (B, supports, figure)" in digest and "### E2" not in digest and "### E3" in digest
        assert "Background filler sentence" in digest and "More filler sentence" in digest, digest
        assert "SQ1: pass 2, warn 0, fail 1, independent clusters 2" in out, out
        assert len(out.splitlines()) <= 40
        print("[2] merge: ids in SQ order, web before academic, statuses, digests with context, gaps.json")

        before = {e["id"]: e for e in ev}
        with open(os.path.join(run_dir, "collect", "SQ2_web.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(item("SQ2", claim="Replacement claim.")) + "\n")
        rc, out, err = run("--run-dir", run_dir, "--only", "SQ2", "--offline")
        assert rc == 0, (out, err)
        ev2 = load_evidence(run_dir)
        assert [e["id"] for e in ev2] == ["E1", "E2", "E3", "E5", "E6", "E7"], [e["id"] for e in ev2]
        assert all(before[e["id"]] == e for e in ev2 if e["sq"] != "SQ2")
        assert ev2[-1]["claim"] == "Replacement claim."
        print("[3] --only SQ2: other ids kept, the new item takes E7")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_hardening():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        paper = item(url="https://doi.org/10.1/x", paper="P1", doi="10.1/X",
                     quote="Agents improved recall by 12 percent")
        db = {"papers": [{"id": "P1", "doi": "10.1/x", "abstract": "Agents improved recall by 12 percent."}]}
        files = {"SQ1_web.jsonl": [
            item(quote="Domestic RPA market revenue reached 900 billion yen in fiscal 2025"),
            item(quote="Domestic RPA market revenue reached 100 billion yen in fiscal 2015"),
            paper, dict(paper, doi="10.9/other"),
            dict(paper, quote="Agents improved recall by 13 percent")]}
        run_dir = make_run(tmp, files, {"SQ1": db})
        os.remove(os.path.join(run_dir, "pages", "index.json"))  # the page is found by its cache name
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        lines = out.strip().splitlines()
        assert rc == 1 and len(lines) == 4, out
        assert lines[0] == "line 1: a number in the quote is absent from the page", lines
        assert lines[1] == "line 2: a number in the quote is absent from the page", lines
        assert lines[2] == "line 4: paper id points to a different record", lines
        assert lines[3].startswith("line 5:"), lines
        with open(os.path.join(run_dir, "collect", "papers_SQ1.json"), "w") as f:
            f.write("{broken")
        rc, out, err = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert "line 3: malformed papers db collect/papers_SQ1.json" in out and "Traceback" not in err, (out, err)
        print("[4] lint: altered number, id of a different record, malformed db, index.json absent")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gaps_across_runs():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item("SQ1")], "SQ2_web.jsonl": [item("SQ2")]})
        with open(os.path.join(run_dir, "collect", "SQ1_web.jsonl"), "a", encoding="utf-8") as f:
            f.write("{not json\n")
        with open(os.path.join(run_dir, "brief.md"), "w", encoding="utf-8") as f:
            f.write("- SQ1: first\n- SQ2: second\n- SQ5: no collector file\n")
        run("--run-dir", run_dir, "--offline")
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert gaps["empty_sq"] == ["SQ5"] and gaps["failed"][0]["id"] == "SQ1_web.jsonl:line 2", gaps
        run("--run-dir", run_dir, "--only", "SQ2", "--offline")
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert [f["id"] for f in gaps["failed"]] == ["SQ1_web.jsonl:line 2"], gaps
        print("[5] brief.md lists an SQ with no file as empty; --only keeps the other SQ's shape failures")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_lint()
    test_merge()
    test_lint_hardening()
    test_gaps_across_runs()
    print("OK")
