#!/usr/bin/env python3
"""select_verification_targets.py - pick and batch the verification targets deterministically.

Used in research-team Step 3. It removes the path where the orchestrator reads the evidence
ledger by eye, picks targets out of it and copies claim text into a brief. This script picks
up every signal a machine can decide, and the orchestrator adds only what a machine cannot -
the claims that swing the conclusion or the recommendation.

Targets are narrowed by how much they bear on the conclusion. Key figures and conflicts bear
on it directly, so every one of them is a target; single-source and estimate claims are
targets only where they belong to a decision KQ, that is a key question whose relevance is
anything other than background. On top of that, the number of batches is capped per mode,
and the excess is cut starting from the lowest-priority batch. The evidence IDs cut this way
appear under dropped in the output, and their count and the reason belong in the gaps of the
evidence ledger. The cap is per investigation, not per wave: the second wave gets only what
the first wave left of it.

Selection runs in two waves. Wave 1 uses the signals the evidence ledger settles on its own:
key figures, single sources, conflicts, key figures resting on grade C alone, self-reported
key figures, and claims whose claim_type is estimate. Wave 2 takes citation_check.json
through `--citation` and picks up the evidence whose citation check came back CRITICAL or
WARN and that wave 1 did not already cover. Splitting the waves this way means wave 1 does
not wait for a full set of citation results, which only arrives midway through the
verification phase.

Each batch gets its own claim payload, targets_{BATCH_ID}.json, holding that batch's claims
and their matching citation-check records and nothing else, so no verifier has to read the
whole of citation_check.json.

`--citation` feeds the payload whether or not it drives the selection. Passing the output of
a narrowed `citation_verifier.py --only` in wave 1 puts those results into the payload too.

Examples:
    python select_verification_targets.py evidence_log.json --run-dir research/20260726-topic
    python select_verification_targets.py evidence_log.json --run-dir DIR \\
        --citation DIR/citation_check_targets.json --json
    python select_verification_targets.py evidence_log.json --run-dir DIR \\
        --wave 2 --citation DIR/citation_check.json --json

Exit codes: 0 = success, including a run with no targets / 2 = usage or I/O error
"""

import argparse
import glob
import json
import os
import sys

BATCH_SIZE = 3          # claims per verifier (the sizing rule in agent_roles.md)
MAX_BATCHES_PER_LAUNCH = 16   # cap on how many agents one message may launch
OPUS_SIGNALS = ("key_figure", "conflicting")   # what swings the conclusion is verified by opus

# Cap on the number of batches, per investigation. Once it is reached, the lowest-priority
# batches are cut.
MAX_BATCHES = {"DEEP": 10, "STANDARD": 6, "LIGHT": 2}

# Signals that only target evidence belonging to a decision KQ. Key figures and conflicts
# bear on the conclusion directly, so every one of them is a target.
DECISION_SCOPED_SIGNALS = ("single_source", "estimate")

SIGNAL_LABELS = {
    "key_figure": "key figure",
    "single_source": "single source",
    "conflicting": "sources conflict",
    "grade_c_key": "key figure resting on grade C alone",
    "self_reported_key": "self-reported key figure",
    "estimate": "estimate or forecast",
    "citation_flagged": "citation check CRITICAL / WARN",
}


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def decision_kqs(log):
    """Return the set of decision-KQ IDs. A KQ with no relevance stated counts as one."""
    ids = set()
    for k in log.get("key_questions", []):
        if isinstance(k, dict) and k.get("id"):
            if k.get("relevance") != "background":
                ids.add(k["id"])
    return ids


def ledger_signals(log):
    """Return the signals the evidence ledger settles on its own, as {evidence_id: [signal, ...]}.

    Single-source and estimate signals apply only to evidence belonging to a decision KQ:
    verifying a claim that does not swing the conclusion spends agents without changing the
    verdict. Key figures and conflicts apply to every evidence unit.
    """
    evidence = log.get("evidence", [])
    by_id = {e.get("id"): e for e in evidence}
    decision = decision_kqs(log)
    signals = {}

    def in_decision_kq(e):
        return any(kq in decision for kq in (e.get("kq_ids") or []))

    def mark(eid, name):
        signals.setdefault(eid, [])
        if name not in signals[eid]:
            signals[eid].append(name)

    for e in evidence:
        eid = e.get("id")
        src = e.get("source") or {}
        if e.get("is_key_figure"):
            mark(eid, "key_figure")
            grades = {src.get("grade")}
            for cid in e.get("corroborating_ids") or []:
                other = by_id.get(cid)
                if other:
                    grades.add((other.get("source") or {}).get("grade"))
            grades.discard(None)
            if grades and grades <= {"C"}:
                mark(eid, "grade_c_key")
            if e.get("self_reported"):
                mark(eid, "self_reported_key")
        if e.get("corroboration") == "conflicting":
            mark(eid, "conflicting")
        if in_decision_kq(e):
            if e.get("corroboration") == "single_source":
                mark(eid, "single_source")
            if e.get("claim_type") == "estimate":
                mark(eid, "estimate")
    return signals


def citation_signals(citation, known_ids):
    """Return the signals taken from the citation-check severities, as {evidence_id: [signal]}."""
    signals = {}
    for r in (citation or {}).get("results") or []:
        eid = r.get("id")
        if eid in known_ids and r.get("severity") in ("CRITICAL", "WARN"):
            signals[eid] = ["citation_flagged"]
    return signals


def make_batches(target_ids, signals, run_dir, wave, max_batches=None):
    """Group the targets into batches, opus batches first, BATCH_SIZE each bar the remainder.

    Anything past max_batches is cut. Returns (batches, dropped_evidence_ids). Because the
    opus batches - key figures and conflicts - come first, what gets cut is always the
    lowest-priority work.
    """
    verification_dir = os.path.join(run_dir, "verification")

    def needs_opus(eid):
        return any(s in OPUS_SIGNALS for s in signals.get(eid, []))

    opus_ids = [i for i in target_ids if needs_opus(i)]
    sonnet_ids = [i for i in target_ids if not needs_opus(i)]

    batches = []
    for model, ids in (("opus", opus_ids), ("sonnet", sonnet_ids)):
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start:start + BATCH_SIZE]
            names = []
            for eid in chunk:
                for s in signals.get(eid, []):
                    label = SIGNAL_LABELS.get(s, s)
                    if label not in names:
                        names.append(label)
            batch_id = f"w{wave}b{len(batches) + 1}"
            batches.append({
                "batch_id": batch_id,
                "ids": chunk,
                "model": model,
                "verdicts_path": os.path.join(verification_dir, f"verdicts_{batch_id}.json"),
                "targets_path": os.path.join(verification_dir, f"targets_{batch_id}.json"),
                "launch_group": len(batches) // MAX_BATCHES_PER_LAUNCH,
                "reason": " / ".join(names),
            })
    if max_batches is not None and len(batches) > max_batches:
        dropped = [eid for b in batches[max_batches:] for eid in b["ids"]]
        batches = batches[:max_batches]
    else:
        dropped = []
    return batches, dropped


def build_payload(batch, log, citation):
    """Build the claim payload for one batch."""
    by_id = {e.get("id"): e for e in log.get("evidence", [])}
    checks = {r.get("id"): r for r in (citation or {}).get("results") or []}
    claims = []
    for eid in batch["ids"]:
        e = by_id.get(eid) or {}
        src = e.get("source") or {}
        claims.append({
            "id": eid,
            "claim": e.get("claim", ""),
            "verbatim_quote": e.get("verbatim_quote", ""),
            "source": {"url": src.get("url", ""), "publisher": src.get("publisher", ""),
                       "published": src.get("published", "")},
            "is_key_figure": bool(e.get("is_key_figure")),
            "citation_check": checks.get(eid),
        })
    return {"batch_id": batch["batch_id"], "model": batch["model"],
            "verdicts_path": batch["verdicts_path"], "claims": claims}


def batches_of_other_waves(run_dir, wave):
    """How many batches the other waves have already created; the cap is per investigation.

    Re-running the same wave - wave 1 run again with --citation, say - is not counted.
    Counting it would eat into the cap on every re-run.
    """
    pattern = os.path.join(run_dir, "verification", "targets_w*b*.json")
    return sum(1 for p in glob.glob(pattern)
               if not os.path.basename(p).startswith(f"targets_w{wave}b"))


def select(log, citation, run_dir, wave, max_batches=None):
    known_ids = [e.get("id") for e in log.get("evidence", []) if e.get("id")]
    ledger = ledger_signals(log)
    if wave == 1:
        signals = ledger
        target_ids = [i for i in known_ids if i in signals]
    else:
        signals = citation_signals(citation, set(known_ids))
        # Do not select again what wave 1 already picked up
        target_ids = [i for i in known_ids if i in signals and i not in ledger]
    if max_batches is None:
        max_batches = MAX_BATCHES.get(log.get("mode"), MAX_BATCHES["STANDARD"])
    spent = batches_of_other_waves(run_dir, wave)
    remaining = max(0, max_batches - spent)
    batches, dropped = make_batches(target_ids, signals, run_dir, wave, remaining)
    selected_ids = [eid for b in batches for eid in b["ids"]]
    counts = {}
    for names in signals.values():
        for s in names:
            counts[s] = counts.get(s, 0) + 1
    return {
        "wave": wave,
        "expected_ids": ",".join(selected_ids),
        "target_count": len(selected_ids),
        "launch_groups": max((b["launch_group"] for b in batches), default=-1) + 1,
        "signals": counts,
        "max_batches": max_batches,
        "batches_used_by_other_waves": spent,
        "batches_remaining": remaining,
        "dropped": {
            "ids": dropped,
            "count": len(dropped),
            "reason": (f"cut for exceeding the cap of {max_batches} batches per investigation "
                       f"({spent} already used by other waves); record the count and this "
                       f"reason in the gaps of the evidence ledger") if dropped else "",
        },
        "batches": batches,
    }


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Pick and batch the verification targets deterministically")
    parser.add_argument("log", help="path to evidence_log.json")
    parser.add_argument("--run-dir", required=True, help="the deliverables directory")
    parser.add_argument("--wave", type=int, choices=(1, 2), default=1,
                        help="1 (default) selects from the evidence ledger alone; "
                             "2 selects from the citation-check severities")
    parser.add_argument("--citation", default=None,
                        help="output of citation_verifier.py; it feeds the payload, and is "
                             "required with --wave 2")
    parser.add_argument("--max-batches", type=int, default=None,
                        help=f"cap on the number of batches "
                             f"(default: per the ledger's mode, {MAX_BATCHES})")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
    except OSError as e:
        print(f"error: cannot read the evidence ledger: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: the evidence ledger is not valid JSON: {e}", file=sys.stderr)
        return 2

    if args.wave == 2 and not args.citation:
        print("error: --wave 2 requires --citation", file=sys.stderr)
        return 2

    citation = None
    if args.citation:
        try:
            with open(args.citation, encoding="utf-8") as f:
                citation = json.load(f)
        except OSError as e:
            print(f"error: cannot read the citation-check results: {e}", file=sys.stderr)
            return 2
        except json.JSONDecodeError as e:
            print(f"error: the citation-check results are not valid JSON: {e}", file=sys.stderr)
            return 2

    run_dir = os.path.abspath(args.run_dir)
    summary = select(log, citation, run_dir, wave=args.wave, max_batches=args.max_batches)

    try:
        os.makedirs(os.path.join(run_dir, "verification"), exist_ok=True)
        for batch in summary["batches"]:
            with open(batch["targets_path"], "w", encoding="utf-8") as f:
                json.dump(build_payload(batch, log, citation), f,
                          ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"error: cannot write the payloads: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"wave {summary['wave']}: {summary['target_count']} target(s) / "
              f"{len(summary['batches'])} batch(es) / {summary['launch_groups']} launch(es)")
        if summary["dropped"]["count"]:
            print(f"  {summary['dropped']['count']} evidence unit(s) cut at the cap: "
                  f"{', '.join(summary['dropped']['ids'])} - {summary['dropped']['reason']}")
        for b in summary["batches"]:
            print(f"  {b['batch_id']} [{b['model']}] {', '.join(b['ids'])} - {b['reason']}")
            print(f"      {b['targets_path']}")
        if summary["batches"]:
            print(f"  apply_verdicts.py --expected {summary['expected_ids']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
