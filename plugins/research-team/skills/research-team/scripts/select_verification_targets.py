#!/usr/bin/env python3
"""select_verification_targets.py - pick and batch the verification targets deterministically.

Used in research-team Step 3. It removes the path where the orchestrator reads the evidence
ledger by eye, picks targets out of it and copies claim text into a brief. This script picks
up every signal a machine can decide, and the orchestrator adds only what a machine cannot -
the claims that swing the conclusion or the recommendation.

Targets are narrowed by how much they bear on the conclusion, in this cut order: a claim the
lead names with `--must-verify` ranks first and is forced into an opus batch; conflicting
sources; a citation check that came back CRITICAL; a key figure not corroborated across two
or more independent source clusters; a single-source claim belonging to a decision KQ. A key
figure that is corroborated across clusters, and any claim whose claim_type is estimate, rank
last — behind a single source — because independence already backs the figure and an estimate
carries no fact to get wrong. On top of that, the number of batches is capped per mode, and
the excess is cut starting from the lowest-priority batch. The evidence IDs cut this way
appear under dropped in the output, and their count and the reason belong in the gaps of the
evidence ledger. The cap counts across the whole investigation: the second wave gets only
what the first wave left of it. Once the cap has cut what it will, every decision KQ (every KQ, in
a mode where none is tagged) that still has no target gets its single highest-ranked evidence
unit added anyway, signalled kq_minimum, so the confidence ceiling cannot cap it at "likely"
only because nobody was sent to check it.

Wave 1 uses the signals the evidence ledger settles on its own — key figures, single
sources, conflicts, key figures resting on grade C alone, self-reported key figures, claims
whose claim_type is estimate — and, when `--citation` names a finished citation_check.json,
folds in every evidence unit whose citation check came back CRITICAL, ranked by the same
SIGNAL_RANK as everything else. This is the normal shape now that S3 finishes
citation_verifier.py before S4 starts, so one call covers both. Wave 2 exists for a gap
resubmission: called later, with a fresher citation_check.json, it picks up whatever
CRITICAL result wave 1 left uncovered — a WARN (an unreachable page, a transient network
error) launches no agent either way; `citation_verifier.py --retry-warn` re-requests it
instead. `--must-verify` is honoured in whichever wave names it.

Each batch gets its own claim payload, targets_{BATCH_ID}.json, holding that batch's claims
and their matching citation-check records and nothing else, so no verifier has to read the
whole of citation_check.json.

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

BATCH_SIZE = 5          # claims per verifier (the sizing rule in pipeline.md)
MAX_BATCHES_PER_LAUNCH = 16   # cap on how many agents one message may launch
# What swings the conclusion is verified by opus. A must-verify claim is forced here too.
OPUS_SIGNALS = ("key_figure", "conflicting", "conclusion_driver")

# Cap on the number of batches, per investigation. Once it is reached, the lowest-priority
# batches are cut.
MAX_BATCHES = {"DEEP": 5, "STANDARD": 3, "LIGHT": 1}

# Signals that only target evidence belonging to a decision KQ. Key figures and conflicts
# bear on the conclusion directly, so every one of them is a target.
DECISION_SCOPED_SIGNALS = ("single_source", "estimate")

SIGNAL_LABELS = {
    "conclusion_driver": "named by the lead as carrying the conclusion",
    "key_figure": "key figure",
    "single_source": "single source",
    "conflicting": "sources conflict",
    "grade_c_key": "key figure resting on grade C alone",
    "self_reported_key": "self-reported key figure",
    "key_figure_corroborated": "key figure corroborated across independent sources",
    "estimate": "estimate or forecast",
    "citation_flagged": "citation check CRITICAL",
    "kq_minimum": "no other target reached this decision KQ",
}

# The cut order: the lower the rank, the later a signal is cut once a mode's batch cap is
# reached. A corroborated key figure and an estimate rank last, behind a single source,
# because a second independent cluster already backs the figure and an estimate carries no
# fact to get wrong. kq_minimum is not ranked here — it is added after the cap has already
# cut what it will.
SIGNAL_RANK = {
    "conclusion_driver": 0,
    "conflicting": 1,
    "citation_flagged": 2,
    "key_figure": 3,
    "single_source": 4,
    "key_figure_corroborated": 5,
    "estimate": 5,
}
UNRANKED_SIGNAL = 6


def signal_rank(eid, signals):
    """The best (lowest) cut-order rank among one evidence unit's signals."""
    names = signals.get(eid, [])
    return min((SIGNAL_RANK.get(s, UNRANKED_SIGNAL) for s in names), default=UNRANKED_SIGNAL)


def merge_signals(*signal_dicts):
    """Combine several {evidence_id: [signal, …]} maps, keeping each signal name once."""
    merged = {}
    for d in signal_dicts:
        for eid, names in d.items():
            lst = merged.setdefault(eid, [])
            for name in names:
                if name not in lst:
                    lst.append(name)
    return merged


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

    A key figure carries the key_figure signal only where it is not corroborated across two
    or more independent origin_cluster values (its own plus its corroborating_ids'); one that
    is corroborated that way carries key_figure_corroborated instead, ranked at the bottom of
    the cut order alongside estimate.
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
            clusters = {src.get("origin_cluster")}
            grades = {src.get("grade")}
            for cid in e.get("corroborating_ids") or []:
                other = by_id.get(cid)
                if other:
                    other_src = other.get("source") or {}
                    clusters.add(other_src.get("origin_cluster"))
                    grades.add(other_src.get("grade"))
            clusters.discard(None)
            mark(eid, "key_figure_corroborated" if len(clusters) >= 2 else "key_figure")
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
    """Return the signals taken from the citation-check severities, as {evidence_id: [signal]}.

    Only CRITICAL is targeted (quote_match: not_found, DOI/arXiv not_found). A WARN — an
    unreachable page or a transient network error — launches no agent; citation_verifier.py
    --retry-warn re-requests it instead.
    """
    signals = {}
    for r in (citation or {}).get("results") or []:
        eid = r.get("id")
        if eid in known_ids and r.get("severity") == "CRITICAL":
            signals[eid] = ["citation_flagged"]
    return signals


def must_verify_signals(spec, known_ids):
    """--must-verify: the lead's conclusion-carrying evidence IDs.

    Returns ({evidence_id: ["conclusion_driver"]}, errors); an ID absent from the ledger goes
    into errors, and selection still runs for the rest of the run.
    """
    if not spec:
        return {}, []
    known = set(known_ids)
    signals = {}
    errors = []
    for eid in (part.strip() for part in spec.split(",")):
        if not eid:
            continue
        if eid in known:
            signals[eid] = ["conclusion_driver"]
        else:
            errors.append(f"--must-verify names an evidence id absent from the ledger: {eid}")
    return signals, errors


GRADE_RANK = {"A": 0, "B": 1, "C": 2}


def best_evidence_for_kq(kq_id, evidence):
    """The single highest-ranked evidence unit belonging to a KQ, for the kq_minimum rule.

    Highest-ranked: a key figure first, then by source grade, then ledger order.
    """
    candidates = [e for e in evidence if kq_id in (e.get("kq_ids") or [])]
    if not candidates:
        return None

    def rank(e):
        grade = (e.get("source") or {}).get("grade")
        return (0 if e.get("is_key_figure") else 1, GRADE_RANK.get(grade, 9))

    return min(candidates, key=rank).get("id")


def make_batches(target_ids, signals, run_dir, wave, max_batches=None, start=0):
    """Group the targets into batches, opus batches first, BATCH_SIZE each bar the remainder.

    target_ids is expected pre-sorted by signal_rank, so within each model the lowest-priority
    work sits last. Anything past max_batches is cut. Returns (batches, dropped_evidence_ids).
    `start` offsets the batch numbering and launch grouping past batches already made for this
    wave (the kq_minimum pass runs a second, uncapped call).
    """
    verification_dir = os.path.join(run_dir, "verification")

    def needs_opus(eid):
        return any(s in OPUS_SIGNALS for s in signals.get(eid, []))

    opus_ids = [i for i in target_ids if needs_opus(i)]
    sonnet_ids = [i for i in target_ids if not needs_opus(i)]

    batches = []
    for model, ids in (("opus", opus_ids), ("sonnet", sonnet_ids)):
        for i in range(0, len(ids), BATCH_SIZE):
            chunk = ids[i:i + BATCH_SIZE]
            names = []
            for eid in chunk:
                for s in signals.get(eid, []):
                    label = SIGNAL_LABELS.get(s, s)
                    if label not in names:
                        names.append(label)
            position = start + len(batches)
            batch_id = f"w{wave}b{position + 1}"
            batches.append({
                "batch_id": batch_id,
                "ids": chunk,
                "model": model,
                "verdicts_path": os.path.join(verification_dir, f"verdicts_{batch_id}.json"),
                "targets_path": os.path.join(verification_dir, f"targets_{batch_id}.json"),
                "launch_group": position // MAX_BATCHES_PER_LAUNCH,
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


def select(log, citation, run_dir, wave, max_batches=None, must_verify=None):
    evidence = log.get("evidence", [])
    by_id = {e.get("id"): e for e in evidence}
    known_ids = [e.get("id") for e in evidence if e.get("id")]
    ledger = ledger_signals(log)
    must, errors = must_verify_signals(must_verify, known_ids)
    cite = citation_signals(citation, set(known_ids)) if citation else {}
    if wave == 1:
        # A citation check finished in time for this call feeds the same selection the
        # ledger signals do, ranked by the same SIGNAL_RANK.
        signals = merge_signals(ledger, cite, must)
        target_ids = [i for i in known_ids if i in signals]
    else:
        signals = merge_signals(cite, must)
        # Do not select again what wave 1 already picked up, unless --must-verify names it.
        target_ids = [i for i in known_ids
                      if i in signals and (i not in ledger or i in must)]

    index = {eid: i for i, eid in enumerate(known_ids)}
    target_ids.sort(key=lambda eid: (signal_rank(eid, signals), index.get(eid, 0)))

    if max_batches is None:
        max_batches = MAX_BATCHES.get(log.get("mode"), MAX_BATCHES["STANDARD"])
    spent = batches_of_other_waves(run_dir, wave)
    remaining = max(0, max_batches - spent)
    batches, dropped = make_batches(target_ids, signals, run_dir, wave, remaining)
    selected_ids = [eid for b in batches for eid in b["ids"]]

    # kq_minimum: once the cap has cut what it will, every decision KQ still without a
    # target gets its single highest-ranked evidence unit added anyway. Wave 1 alone runs
    # this: wave 2 sees only the citation-driven follow-up, so it cannot tell an uncovered
    # KQ apart from one wave 1 already sent a verifier to.
    kq_min_ids = []
    if wave == 1:
        covered = set()
        for eid in selected_ids:
            covered.update((by_id.get(eid) or {}).get("kq_ids") or [])
        for kq in sorted(decision_kqs(log)):
            if kq in covered:
                continue
            best = best_evidence_for_kq(kq, evidence)
            if best is None or best in selected_ids:
                continue
            signals.setdefault(best, [])
            if "kq_minimum" not in signals[best]:
                signals[best].append("kq_minimum")
            kq_min_ids.append(best)
    if kq_min_ids:
        # An id the cap cut and kq_minimum then reinstates is verified, so it leaves
        # dropped: the two lists stay disjoint with expected_ids.
        dropped = [eid for eid in dropped if eid not in kq_min_ids]
        extra, _ = make_batches(kq_min_ids, signals, run_dir, wave, max_batches=None,
                                 start=len(batches))
        batches = batches + extra
        selected_ids = selected_ids + [eid for b in extra for eid in b["ids"]]

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
        "errors": errors,
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
                        help="output of citation_verifier.py; it feeds the payload and, in "
                             "wave 1, a CRITICAL severity also becomes a target; required "
                             "with --wave 2")
    parser.add_argument("--max-batches", type=int, default=None,
                        help=f"cap on the number of batches "
                             f"(default: per the ledger's mode, {MAX_BATCHES})")
    parser.add_argument("--must-verify", default=None,
                        help="comma-separated evidence IDs the lead names as carrying the "
                             "conclusion (e.g. E1,E7); each becomes a target ranked first and "
                             "forced into an opus batch, and an unknown ID is reported as an "
                             "error")
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
    summary = select(log, citation, run_dir, wave=args.wave, max_batches=args.max_batches,
                      must_verify=args.must_verify)

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
        for e in summary["errors"]:
            print(f"  error: {e}", file=sys.stderr)
        if summary["dropped"]["count"]:
            print(f"  {summary['dropped']['count']} evidence unit(s) cut at the cap: "
                  f"{', '.join(summary['dropped']['ids'])} - {summary['dropped']['reason']}")
        for b in summary["batches"]:
            print(f"  {b['batch_id']} [{b['model']}] {', '.join(b['ids'])} - {b['reason']}")
            print(f"      {b['targets_path']}")
        if summary["batches"]:
            print(f"  apply_verdicts.py --expected {summary['expected_ids']}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
