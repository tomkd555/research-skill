#!/usr/bin/env python3
"""Checks for select_verification_targets.py.

Confirms that every selection signal a machine can decide is picked up, that wave 1 and
wave 2 separate correctly, that a batch holds 3 claims and splits between opus and sonnet,
and that going past 16 batches splits the launch into groups.
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


def run(log_path, run_dir, citation=None, wave=None, max_batches=None):
    args = [PY, os.path.join(SCRIPTS, "select_verification_targets.py"), log_path,
            "--run-dir", run_dir, "--json"]
    if citation:
        args += ["--citation", citation]
    if wave:
        args += ["--wave", str(wave)]
    if max_batches:
        args += ["--max-batches", str(max_batches)]
    cp = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if cp.returncode != 0:
        raise AssertionError(f"rc={cp.returncode} err={cp.stderr[:300]}")
    return json.loads(cp.stdout)


def ev(n, **over):
    e = {
        "id": f"E{n}", "kq_ids": ["KQ1"], "claim": f"a proposition (E{n})",
        "claim_type": "fact", "verbatim_quote": f"quote {n}",
        "source": {"publisher": "Publisher", "title": f"t{n}", "url": f"https://example.com/{n}",
                   "published": "2025", "grade": "A", "origin_cluster": f"c{n}"},
        "accessed": "2026-07-25", "is_key_figure": False, "corroboration": "corroborated",
        "corroborating_ids": [],
    }
    src = over.pop("source", {})
    e["source"].update(src)
    e.update(over)
    return e


def write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="rt-select-")
    run_dir = os.path.join(tmp, "run")
    os.makedirs(run_dir)
    try:
        log = {"key_questions": [{"id": "KQ1", "text": "a key question"}], "evidence": [
            ev(1, is_key_figure=True, corroborating_ids=["E2"]),          # key figure
            ev(2),                                                        # no signal
            ev(3, corroboration="single_source"),                         # single source
            ev(4, corroboration="conflicting", corroborating_ids=["E5"]),  # conflicting
            ev(5, corroboration="conflicting", corroborating_ids=["E4"]),
            ev(6, claim_type="estimate"),                                 # estimate
            ev(7, is_key_figure=True, source={"grade": "C"}),             # key figure on grade C only
            ev(8, is_key_figure=True, self_reported=True),                # self-reported key figure
            ev(9),                                                        # no signal (wave 2 takes it)
        ]}
        log_path = write(os.path.join(run_dir, "evidence_log.json"), log)

        print("[wave 1: signals the evidence log alone decides]")
        res = run(log_path, run_dir)
        ids = res["expected_ids"].split(",")
        check("every piece of evidence carrying a signal is picked up",
              sorted(ids) == ["E1", "E3", "E4", "E5", "E6", "E7", "E8"], str(ids))
        check("ordered by what survives the cap, key figures and conflicts first",
              ids[:5] == ["E1", "E4", "E5", "E7", "E8"], str(ids))
        check("evidence carrying no signal is left out", "E2" not in ids and "E9" not in ids,
              str(ids))
        check("a key figure resting on grade C alone counts as a signal",
              res["signals"].get("grade_c_key") == 1, str(res["signals"]))
        check("a self-reported key figure counts as a signal",
              res["signals"].get("self_reported_key") == 1, str(res["signals"]))
        check("a claim marked as an estimate counts as a signal",
              res["signals"].get("estimate") == 1, str(res["signals"]))

        print("[how the batches are formed]")
        opus = [b for b in res["batches"] if b["model"] == "opus"]
        sonnet = [b for b in res["batches"] if b["model"] == "sonnet"]
        opus_ids = [i for b in opus for i in b["ids"]]
        sonnet_ids = [i for b in sonnet for i in b["ids"]]
        check("key figures and conflicts go into the opus batches",
              sorted(opus_ids) == ["E1", "E4", "E5", "E7", "E8"], str(opus_ids))
        check("everything else goes into the sonnet batches", sorted(sonnet_ids) == ["E3", "E6"],
              str(sonnet_ids))
        check("a batch holds 3 claims, only the remainder is smaller",
              [len(b["ids"]) for b in res["batches"]] == [3, 2, 2],
              str([len(b["ids"]) for b in res["batches"]]))
        check("the opus batches come first", res["batches"][0]["model"] == "opus",
              res["batches"][0]["model"])
        check("each batch gets its own verdicts output path",
              all(b["verdicts_path"].endswith(f"verdicts_{b['batch_id']}.json")
                  for b in res["batches"]))

        print("[the payload of a batch]")
        first = res["batches"][0]
        payload = json.load(open(first["targets_path"], encoding="utf-8"))
        check("only the projection of a claim is written out",
              [c["id"] for c in payload["claims"]] == first["ids"]
              and set(payload["claims"][0]) == {"id", "claim", "verbatim_quote", "source",
                                                "is_key_figure", "citation_check"},
              str(payload["claims"][0].keys()))
        check("wave 1 carries no citation-check record",
              all(c["citation_check"] is None for c in payload["claims"]))

        print("[wave 2: picked up by the severity of the citation check]")
        citation = write(os.path.join(run_dir, "citation_check.json"), {"results": [
            {"id": "E1", "severity": "CRITICAL", "quote_match": "not_found"},
            {"id": "E2", "severity": "PASS", "quote_match": "found"},
            {"id": "E9", "severity": "WARN", "quote_match": "unfetchable"},
        ]})
        res1b = run(log_path, run_dir, citation=citation)
        payload1b = json.load(open(res1b["batches"][0]["targets_path"], encoding="utf-8"))
        check("--citation does not change the wave 1 selection",
              res1b["expected_ids"] == res["expected_ids"], res1b["expected_ids"])
        check("the citation results for the selected claims reach the payload",
              any(c["citation_check"] for c in payload1b["claims"]),
              str([c["citation_check"] for c in payload1b["claims"]]))

        res2 = run(log_path, run_dir, citation=citation, wave=2)
        check("only evidence left out of wave 1 is picked up", res2["expected_ids"] == "E9",
              res2["expected_ids"])
        payload2 = json.load(open(res2["batches"][0]["targets_path"], encoding="utf-8"))
        check("only the matching citation-check record travels with the claim",
              payload2["claims"][0]["citation_check"]["severity"] == "WARN"
              and len(payload2["claims"]) == 1, str(payload2["claims"]))
        check("batch IDs from different waves do not collide",
              res2["batches"][0]["batch_id"].startswith("w2"),
              res2["batches"][0]["batch_id"])

        print("[the cap on the number of batches]")
        big_dir = os.path.join(tmp, "big-run")
        os.makedirs(big_dir)
        big = {"mode": "DEEP", "key_questions": [{"id": "KQ1", "text": "a key question"}],
               "evidence": [ev(i, claim_type="estimate") for i in range(1, 61)]
                           + [ev(i, is_key_figure=True) for i in range(61, 70)]}
        big_path = write(os.path.join(big_dir, "big.json"), big)
        res3 = run(big_path, big_dir)
        check("DEEP stops at 10 batches per piece of research", len(res3["batches"]) == 10,
              str(len(res3["batches"])))
        check("the evidence cut by the cap is reported under dropped",
              res3["dropped"]["count"] == 69 - 10 * 3 and res3["dropped"]["reason"],
              str(res3["dropped"]["count"]))
        check("the batches that survive are filled from the key figures (opus) first",
              all(b["model"] == "opus" for b in res3["batches"][:3]),
              str([b["model"] for b in res3["batches"][:4]]))
        check("one launch group, because the batches stay under the cap",
              res3["launch_groups"] == 1, str(res3["launch_groups"]))
        res4 = run(big_path, big_dir, max_batches=20)
        check("raising --max-batches past 16 batches splits the launch",
              res4["launch_groups"] == 2 and len(res4["batches"]) == 20,
              f"{res4['launch_groups']} / {len(res4['batches'])}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
