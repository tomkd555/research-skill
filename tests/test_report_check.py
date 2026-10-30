#!/usr/bin/env python3
"""Checks for report_check.py.

1. A clean report passes and sources.md lists cited items, uncited items, gaps and searches
2. Failing cases: missing heading, dangling marker, marker on a failed item, a patched sentence
   that remains
3. Sentence boundaries: a stop ends a sentence; an abbreviation or "No. 5" does not; table rows
   are units and the header row is skipped
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
sys.path.insert(0, os.path.dirname(SCRIPT))
import report_check as rcm  # noqa: E402

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


def test_clean_report_returns_zero():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)
        rc, out, err = run(d)
        assert rc == 0, (out, err)
        print("[1] clean report passes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_clean_report_writes_sources_md():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)
        run(d)
        src = open(os.path.join(d, "sources.md"), encoding="utf-8").read()
        assert "| E1 | Pub | Title 1 |" in src and "| E2 |" in src, src
        assert "- E4:" in src and "E3:" not in src.split("## Gaps")[0], src
        assert "| rpa market | search | 8 | 3 |" in src, src
        print("[2] sources.md has cited, uncited, gaps and search rows")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_report_violations_return_one():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        cases = {
            "missing heading": (REPORT.replace("## Disagreements and limits", "## Limits"),
                                None, "missing heading: ## Disagreements and limits"),
            "dangling marker": (REPORT.replace("[E1]", "[E9]"), None, "dangling marker E9"),
            "marker on a failed item": (REPORT.replace("[E1]", "[E3]"), None, "dangling marker E3"),
        }
        for name, (report, patch, expect) in cases.items():
            sub = os.path.join(tmp, name.replace(" ", "_"))
            os.makedirs(sub)
            rc, out, _ = run(make_run(sub, report, patch))
            assert rc == 1 and expect in out, (name, out)
        print("[3] missing heading, dangling marker, failed-item marker")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


PATCH = [{"cid": "C1", "sentence": "Revenue reached 100 billion yen [E1].",
          "verdict": "partial", "action": "narrow"}]


def test_patched_sentence_remaining_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        rc, out, _ = run(make_run(tmp, patch=PATCH))
        assert rc == 1 and "patched sentence C1 (partial) remains" in out, out
        print("[4] a patched sentence that remains fails")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_patched_sentence_removed_returns_zero():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        patch = [dict(PATCH[0], sentence="Revenue reached 90 billion yen [E1].")]
        rc, out, _ = run(make_run(tmp, patch=patch))
        assert rc == 0, out
        print("[5] a patched sentence that is gone passes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_abbreviation_periods_single_sentence_returns_zero():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        text = ("Acme Inc. grew 5% vs. peers, e.g. J. Smith et al. in the U.S. and 3.5% in Mar. 2025 [E1].")
        report = REPORT.replace("Vendors differ in approach.", text)
        rc, out, _ = run(make_run(tmp, report))
        assert rc == 0, out
        print("[9] a period after vs, e.g, Inc, al, Mar or an initial does not end a sentence")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_translation(text):
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)
        with open(os.path.join(d, "report.ja.md"), "w", encoding="utf-8") as f:
            f.write(text)
        return run(d, "--translation", "report.ja.md")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_translation_clean_returns_zero():
    rc, out, _ = check_translation(
        REPORT.replace("Adoption is spreading across industries.", "普及が進んでいます。"))
    assert rc == 0, out
    print("[10] translation: clean pass")


def test_translation_dropped_marker_returns_one():
    rc, out, _ = check_translation(REPORT.replace(" [E1, E2]", " [E1]"))
    assert rc == 1 and "marker sequence differs" in out, out
    print("[11] translation: dropped marker")


def test_translation_changed_number_returns_one():
    rc, out, _ = check_translation(REPORT.replace("12.5%", "12.6%"))
    assert rc == 1 and "numbers differ" in out, out
    print("[12] translation: changed number")


def test_translation_changed_heading_count_returns_one():
    rc, out, _ = check_translation(REPORT.replace("### Market size\n", ""))
    assert rc == 1 and "heading count differs: report 5 / translation 4" in out, out
    print("[13] translation: changed heading count")


def uncited_in(report_fragment):
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        report = REPORT.replace("- Vendors differ in approach.", report_fragment)
        return run(make_run(tmp, report))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sentences_of(report_fragment):
    """The sentences report_sentences yields once the fragment replaces a Findings line."""
    report = REPORT.replace("- Vendors differ in approach.", report_fragment)
    return [s for _, s in rcm.report_sentences(report)]


def test_report_sentences_stop_ends_sentence():
    cases = {
        "ms unit": ("- Median latency was 200 ms. Throughput reached 5,000 rps [E1].",
                    "Median latency was 200 ms."),
        "closing quote": ('- The vendor says "latency drops 50%." Tests found 20% [E1].',
                          'The vendor says "latency drops 50%."'),
        "said no": ("- Sales rose 5% last year, said no. Prices fell 3% [E1].",
                    "Sales rose 5% last year, said no."),
    }
    for name, (fragment, first) in cases.items():
        assert first in sentences_of(fragment), (name, sentences_of(fragment))


def test_report_sentences_abbreviation_single_sentence():
    for name, line in {"no before digit": "Standard No. 5 sets a limit of 3% [E1].",
                       "co": "In 2024 Toyota Motor Co. sold 10 million vehicles [E1].",
                       "ms title": "Ms. Lee reported 5% growth [E1]."}.items():
        assert line in sentences_of("- " + line), (name, sentences_of("- " + line))


def test_report_sentences_table_rows_separate_header_skipped():
    got = sentences_of("| Vendor | 2025 |\n|---|---|\n| Acme | 41% |\n| - | - |\n| Gamma | 26% [E4] |")
    assert "| Acme | 41% |" in got and "| Gamma | 26% [E4] |" in got, got
    assert not any("Vendor" in s or "---" in s for s in got), got


def test_table_header_row_dangling_marker_returns_one():
    rc, out, _ = uncited_in("| Metric | FY2025 [E9] |\n|---|---|\n| Revenue | 5% [E1] |")
    assert rc == 1 and "dangling marker E9" in out, out


def test_malformed_marker_returns_one():
    for bad in ("[E1-E3]", "[E1; E4]", "[e2]"):
        rc, out, _ = uncited_in(f"- Vendors converge on one design {bad}.")
        assert rc == 1 and f"malformed marker: {bad}" in out, (bad, out)
    print("[15] a bracket that starts like a marker and does not parse fails")


def test_batches_without_verdicts_json_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-rc-")
    try:
        d = make_run(tmp)
        os.makedirs(os.path.join(d, "claims"))
        open(os.path.join(d, "claims", "batch_1.json"), "w").write("[]")
        rc, out, _ = run(d)
        assert rc == 1 and "verification incomplete" in out, out
        print("[16] batches without verdicts.json fail as verification incomplete")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_clean_report_returns_zero()
    test_clean_report_writes_sources_md()
    test_report_violations_return_one()
    test_patched_sentence_remaining_returns_one()
    test_patched_sentence_removed_returns_zero()
    test_abbreviation_periods_single_sentence_returns_zero()
    test_translation_clean_returns_zero()
    test_translation_dropped_marker_returns_one()
    test_translation_changed_number_returns_one()
    test_translation_changed_heading_count_returns_one()
    test_report_sentences_stop_ends_sentence()
    test_report_sentences_abbreviation_single_sentence()
    test_report_sentences_table_rows_separate_header_skipped()
    test_malformed_marker_returns_one()
    test_batches_without_verdicts_json_returns_one()
    test_table_header_row_dangling_marker_returns_one()
    print("OK")
