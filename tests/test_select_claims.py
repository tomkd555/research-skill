#!/usr/bin/env python3
"""Checks for select_claims.py.

1. Only cited sentences are candidates; order is Answer, then digit sentences, then the rest
2. --cap cuts the list and the count of dropped candidates is printed
3. Batches hold 5 claims; the evidence carries quote, url and page (null for a paper item)
4. A list item is a sentence boundary; a marker after the full stop stays with its sentence
5. With screen.json, its priority sentences come first, also after a small rewording
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "research-team", "skills", "research-team", "scripts")
SCRIPT = os.path.join(SCRIPTS, "select_claims.py")
sys.path.insert(0, SCRIPTS)
import citation_verifier as cv  # noqa: E402

PAGE = "pages/" + cv.cache_name("https://a.com/1")

REPORT = """# Title

As of 2026-10-24. Tier: STANDARD.

## Answer
Adoption is spreading [E1]. Revenue reached 100 billion yen [E2].

## Findings
### Market
Vendors differ in approach [E1]. Uncited sentence without a marker.
- Growth was 12.5% in 2025 [E1, E3].
- Buyers want support. [E2]
- Prices fell by 3% [E3].

## Disagreements and limits
Estimates range widely [E2].
"""


def run(run_dir, cap):
    p = subprocess.run([sys.executable, SCRIPT, "--run-dir", run_dir, "--cap", str(cap)],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def make_run(tmp):
    d = os.path.join(tmp, "run")
    os.makedirs(os.path.join(d, "pages"))
    ev = [{"id": "E1", "quote": "q1", "url": "https://a.com/1"},
          {"id": "E2", "quote": "q2", "url": "https://a.com/2"},
          {"id": "E3", "quote": "q3", "url": "https://doi.org/10.1/x", "paper": "P1"}]
    with open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(e) for e in ev) + "\n")
    # the page exists on disk but index.json lost its entry: the lookup uses the cache name
    open(os.path.join(d, PAGE), "w", encoding="utf-8").write("body")
    with open(os.path.join(d, "pages", "index.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    with open(os.path.join(d, "report.md"), "w", encoding="utf-8") as f:
        f.write(REPORT)
    return d


def sentences(d):
    out = []
    for name in sorted(os.listdir(os.path.join(d, "claims"))):
        out += json.load(open(os.path.join(d, "claims", name), encoding="utf-8"))
    return out


def test_cited_sentences_order():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        rc, out, err = run(d, 25)
        assert rc == 0, (out, err)
        claims = sentences(d)
        assert [c["sentence"] for c in claims] == [
            "Adoption is spreading [E1].",
            "Revenue reached 100 billion yen [E2].",
            "Growth was 12.5% in 2025 [E1, E3].",
            "Prices fell by 3% [E3].",
            "Vendors differ in approach [E1].",
            "Buyers want support. [E2]",
            "Estimates range widely [E2].",
        ], [c["sentence"] for c in claims]
        assert [c["cid"] for c in claims] == [f"C{n}" for n in range(1, 8)]
        print("[1] order: Answer, digit sentences, rest; list items and trailing markers split correctly")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_batches_of_five_claims():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        rc, out, err = run(d, 25)
        assert rc == 0, (out, err)
        assert "7 claims in 2 batches; 0 candidates dropped" in out, out
        assert [len(json.load(open(os.path.join(d, "claims", f"batch_{k}.json")))) for k in (1, 2)] == [5, 2]
        print("[2] 7 claims split into batches of 5 and 2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cap_drops_candidates():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        run(d, 25)
        open(os.path.join(d, "claims", "verdicts_9.json"), "w").write("[]")
        open(os.path.join(d, "claims", "batch_9.json"), "w").write("[]")
        rc, out, _ = run(d, 3)
        assert sorted(os.listdir(os.path.join(d, "claims"))) == ["batch_1.json"], os.listdir(os.path.join(d, "claims"))
        assert rc == 0 and "3 claims in 1 batches; 4 candidates dropped" in out, out
        assert len(sentences(d)) == 3
        print("[3] --cap 3 keeps 3 and reports 4 dropped; stale batch and verdict files are deleted")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_evidence_page_set_for_cached_url_null_otherwise():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        run(d, 25)
        by = {c["sentence"]: c for c in sentences(d)}
        ev = by["Growth was 12.5% in 2025 [E1, E3]."]["evidence"]
        assert ev == [{"id": "E1", "quote": "q1", "url": "https://a.com/1", "page": PAGE},
                      {"id": "E3", "quote": "q3", "url": "https://doi.org/10.1/x", "page": None}], ev
        assert by["Revenue reached 100 billion yen [E2]."]["evidence"][0]["page"] is None  # not cached
        print("[4] evidence entries carry quote, url and page (null for a paper or an uncached url)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rerun_removes_stale_verdicts_json():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        stale = os.path.join(d, "verdicts.json")
        open(stale, "w").write("{}")
        run(d, 25)
        assert not os.path.exists(stale)
        print("[5] a rerun removes verdicts.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_or_failed_evidence_sentence_skipped():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        ev = [{"id": "E1", "quote": "q1", "url": "https://a.com/1", "check": {"status": "pass"}},
              {"id": "E2", "quote": "q2", "url": "https://a.com/2", "check": {"status": "fail"}}]
        open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8").write(
            "\n".join(json.dumps(e) for e in ev) + "\n")
        rc, out, _ = run(d, 25)
        by = {c["sentence"]: c for c in sentences(d)}
        assert [e["id"] for e in by["Growth was 12.5% in 2025 [E1, E3]."]["evidence"]] == ["E1"]
        assert "Revenue reached 100 billion yen [E2]." not in by
        assert "Prices fell by 3% [E3]." not in by
        assert "skipped" in out and "Prices fell by 3% [E3]." in out, out
        print("[6] evidence that is missing or failed is dropped; a sentence left bare is skipped")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_paper_abstract_written_and_page_set():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        os.makedirs(os.path.join(d, "collect"))
        json.dump({"papers": [{"id": "P1", "abstract": "The abstract text."}]},
                  open(os.path.join(d, "collect", "papers_SQ1.json"), "w", encoding="utf-8"))
        ev = [{"id": "E1", "quote": "q1", "url": "https://a.com/1"},
              {"id": "E2", "quote": "q2", "url": "https://a.com/2"},
              {"id": "E3", "quote": "q3", "url": "https://doi.org/10.1/x", "paper": "P1", "sq": "SQ1"}]
        open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8").write(
            "\n".join(json.dumps(e) for e in ev) + "\n")
        run(d, 25)
        by = {c["sentence"]: c for c in sentences(d)}
        page = by["Prices fell by 3% [E3]."]["evidence"][0]["page"]
        assert page == "abstracts/E3.txt", page
        assert open(os.path.join(d, page), encoding="utf-8").read() == "The abstract text."
        print("[7] a paper item gets its abstract as the page")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_table_rows_sent_as_single_claims():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        path = os.path.join(d, "report.md")
        report = open(path, encoding="utf-8").read().replace(
            "- Prices fell by 3% [E3].",
            "| Vendor | Share |\n|---|---|\n| Acme | 41% [E1] |\n| Beta | 9% [E2] |")
        open(path, "w", encoding="utf-8").write(report)
        run(d, 25)
        sent = [c["sentence"] for c in sentences(d)]
        assert "| Acme | 41% [E1] |" in sent and "| Beta | 9% [E2] |" in sent, sent
        print("[8] each table row is one claim")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_screen_priority_sentences_first():
    """A flagged sentence, and one the writer reworded while citing it, lead the order."""
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        with open(os.path.join(d, "screen.json"), "w", encoding="utf-8") as f:
            json.dump({"priority": ["Prices fell by 3%.", "Estimates vary widely."]}, f)
        rc, out, _ = run(d, 3)
        got = [c["sentence"] for c in sentences(d)]
        assert rc == 0 and got == ["Prices fell by 3% [E3].", "Estimates range widely [E2].",
                                   "Adoption is spreading [E1]."], got
        assert "2 screen priority sentences within the cap" in out, out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_cited_sentences_order()
    test_batches_of_five_claims()
    test_cap_drops_candidates()
    test_evidence_page_set_for_cached_url_null_otherwise()
    test_rerun_removes_stale_verdicts_json()
    test_missing_or_failed_evidence_sentence_skipped()
    test_paper_abstract_written_and_page_set()
    test_table_rows_sent_as_single_claims()
    test_screen_priority_sentences_first()
    print("OK")
