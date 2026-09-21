#!/usr/bin/env python3
"""Checks for select_verification_targets.py.

Confirms that every selection signal a machine can decide is picked up, that wave 1 and
wave 2 separate correctly, that a batch holds 5 claims and splits between opus and sonnet,
that going past 16 batches splits the launch, that --must-verify and kq_minimum add their
targets, and that a corroborated key figure and a WARN citation rank out of the way.
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


def run(log_path, run_dir, citation=None, wave=None, max_batches=None, must_verify=None):
    args = [PY, os.path.join(SCRIPTS, "select_verification_targets.py"), log_path,
            "--run-dir", run_dir, "--json"]
    if citation:
        args += ["--citation", citation]
    if wave:
        args += ["--wave", str(wave)]
    if max_batches:
        args += ["--max-batches", str(max_batches)]
    if must_verify:
        args += ["--must-verify", must_verify]
    cp = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return cp.returncode, json.loads(cp.stdout)


def run_ok(log_path, run_dir, **kw):
    rc, res = run(log_path, run_dir, **kw)
    if rc != 0:
        raise AssertionError(f"rc={rc} errors={res.get('errors')}")
    return res


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
            ev(1, is_key_figure=True, corroborating_ids=["E2"]),          # key figure,
                                                                            # corroborated (E2's
                                                                            # cluster differs)
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
        res = run_ok(log_path, run_dir)
        ids = res["expected_ids"].split(",")
        check("every piece of evidence carrying a signal is picked up",
              sorted(ids) == ["E1", "E3", "E4", "E5", "E6", "E7", "E8"], str(ids))
        check("ranked in the cut order: conflicting, then key figures, then single source, "
              "then a corroborated key figure and an estimate last",
              ids == ["E4", "E5", "E7", "E8", "E3", "E1", "E6"], str(ids))
        check("a corroborated key figure ranks below a single-source one",
              ids.index("E3") < ids.index("E1"), str(ids))
        check("evidence carrying no signal is left out", "E2" not in ids and "E9" not in ids,
              str(ids))
        check("a key figure resting on grade C alone counts as a signal",
              res["signals"].get("grade_c_key") == 1, str(res["signals"]))
        check("a self-reported key figure counts as a signal",
              res["signals"].get("self_reported_key") == 1, str(res["signals"]))
        check("a claim marked as an estimate counts as a signal",
              res["signals"].get("estimate") == 1, str(res["signals"]))
        check("a key figure corroborated across independent clusters carries the "
              "key_figure_corroborated signal",
              res["signals"].get("key_figure_corroborated") == 1
              and res["signals"].get("key_figure") == 2, str(res["signals"]))

        print("[how the batches are formed]")
        opus = [b for b in res["batches"] if b["model"] == "opus"]
        sonnet = [b for b in res["batches"] if b["model"] == "sonnet"]
        opus_ids = [i for b in opus for i in b["ids"]]
        sonnet_ids = [i for b in sonnet for i in b["ids"]]
        check("key figures and conflicts go into the opus batches",
              sorted(opus_ids) == ["E4", "E5", "E7", "E8"], str(opus_ids))
        check("a corroborated key figure, a single source and an estimate go into the "
              "sonnet batches", sorted(sonnet_ids) == ["E1", "E3", "E6"], str(sonnet_ids))
        check("a batch holds 5 claims, only the remainder is smaller",
              [len(b["ids"]) for b in res["batches"]] == [4, 3],
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
            {"id": "E1", "severity": "CRITICAL", "quote_match": "not_found"},  # already in wave 1
            {"id": "E2", "severity": "CRITICAL", "quote_match": "not_found"},  # new to wave 2
            {"id": "E9", "severity": "WARN", "quote_match": "unfetchable"},    # WARN, no target
        ]})
        res1b = run_ok(log_path, run_dir, citation=citation)
        ids1b = res1b["expected_ids"].split(",")
        check("a CRITICAL citation record adds a citation_flagged target in wave 1",
              "E2" in ids1b and res1b["signals"].get("citation_flagged") == 2,
              str(res1b["signals"]))
        check("a WARN citation record adds no target in wave 1",
              "E9" not in ids1b, str(ids1b))
        sonnet_batch = next(b for b in res1b["batches"] if "E1" in b["ids"])
        payload1b = json.load(open(sonnet_batch["targets_path"], encoding="utf-8"))
        check("the citation results for the selected claims reach the payload",
              any(c["citation_check"] for c in payload1b["claims"]),
              str([c["citation_check"] for c in payload1b["claims"]]))

        res2 = run_ok(log_path, run_dir, citation=citation, wave=2)
        check("only a CRITICAL result left out of wave 1 is picked up (WARN launches nothing, "
              "and E1 is already covered)", res2["expected_ids"] == "E2", res2["expected_ids"])
        payload2 = json.load(open(res2["batches"][0]["targets_path"], encoding="utf-8"))
        check("only the matching citation-check record travels with the claim",
              payload2["claims"][0]["citation_check"]["severity"] == "CRITICAL"
              and len(payload2["claims"]) == 1, str(payload2["claims"]))
        check("batch IDs from different waves do not collide",
              res2["batches"][0]["batch_id"].startswith("w2"),
              res2["batches"][0]["batch_id"])

        print("[a WARN citation severity produces no target]")
        warn_only = write(os.path.join(run_dir, "citation_warn_only.json"), {"results": [
            {"id": "E2", "severity": "WARN", "quote_match": "unfetchable"},
        ]})
        res2b = run_ok(log_path, run_dir, citation=warn_only, wave=2)
        check("a WARN-only citation check selects nothing", res2b["target_count"] == 0,
              str(res2b))

        print("[--must-verify]")
        mv_dir = os.path.join(tmp, "must-verify-run")
        os.makedirs(mv_dir)
        mv_log = {"key_questions": [{"id": "KQ1", "text": "a key question"}],
                  "evidence": [ev(1), ev(2)]}
        mv_path = write(os.path.join(mv_dir, "evidence_log.json"), mv_log)
        rc_mv, res_mv = run(mv_path, mv_dir, must_verify="E1,E9")
        check("a must-verify claim is ranked first and forced into an opus batch",
              res_mv["batches"] and res_mv["batches"][0]["model"] == "opus"
              and "E1" in res_mv["batches"][0]["ids"], str(res_mv["batches"]))
        check("an unknown --must-verify id is reported under errors",
              any("E9" in e for e in res_mv["errors"]), str(res_mv["errors"]))
        check("an unknown --must-verify id makes the exit code 1", rc_mv == 1, f"rc={rc_mv}")

        print("[kq_minimum: a decision KQ with no signal still gets a target]")
        km_dir = os.path.join(tmp, "kq-min-run")
        os.makedirs(km_dir)
        km_log = {"key_questions": [{"id": "KQ1", "text": "q1"}, {"id": "KQ2", "text": "q2"}],
                  "evidence": [
                      ev(1, is_key_figure=True),                # KQ1 already has a target
                      ev(2, kq_ids=["KQ2"]),                     # KQ2's only evidence, no signal
                  ]}
        km_path = write(os.path.join(km_dir, "evidence_log.json"), km_log)
        res_km = run_ok(km_path, km_dir)
        check("the uncovered decision KQ's evidence is added with kq_minimum",
              "E2" in res_km["expected_ids"].split(",")
              and res_km["signals"].get("kq_minimum") == 1, str(res_km))

        print("[dropped and kq_minimum stay disjoint]")
        km2_dir = os.path.join(tmp, "kq-min-dropped-run")
        os.makedirs(km2_dir)
        # KQ4's only evidence is low priority (single source); with max_batches=1 it is
        # the one the cap cuts, so it must come back through kq_minimum and leave the
        # dropped list.
        km2_log = {"key_questions": [{"id": "KQ1", "text": "q1"}, {"id": "KQ4", "text": "q4"}],
                  "evidence": [
                      ev(1, is_key_figure=True),                          # KQ1, opus, kept
                      ev(2, kq_ids=["KQ4"], corroboration="single_source"),  # KQ4, cut by the cap
                  ]}
        km2_path = write(os.path.join(km2_dir, "evidence_log.json"), km2_log)
        res_km2 = run_ok(km2_path, km2_dir, max_batches=1)
        check("the cap-cut id KQ4 needed is reinstated by kq_minimum",
              "E2" in res_km2["expected_ids"].split(","), str(res_km2))
        check("a reinstated id leaves dropped, keeping the two sets disjoint",
              "E2" not in res_km2["dropped"]["ids"] and res_km2["dropped"]["count"] == 0,
              str(res_km2["dropped"]))

        print("[the cap on the number of batches]")
        big_dir = os.path.join(tmp, "big-run")
        os.makedirs(big_dir)
        big = {"mode": "DEEP", "key_questions": [{"id": "KQ1", "text": "a key question"}],
               "evidence": [ev(i, claim_type="estimate") for i in range(1, 101)]
                           + [ev(i, is_key_figure=True) for i in range(101, 110)]}
        big_path = write(os.path.join(big_dir, "big.json"), big)
        res3 = run_ok(big_path, big_dir)
        check("DEEP stops at 5 batches per piece of research", len(res3["batches"]) == 5,
              str(len(res3["batches"])))
        # 109 evidence units; the 5 surviving batches hold 5 + 4 (opus, 9 key figures) and
        # 5 + 5 + 5 (sonnet, the first 15 of 100 estimates) = 24.
        check("the evidence cut by the cap is reported under dropped",
              res3["dropped"]["count"] == 109 - 24 and res3["dropped"]["reason"],
              str(res3["dropped"]["count"]))
        check("the batches that survive are filled from the key figures (opus) first",
              all(b["model"] == "opus" for b in res3["batches"][:2]),
              str([b["model"] for b in res3["batches"][:2]]))
        check("one launch group, because the batches stay under the cap",
              res3["launch_groups"] == 1, str(res3["launch_groups"]))
        res4 = run_ok(big_path, big_dir, max_batches=20)
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
