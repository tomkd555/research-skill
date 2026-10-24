#!/usr/bin/env python3
"""Checks for select_claims.py.

1. Only cited sentences are candidates; order is Answer, then digit sentences, then the rest
2. --cap cuts the list and the count of dropped candidates is printed
3. Batches hold 5 claims; the evidence carries quote, url and page (null for a paper item)
4. A list item is a sentence boundary; a marker after the full stop stays with its sentence
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


def test_order_and_cap():
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
        assert "7 claims in 2 batches; 0 candidates dropped" in out, out
        assert [len(json.load(open(os.path.join(d, "claims", f"batch_{k}.json")))) for k in (1, 2)] == [5, 2]
        print("[1] order: Answer, digit sentences, rest; list items and trailing markers split correctly")

        open(os.path.join(d, "claims", "verdicts_9.json"), "w").write("[]")
        open(os.path.join(d, "claims", "batch_9.json"), "w").write("[]")
        rc, out, _ = run(d, 3)
        assert sorted(os.listdir(os.path.join(d, "claims"))) == ["batch_1.json"], os.listdir(os.path.join(d, "claims"))
        assert rc == 0 and "3 claims in 1 batches; 4 candidates dropped" in out, out
        assert len(sentences(d)) == 3
        print("[2] --cap 3 keeps 3 and reports 4 dropped; stale batch and verdict files are deleted")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_evidence_shape():
    tmp = tempfile.mkdtemp(prefix="rt-sc-")
    try:
        d = make_run(tmp)
        run(d, 25)
        by = {c["sentence"]: c for c in sentences(d)}
        ev = by["Growth was 12.5% in 2025 [E1, E3]."]["evidence"]
        assert ev == [{"id": "E1", "quote": "q1", "url": "https://a.com/1", "page": PAGE},
                      {"id": "E3", "quote": "q3", "url": "https://doi.org/10.1/x", "page": None}], ev
        assert by["Revenue reached 100 billion yen [E2]."]["evidence"][0]["page"] is None  # not cached
        print("[3] evidence entries carry quote, url and page (null for a paper or an uncached url)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_order_and_cap()
    test_evidence_shape()
    print("OK")
