#!/usr/bin/env python3
"""Checks for report_check.py.

1. A clean report passes and sources.md lists cited items, uncited items, gaps and searches
2. Failing cases: missing heading, dangling marker, marker on a failed item, uncited number,
   a patched sentence that remains
3. A number inside a marker, a decimal or a name such as GPT-4 does not trigger the uncited-number rule
4. --translation: a dropped marker, a changed number and a changed heading count each report
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "research-team", "skills", "research-team", "scripts",
                      "report_check.py")

REPORT = """# Title

As of 2026-10-24. Tier: STANDARD.

## Answer
Revenue reached 100 billion yen [E1]. Adoption is spreading across industries.

## Findings
### Market size
- Revenue grew 12.5% in 2025 [E1, E2].
- Vendors differ in approach.

## Disagreements and limits
Estimates range widely.
"""


def run(run_dir, *args):
    p = subprocess.run([sys.executable, SCRIPT, "--run-dir", run_dir, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def make_run(tmp, report=REPORT, patch=None):
    d = os.path.join(tmp, "run")
    os.makedirs(os.path.join(d, "collect"))
    ev = [{"id": f"E{i}", "sq": "SQ1", "publisher": "Pub", "title": f"Title {i}", "date": "2025",
           "grade": "B", "url": f"https://e.com/{i}", "check": {"status": s}}
          for i, s in ((1, "pass"), (2, "warn"), (3, "fail"), (4, "pass"))]
    with open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(e) for e in ev) + "\n")
    with open(os.path.join(d, "collect", "searches_SQ1_web.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"query": "rpa market", "purpose": "search", "results": 8, "new_sources": 3}) + "\n")
    with open(os.path.join(d, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    if patch is not None:
        with open(os.path.join(d, "verdicts.json"), "w", encoding="utf-8") as f:
            json.dump({"verdicts": [], "patch": patch}, f)
    return d


def test_clean_and_sources():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)
        rc, out, err = run(d)
        assert rc == 0, (out, err)
        src = open(os.path.join(d, "sources.md"), encoding="utf-8").read()
        assert "| E1 | Pub | Title 1 |" in src and "| E2 |" in src, src
        assert "- E4:" in src and "E3:" not in src.split("## Gaps")[0], src
        assert "| rpa market | search | 8 | 3 |" in src, src
        print("[1] clean report passes; sources.md has cited, uncited, gaps and search rows")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_failures():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        cases = {
            "missing heading": (REPORT.replace("## Disagreements and limits", "## Limits"),
                                None, "missing heading: ## Disagreements and limits"),
            "dangling marker": (REPORT.replace("[E1]", "[E9]"), None, "dangling marker E9"),
            "marker on a failed item": (REPORT.replace("[E1]", "[E3]"), None, "dangling marker E3"),
            "uncited number": (REPORT.replace("Vendors differ in approach.", "3 vendors lead."),
                               None, "uncited number in Findings: 3 vendors lead."),
        }
        for name, (report, patch, expect) in cases.items():
            sub = os.path.join(tmp, name.replace(" ", "_"))
            os.makedirs(sub)
            rc, out, _ = run(make_run(sub, report, patch))
            assert rc == 1 and expect in out, (name, out)
        sub = os.path.join(tmp, "patched")
        os.makedirs(sub)
        patch = [{"cid": "C1", "sentence": "Revenue reached 100 billion yen [E1].",
                  "verdict": "partial", "action": "narrow"}]
        rc, out, _ = run(make_run(sub, patch=patch))
        assert rc == 1 and "patched sentence C1 (partial) remains" in out, out
        sub = os.path.join(tmp, "patched_gone")
        os.makedirs(sub)
        patch[0]["sentence"] = "Revenue reached 90 billion yen [E1]."
        rc, out, _ = run(make_run(sub, patch=patch))
        assert rc == 0, out
        print("[2] missing heading, dangling marker, failed-item marker, uncited number, patched sentence")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_number_edges():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        # the marker's own digits are ignored: this sentence has no digit outside it
        report = REPORT.replace("Vendors differ in approach.", "Vendors differ in approach [E4].")
        rc, out, _ = run(make_run(tmp, report))
        assert rc == 0, out
        sub = os.path.join(tmp, "b")
        os.makedirs(sub)
        report = REPORT.replace("Vendors differ in approach.", "The model GPT-4 helps.")
        rc, out, _ = run(make_run(sub, report))
        assert rc == 0, out
        sub2 = os.path.join(tmp, "c")
        os.makedirs(sub2)
        report = REPORT.replace("Vendors differ in approach.", "It costs 10k tokens.")
        rc, out, _ = run(make_run(sub2, report))
        assert rc == 1 and "uncited number in Findings: It costs 10k tokens." in out, out
        print("[3] digits inside a marker or a name (GPT-4) are ignored; a figure needs its own marker")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_abbreviations():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        text = ("Acme Inc. grew 5% vs. peers, e.g. J. Smith et al. in the U.S. and 3.5% in Mar. 2025 [E1].")
        report = REPORT.replace("Vendors differ in approach.", text)
        rc, out, _ = run(make_run(tmp, report))
        assert rc == 0, out
        print("[5] a period after vs, e.g, Inc, al, Mar or an initial does not end a sentence")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_translation():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)

        def check(text):
            with open(os.path.join(d, "report.ja.md"), "w", encoding="utf-8") as f:
                f.write(text)
            return run(d, "--translation", "report.ja.md")

        rc, out, _ = check(REPORT.replace("Adoption is spreading across industries.", "普及が進んでいます。"))
        assert rc == 0, out
        rc, out, _ = check(REPORT.replace(" [E1, E2]", " [E1]"))
        assert rc == 1 and "marker sequence differs" in out, out
        rc, out, _ = check(REPORT.replace("12.5%", "12.6%"))
        assert rc == 1 and "numbers differ" in out, out
        rc, out, _ = check(REPORT.replace("### Market size\n", ""))
        assert rc == 1 and "heading count differs: report 5 / translation 4" in out, out
        print("[4] translation: clean pass; dropped marker, changed number, changed heading count")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_clean_and_sources()
    test_failures()
    test_number_edges()
    test_abbreviations()
    test_translation()
    print("OK")
