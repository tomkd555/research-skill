#!/usr/bin/env python3
"""Checks for apply_verdicts.py.

1. All verdicts present: verdicts.json carries every claim, the patch lists the non-supported
   ones with the contract's action wording
2. Failing cases: a batch claim with no verdict, an unknown cid, an unknown verdict value, a
   duplicate cid; each exits 1 and writes nothing
3. A verdict file that is not a list exits 2
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "research-team", "skills", "research-team", "scripts",
                      "apply_verdicts.py")


def run(run_dir):
    p = subprocess.run([sys.executable, SCRIPT, "--run-dir", run_dir],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def claim(n):
    return {"cid": f"C{n}", "sentence": f"Sentence {n} [E{n}].",
            "evidence": [{"id": f"E{n}", "quote": "q", "url": "https://a.com", "page": None}]}


def verdict(n, v="supported"):
    return {"cid": f"C{n}", "verdict": v, "reason": "r", "found": "f", "source": "https://a.com"}


def make_run(tmp, verdicts):
    d = os.path.join(tmp, "run")
    os.makedirs(os.path.join(d, "claims"))
    dump = lambda name, data: json.dump(data, open(os.path.join(d, "claims", name), "w", encoding="utf-8"))
    dump("batch_1.json", [claim(n) for n in range(1, 4)])
    dump("batch_2.json", [claim(4)])
    dump("verdicts_1.json", verdicts[0])
    dump("verdicts_2.json", verdicts[1])
    return d


def test_all_verdicts_present_writes_verdicts_and_patch():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([verdict(1), verdict(2, "partial"), verdict(3, "contradicted")],
                           [verdict(4, "unsupported")]))
        rc, out, err = run(d)
        assert rc == 0, (out, err)
        data = json.load(open(os.path.join(d, "verdicts.json"), encoding="utf-8"))
        assert [v["cid"] for v in data["verdicts"]] == ["C1", "C2", "C3", "C4"]
        assert data["verdicts"][0]["evidence_ids"] == ["E1"] and data["verdicts"][0]["reason"] == "r"
        assert [(p["cid"], p["action"]) for p in data["patch"]] == [
            ("C2", "narrow the sentence to what the quote supports"),
            ("C3", "state both sources"),
            ("C4", "remove the sentence or replace its support with a passing item")], data["patch"]
        assert "supported 1, partial 1, unsupported 1, contradicted 1" in out, out
        print("[1] verdicts.json and the patch list, with the contract's action wording")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_invalid_verdicts_return_one():
    cases = {
        "missing verdict": (([verdict(1), verdict(2), verdict(3)], []), "C4: no verdict"),
        "unknown cid": (([verdict(1), verdict(2), verdict(3), verdict(9)], [verdict(4)]),
                        "unknown cid 'C9'"),
        "unknown verdict": (([verdict(1), verdict(2, "mostly"), verdict(3)], [verdict(4)]),
                            "C2: unknown verdict value 'mostly'"),
        "duplicate": (([verdict(1), verdict(1), verdict(2), verdict(3)], [verdict(4)]),
                      "C1: more than one verdict"),
    }
    for name, (verdicts, expect) in cases.items():
        tmp = tempfile.mkdtemp(prefix="rt-av-")
        try:
            d = make_run(tmp, verdicts)
            rc, out, _ = run(d)
            assert rc == 1 and expect in out, (name, out)
            assert not os.path.exists(os.path.join(d, "verdicts.json")), name
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("[2] missing verdict, unknown cid, unknown verdict value and duplicate exit 1")


def test_claim_in_two_batches_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([verdict(1), verdict(2), verdict(3)], [verdict(4)]))
        json.dump([claim(1)], open(os.path.join(d, "claims", "batch_3.json"), "w", encoding="utf-8"))
        rc, out, _ = run(d)
        assert rc == 1 and "C1: appears in more than one batch" in out, out
        print("[3] a claim in two batches exits 1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verdict_file_not_list_returns_two():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([], []))
        open(os.path.join(d, "claims", "verdicts_1.json"), "w").write('{"cid": "C1"}')
        rc, _, err = run(d)
        assert rc == 2 and "expected a JSON list" in err, (rc, err)
        print("[4] a verdict file that is not a list exits 2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verdict_file_malformed_json_error_names_file():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([], []))
        open(os.path.join(d, "claims", "verdicts_2.json"), "w").write('[{"cid": "C4" "verdict"')
        rc, _, err = run(d)
        assert rc == 2 and "verdicts_2.json" in err, (rc, err)
        print("[5] a parse error names the verdict file")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verdict_entry_not_object_returns_one():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([verdict(1), verdict(2), verdict(3)], ["C4"]))
        rc, out, err = run(d)
        assert rc == 1 and "verdicts_2.json: item 1 is not a JSON object" in out, (rc, out, err)
        print("[6] a non-object entry is listed and exits 1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_verdict_line_names_batch_file():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        d = make_run(tmp, ([verdict(1), verdict(2), verdict(3)], []))
        rc, out, _ = run(d)
        assert rc == 1 and "C4: no verdict" in out and "batch_2.json" in out, out
        print("[7] a missing verdict names its batch file")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_patch_entries_carry_reason_found_source():
    tmp = tempfile.mkdtemp(prefix="rt-av-")
    try:
        long_reason = "drops the word often " + "x" * 150
        v = dict(verdict(2, "partial"), reason=long_reason, found="teams often adopted it")
        d = make_run(tmp, ([verdict(1), v, verdict(3)], [verdict(4)]))
        rc, out, _ = run(d)
        assert rc == 0, out
        patch = json.load(open(os.path.join(d, "verdicts.json"), encoding="utf-8"))["patch"]
        assert (patch[0]["reason"], patch[0]["found"], patch[0]["source"]) == (
            long_reason, "teams often adopted it", "https://a.com"), patch
        assert long_reason in out and "teams often adopted it" in out, out
        print("[8] the patch carries and prints reason, found passage and source")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_all_verdicts_present_writes_verdicts_and_patch()
    test_invalid_verdicts_return_one()
    test_claim_in_two_batches_returns_one()
    test_verdict_file_not_list_returns_two()
    test_verdict_file_malformed_json_error_names_file()
    test_verdict_entry_not_object_returns_one()
    test_no_verdict_line_names_batch_file()
    test_patch_entries_carry_reason_found_source()
    print("OK")
