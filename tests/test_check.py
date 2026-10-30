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


PAPER = item(url="https://doi.org/10.1/x", paper="P1", quote="Agents improved recall by 12 percent")
PAPER_DB = {"papers": [{"id": "P1", "abstract": "Agents improved recall by 12 percent on the task."}]}


def test_lint_invalid_items_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        bad = [
            item(),
            item(quote="a sentence that the page never contains at all, anywhere"),
            item(stance="maybe"),
            item(date="June 2025"),
            {k: v for k, v in item().items() if k != "publisher"},
            PAPER,
            dict(PAPER, quote="Agents ruined everything in the evaluation set"),
        ]
        run_dir = make_run(tmp, {"SQ1_web.jsonl": bad}, {"SQ1": PAPER_DB})
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        lines = out.strip().splitlines()
        assert rc == 1 and len(lines) == 5, out
        assert lines[0].startswith("line 2: quote not found in the cached page"), lines
        assert "unknown stance" in lines[1] and "bad date" in lines[2], lines
        assert "missing required field publisher" in lines[3], lines
        assert lines[4].startswith("line 7: quote not found in the abstract of P1"), lines
        print("[1] lint: absent quote, unknown enum, bad date, missing field, paper quote")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_clean_file_returns_zero():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        good = make_run(tmp, {"SQ1_web.jsonl": [item(), PAPER]}, {"SQ1": PAPER_DB})
        rc, out, _ = run("--run-dir", good, "--lint", os.path.join(good, "collect", "SQ1_web.jsonl"))
        assert rc == 0 and out == "", out
        print("[2] lint: a clean file passes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


MERGE_FILES = {
    "SQ2_web.jsonl": [item("SQ2")],
    "SQ1_academic.jsonl": [item("SQ1", cluster="journal.org")],
    "SQ1_web.jsonl": [item("SQ1"), item("SQ1", quote="absent from the cached page entirely, really")],
    "SQ3_web.jsonl": [item("SQ3", url="https://example.com/a", cluster="example.com")],
    "SQ4_web.jsonl": [item("SQ4", quote="absent from the cached page entirely, really")],
}


def merged_run(tmp):
    run_dir = make_run(tmp, MERGE_FILES)
    rc, out, err = run("--run-dir", run_dir, "--offline")
    assert rc == 0, (out, err)
    return run_dir, out


def test_merge_orders_ids_by_sq_web_before_academic():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        ev = load_evidence(run_dir)
        assert [(e["id"], e["sq"]) for e in ev] == [
            ("E1", "SQ1"), ("E2", "SQ1"), ("E3", "SQ1"), ("E4", "SQ2"), ("E5", "SQ3"), ("E6", "SQ4")], ev
        print("[3] merge: ids in SQ order, web before academic")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_status_per_item_offline():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        ev = load_evidence(run_dir)
        assert [e["check"]["status"] for e in ev] == ["pass", "fail", "pass", "pass", "warn", "fail"], \
            [e["check"] for e in ev]
        print("[4] merge: an absent quote fails, an https item reads warn offline")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_failed_item_in_gaps_json():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert gaps["empty_sq"] == ["SQ4"] and [f["id"] for f in gaps["failed"]] == ["E2", "E6"], gaps
        print("[5] merge: failed items and an SQ with no passing item land in gaps.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_digest_omits_failed_item():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        digest = open(os.path.join(run_dir, "digests", "SQ1.md"), encoding="utf-8").read()
        assert "### E1 (B, supports, figure)" in digest and "### E2" not in digest and "### E3" in digest
        assert "Background filler sentence" in digest and "More filler sentence" in digest, digest
        print("[6] merge: the digest keeps passing items with context and omits the failed one")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_summary_counts_per_sq():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        _, out = merged_run(tmp)
        assert "SQ1: pass 2, warn 0, fail 1, independent clusters 2" in out, out
        assert len(out.splitlines()) <= 40
        print("[7] merge: one summary line per SQ within 40 lines")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_only_sq_other_ids_unchanged():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        before = {e["id"]: e for e in load_evidence(run_dir)}
        with open(os.path.join(run_dir, "collect", "SQ2_web.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(item("SQ2", claim="Replacement claim.")) + "\n")
        rc, out, err = run("--run-dir", run_dir, "--only", "SQ2", "--offline")
        assert rc == 0, (out, err)
        ev2 = load_evidence(run_dir)
        assert [e["id"] for e in ev2] == ["E1", "E2", "E3", "E5", "E6", "E7"], [e["id"] for e in ev2]
        assert all(before[e["id"]] == e for e in ev2 if e["sq"] != "SQ2")
        assert ev2[-1]["claim"] == "Replacement claim."
        print("[8] --only SQ2: other ids kept, the new item takes E7")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def hardening_run(tmp):
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
    return run_dir


def test_lint_altered_number_and_paper_mismatch_return_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = hardening_run(tmp)
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        lines = out.strip().splitlines()
        assert rc == 1 and len(lines) == 4, out
        assert lines[0] == "line 1: a number in the quote is absent from the page", lines
        assert lines[1] == "line 2: a number in the quote is absent from the page", lines
        assert lines[2] == "line 4: paper id points to a different record", lines
        assert lines[3].startswith("line 5:"), lines
        print("[9] lint: altered number, id of a different record, index.json absent")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_malformed_papers_db_reports_line_without_traceback():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = hardening_run(tmp)
        with open(os.path.join(run_dir, "collect", "papers_SQ1.json"), "w") as f:
            f.write("{broken")
        rc, out, err = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert "line 3: malformed papers db collect/papers_SQ1.json" in out and "Traceback" not in err, (out, err)
        print("[10] lint: a malformed papers db is reported against the line")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def gaps_run(tmp):
    run_dir = make_run(tmp, {"SQ1_web.jsonl": [item("SQ1")], "SQ2_web.jsonl": [item("SQ2")]})
    with open(os.path.join(run_dir, "collect", "SQ1_web.jsonl"), "a", encoding="utf-8") as f:
        f.write("{not json\n")
    with open(os.path.join(run_dir, "brief.md"), "w", encoding="utf-8") as f:
        f.write("- SQ1: first\n- SQ2: second\n- SQ5: no collector file\n")
    run("--run-dir", run_dir, "--offline")
    return run_dir


def test_merge_brief_sq_without_file_in_empty_sq():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = gaps_run(tmp)
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert gaps["empty_sq"] == ["SQ5"], gaps
        print("[11] brief.md lists an SQ with no file as empty")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_malformed_line_in_gaps_failed():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = gaps_run(tmp)
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert gaps["failed"][0]["id"] == "SQ1_web.jsonl:line 2", gaps
        print("[12] a malformed line is a failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_only_other_sq_shape_failure_listed():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = gaps_run(tmp)
        run("--run-dir", run_dir, "--only", "SQ2", "--offline")
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert [f["id"] for f in gaps["failed"]] == ["SQ1_web.jsonl:line 2"], gaps
        print("[13] --only keeps the other SQ's shape failures")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def header_number_run(tmp):
    run_dir = make_run(tmp, {})
    with open(os.path.join(run_dir, "pages", cv.cache_name(LOCAL)), "w", encoding="utf-8") as f:
        f.write(f"# url: {LOCAL}\n# accessed: 2026-10-24\n\nMarket revenue reached 13 billion yen in fiscal 2025.\n")
    return run_dir


def test_lint_quote_from_cache_header_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item(quote="accessed: 2026-10-24")]})
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 1 and "line 1" in out, (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_number_only_in_cache_header_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = header_number_run(tmp)
        path = os.path.join(run_dir, "collect", "SQ1_web.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(item(quote="Market revenue reached 10 billion yen in fiscal 2025")) + "\n")
        rc, out, _ = run("--run-dir", run_dir, "--lint", path)
        assert rc == 1 and "number in the quote is absent" in out, (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_misnamed_collector_file_in_gaps_failed():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item("SQ1")], "SQ3b_web.jsonl": [item("SQ3")]})
        rc, out, _ = run("--run-dir", run_dir, "--offline")
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert rc == 0 and "SQ3b_web.jsonl" in out, out
        assert "SQ3b_web.jsonl" in [f["id"] for f in gaps["failed"]], gaps
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_only_lower_case_sq_runs_merge():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, MERGE_FILES)
        rc, out, err = run("--run-dir", run_dir, "--only", "sq1", "--offline")
        assert rc == 0 and out.startswith("SQ1:"), (rc, out, err)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_non_string_url_reports_line_without_traceback():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item(url=123), item(quote=5)]})
        rc, out, err = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 1 and "line 1: field url must be a string" in out, (rc, out, err)
        assert "line 2: field quote must be a string" in out and "Traceback" not in err, (out, err)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_non_string_url_item_fails_without_traceback():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item(url=123), item()]})
        rc, out, err = run("--run-dir", run_dir, "--offline")
        assert rc == 0 and "Traceback" not in err, (rc, out, err)
        assert [i["check"]["status"] for i in load_evidence(run_dir)][0] == "fail"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_digest_header_has_status_and_cluster():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        digest = open(os.path.join(run_dir, "digests", "SQ1.md"), encoding="utf-8").read()
        assert "### E1 (B, supports, figure) pass, cluster example.com" in digest, digest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_sq_differs_from_file_name_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item("1")]})
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 1 and "line 1" in out and "SQ1" in out, (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_sq_differs_from_file_name_in_gaps_failed():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item("1")]})
        run("--run-dir", run_dir, "--offline")
        gaps = json.load(open(os.path.join(run_dir, "gaps.json"), encoding="utf-8"))
        assert [f["id"] for f in gaps["failed"]] == ["SQ1_web.jsonl:line 1"], gaps
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_check_detail_omits_empty_quote_note():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        assert all("no verbatim_quote" not in i["check"]["detail"] for i in load_evidence(run_dir))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_summary_line_on_stderr_for_clean_file():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item(), item(quote="absent from the cached page entirely, really")]})
        rc, out, err = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 1 and err.strip() == "2 items, 1 failing" and "items" not in out, (out, err)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_misnamed_collector_file_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1-web.jsonl": [item()]})
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1-web.jsonl"))
        assert rc == 1 and "SQ1-web.jsonl" in out, (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_misnamed_file_summary_counts_items_only():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1-web.jsonl": [item()]})
        rc, _, err = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1-web.jsonl"))
        assert rc == 1 and err.strip() == "1 items, 0 failing", (rc, err)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_quote_dropped_negation_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item()]})
        with open(os.path.join(run_dir, "pages", cv.cache_name(LOCAL)), "w", encoding="utf-8") as f:
            f.write(f"# url: {LOCAL}\n# accessed: 2026-10-30\n\n{BODY} Remote work did not increase "
                    "productivity among call-centre employees over the nine-month period.\n")
        with open(os.path.join(run_dir, "collect", "SQ1_web.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(item(quote="Remote work did increase productivity among call-centre "
                                          "employees over the nine-month period.")) + "\n")
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 1 and "line 1: quote not verbatim" in out, (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_quote_differs_in_space_quotes_dashes_returns_zero():
    """Whitespace, curly quotes, dashes and soft hyphens are the only differences a quote may carry."""
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item()]})
        with open(os.path.join(run_dir, "pages", cv.cache_name(LOCAL)), "w", encoding="utf-8") as f:
            f.write(f"# url: {LOCAL}\n# accessed: 2026-10-30\n\n{BODY} The so‑called “pilot "
                    "phase” ended in 2025 — a year early; 国内の 生成 AI市場は拡­大した。\n")
        quotes = ['The so-called "pilot phase" ended in 2025 - a year early',
                  "国内の生成AI市場は拡大した。"]
        with open(os.path.join(run_dir, "collect", "SQ1_web.jsonl"), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(item(quote=q)) + "\n" for q in quotes))
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 0 and out == "", (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_paper_items_distinct_doi_two_clusters():
    db = {"papers": [{"id": "P1", "doi": "10.1/a", "abstract": "Agents improved recall by 12 percent."},
                     {"id": "P2", "doi": "10.1/b", "abstract": "Agents lowered cost by 30 percent."}]}
    a = item(url="https://doi.org/10.1/a", paper="P1", doi="10.1/a", cluster="doi.org",
             quote="Agents improved recall by 12 percent")
    b = item(url="https://doi.org/10.1/b", paper="P2", doi="10.1/b", cluster="doi.org",
             quote="Agents lowered cost by 30 percent")
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_academic.jsonl": [a, b]}, {"SQ1": db})
        rc, out, _ = run("--run-dir", run_dir, "--offline")
        assert rc == 0 and "independent clusters 2" in out, out
        assert [e["cluster"] for e in load_evidence(run_dir)] == ["doi:10.1/a", "doi:10.1/b"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_merge_account_cluster_refined_custom_cluster_kept():
    """A domain-valued cluster on a platform host becomes the account; any other value stays."""
    urls = ["https://github.com/acme/tool", "https://github.com/beta/lib", "https://medium.com/@x/p"]
    items = [item(url=urls[0], cluster="github.com"), item(url=urls[1], cluster="github.com"),
             item(url=urls[2], cluster="press-origin.com")]
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": items})
        for url in urls:
            with open(os.path.join(run_dir, "pages", cv.cache_name(url)), "w", encoding="utf-8") as f:
                f.write(f"# url: {url}\n# accessed: 2026-10-30\n\n{BODY}\n")
        run("--run-dir", run_dir, "--offline")
        clusters = [e["cluster"] for e in load_evidence(run_dir)]
        assert clusters == ["github.com/acme", "github.com/beta", "press-origin.com"], clusters
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


OPPOSING = item(url="https://example.com/a", stance="opposes",
                quote="More filler sentence about the outlook.")


def test_append_opposing_item_takes_next_id_others_unchanged():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        before = load_evidence(run_dir)
        path = os.path.join(run_dir, "claims", "opposing.jsonl")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(OPPOSING) + "\n")
        rc, out, _ = run("--run-dir", run_dir, "--append", path, "--offline")
        after = load_evidence(run_dir)
        new_id = f"E{max(int(e['id'][1:]) for e in before) + 1}"
        assert rc == 0 and after[:len(before)] == before and after[-1]["id"] == new_id, (rc, out)
        assert out.startswith(new_id), out
        with open(os.path.join(run_dir, "digests", "SQ1.md"), encoding="utf-8") as f:
            assert f"### {new_id} " in f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_append_same_item_twice_added_once():
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir, _ = merged_run(tmp)
        n = len(load_evidence(run_dir))
        path = os.path.join(run_dir, "opposing.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(OPPOSING) + "\n")
        run("--run-dir", run_dir, "--append", path, "--offline")
        run("--run-dir", run_dir, "--append", path, "--offline")
        assert len(load_evidence(run_dir)) == n + 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lint_headerless_cache_first_paragraph_quote_returns_zero():
    """A cache file with no `# url:` header is page text from its first line."""
    tmp = tempfile.mkdtemp(prefix="rt-check-")
    try:
        run_dir = make_run(tmp, {"SQ1_web.jsonl": [item()]})
        with open(os.path.join(run_dir, "pages", cv.cache_name(LOCAL)), "w", encoding="utf-8") as f:
            f.write(f"{BODY}\n\nA second paragraph of the page.\n")
        rc, out, _ = run("--run-dir", run_dir, "--lint", os.path.join(run_dir, "collect", "SQ1_web.jsonl"))
        assert rc == 0 and out == "", (rc, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_lint_invalid_items_returns_one()
    test_lint_clean_file_returns_zero()
    test_merge_orders_ids_by_sq_web_before_academic()
    test_merge_status_per_item_offline()
    test_merge_failed_item_in_gaps_json()
    test_merge_digest_omits_failed_item()
    test_merge_summary_counts_per_sq()
    test_merge_only_sq_other_ids_unchanged()
    test_lint_altered_number_and_paper_mismatch_return_one()
    test_lint_malformed_papers_db_reports_line_without_traceback()
    test_merge_brief_sq_without_file_in_empty_sq()
    test_merge_malformed_line_in_gaps_failed()
    test_merge_only_other_sq_shape_failure_listed()
    test_lint_quote_from_cache_header_returns_one()
    test_lint_number_only_in_cache_header_returns_one()
    test_merge_misnamed_collector_file_in_gaps_failed()
    test_merge_only_lower_case_sq_runs_merge()
    test_lint_non_string_url_reports_line_without_traceback()
    test_merge_non_string_url_item_fails_without_traceback()
    test_merge_digest_header_has_status_and_cluster()
    test_lint_sq_differs_from_file_name_returns_one()
    test_merge_sq_differs_from_file_name_in_gaps_failed()
    test_merge_check_detail_omits_empty_quote_note()
    test_lint_summary_line_on_stderr_for_clean_file()
    test_lint_misnamed_collector_file_returns_one()
    test_lint_headerless_cache_first_paragraph_quote_returns_zero()
    test_lint_misnamed_file_summary_counts_items_only()
    test_lint_quote_dropped_negation_returns_one()
    test_lint_quote_differs_in_space_quotes_dashes_returns_zero()
    test_merge_paper_items_distinct_doi_two_clusters()
    test_merge_account_cluster_refined_custom_cluster_kept()
    test_append_opposing_item_takes_next_id_others_unchanged()
    test_append_same_item_twice_added_once()
    print("OK")
