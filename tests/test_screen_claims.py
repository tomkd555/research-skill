#!/usr/bin/env python3
"""Checks for screen_claims.py.

1. --write puts every sentence of Answer, Findings and Disagreements and limits into batches of
   40 with sids, evidence and context, and removes earlier screen files
2. --apply exits 1 for a missing label, an unknown sid and an unknown label, writing nothing
3. --apply writes screen.json: counts, priority sentences and one fix per uncited fact or
   reading under a source marker
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "research-team", "skills", "research-team", "scripts")
SCRIPT = os.path.join(SCRIPTS, "screen_claims.py")
sys.path.insert(0, SCRIPTS)
import citation_verifier as cv  # noqa: E402

URL = "https://a.com/1"
BODY = ("Filler about the market. " * 30 + "Revenue reached 100 billion yen in fiscal 2025. "
        + "More filler about the outlook. " * 30)

REPORT = """# Title

As of 2026-10-30. Tier: STANDARD.

## Answer
Revenue reached 100 billion yen [E1]. The market looks healthy.

## Findings
### Market
- Revenue grew 5% [E2].
- Vendors launched 3 products.

## Disagreements and limits
Estimates range widely [E1].

Sources, the gaps and the search log: `sources.md`.
"""


def run(run_dir, *args):
    p = subprocess.run([sys.executable, SCRIPT, "--run-dir", run_dir, *args],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def make_run(tmp, report=REPORT):
    d = os.path.join(tmp, "run")
    os.makedirs(os.path.join(d, "pages"))
    ev = [{"id": "E1", "claim": "Revenue reached 100 billion yen.", "url": URL,
           "quote": "Revenue reached 100 billion yen in fiscal 2025", "check": {"status": "pass"}},
          {"id": "E2", "claim": "Revenue grew 5%.", "url": "https://b.com/2",
           "quote": "revenue grew 5 percent", "check": {"status": "pass"}}]
    with open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(e) for e in ev) + "\n")
    with open(os.path.join(d, "pages", cv.cache_name(URL)), "w", encoding="utf-8") as f:
        f.write(f"# url: {URL}\n# accessed: 2026-10-30\n\n{BODY}\n")
    with open(os.path.join(d, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    return d


def batch_sentences(d):
    out = []
    for name in sorted(os.listdir(os.path.join(d, "screen"))):
        if name.startswith("batch_"):
            out += json.load(open(os.path.join(d, "screen", name), encoding="utf-8"))
    return out


def write_labels(d, labels):
    with open(os.path.join(d, "screen", "labels_1.json"), "w", encoding="utf-8") as f:
        json.dump(labels, f)


def test_write_three_sections_batched_with_context():
    tmp = tempfile.mkdtemp(prefix="rt-scr-")
    try:
        d = make_run(tmp)
        os.makedirs(os.path.join(d, "screen"))
        open(os.path.join(d, "screen", "labels_9.json"), "w").write("[]")
        open(os.path.join(d, "screen.json"), "w").write("{}")
        rc, out, err = run(d, "--write")
        got = batch_sentences(d)
        assert rc == 0, (out, err)
        assert [s["sid"] for s in got] == ["S1", "S2", "S3", "S4", "S5", "S6"], got
        assert [s["section"] for s in got] == ["Answer", "Answer", "Findings", "Findings",
                                                "Disagreements and limits", "Disagreements and limits"]
        e1 = got[0]["evidence"][0]
        assert e1["id"] == "E1" and "Filler about the market" in e1["context"], e1
        assert got[2]["evidence"][0]["context"] == "revenue grew 5 percent", got[2]
        assert got[3]["evidence"] == [], got[3]
        assert not os.path.exists(os.path.join(d, "screen", "labels_9.json"))
        assert not os.path.exists(os.path.join(d, "screen.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_batches_hold_forty_sentences():
    tmp = tempfile.mkdtemp(prefix="rt-scr-")
    try:
        lines = "\n".join(f"- Item {n} holds [E1]." for n in range(1, 46))
        d = make_run(tmp, REPORT.replace("- Vendors launched 3 products.", lines))
        run(d, "--write")
        sizes = [len(json.load(open(os.path.join(d, "screen", n), encoding="utf-8")))
                 for n in sorted(os.listdir(os.path.join(d, "screen")))]
        assert sizes == [40, 10], sizes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_apply_invalid_labels_returns_one():
    cases = {
        "missing label": ([{"sid": f"S{n}", "label": "ok", "reason": ""} for n in range(1, 6)],
                          "S6: no label"),
        "unknown sid": ([{"sid": f"S{n}", "label": "ok", "reason": ""} for n in range(1, 8)],
                        "label for unknown sid 'S7'"),
        "unknown label": ([{"sid": f"S{n}", "label": "ok" if n > 1 else "wrong", "reason": ""}
                           for n in range(1, 7)], "S1: unknown label 'wrong'"),
    }
    for name, (labels, expect) in cases.items():
        tmp = tempfile.mkdtemp(prefix="rt-scr-")
        try:
            d = make_run(tmp)
            run(d, "--write")
            write_labels(d, labels)
            rc, out, _ = run(d, "--apply")
            assert rc == 1 and expect in out, (name, out)
            assert not os.path.exists(os.path.join(d, "screen.json")), name
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def test_apply_writes_priority_and_fix():
    tmp = tempfile.mkdtemp(prefix="rt-scr-")
    try:
        d = make_run(tmp)
        run(d, "--write")
        labels = {"S1": "ok", "S2": "own", "S3": "drift", "S4": "uncited_fact", "S5": "own_cited",
                  "S6": "own"}
        write_labels(d, [{"sid": s, "label": l, "reason": "" if l in ("ok", "own") else f"why {s}"}
                         for s, l in labels.items()])
        rc, out, _ = run(d, "--apply")
        screen = json.load(open(os.path.join(d, "screen.json"), encoding="utf-8"))
        assert rc == 0, out
        assert screen["priority"] == ["Revenue grew 5% [E2].", "Vendors launched 3 products.",
                                      "Estimates range widely [E1]."], screen
        assert [(f["sid"], f["label"], f["reason"]) for f in screen["fix"]] == [
            ("S4", "uncited_fact", "why S4"), ("S5", "own_cited", "why S5")], screen["fix"]
        assert screen["counts"]["drift"] == 1 and screen["counts"]["ok"] == 1, screen["counts"]
        assert "screened 6 sentences: 1 drift, 1 uncited facts, 1 readings under a source marker" in out, out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_write_three_sections_batched_with_context()
    test_write_batches_hold_forty_sentences()
    test_apply_invalid_labels_returns_one()
    test_apply_writes_priority_and_fix()
    print("OK")
