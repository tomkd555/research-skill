#!/usr/bin/env python3
"""screen_claims.py - compare every report sentence with its cited quotes (research-team 2.0).

Used in research-team Step 5.1 (--write, before the screeners start) and Step 5.2 (--apply,
after every screener has written screen/labels_{k}.json). Standard library only, no network.

Examples:
    python screen_claims.py --run-dir research/20261024-topic --write
    python screen_claims.py --run-dir research/20261024-topic --apply

--write: every sentence of report.md under "## Answer", "## Findings" and "## Disagreements
and limits" becomes {"sid", "section", "sentence", "evidence": [{"id", "claim", "quote",
"context"}]} in screen/batch_{k}.json, 40 sentences per file. "context" is the quote with up
to 400 characters of the cached page around it, the abstract of a paper item, or the quote
alone. Earlier screen/ files and screen.json are removed first.
--apply: reads screen/batch_*.json and screen/labels_*.json ({"sid", "label", "reason"}, label
one of ok, drift, uncited_fact, own, own_cited) and writes screen.json {"counts", "priority",
"fix"}. "priority" holds the drift, uncited_fact and own_cited sentences, which
select_claims.py puts first; "fix" holds the uncited_fact and own_cited ones with their
reasons, printed one per line.

Exit codes: 0 = written / 1 = a sid without a label, an unknown sid, a repeated sid or an
unknown label (nothing written) / 2 = usage or I/O error
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check as ck  # noqa: E402
import report_check as rc  # noqa: E402
import select_claims as sc  # noqa: E402

SECTIONS = ("## Answer", "## Findings", "## Disagreements and limits")
LABELS = ("ok", "drift", "uncited_fact", "own", "own_cited")
PRIORITY = ("drift", "uncited_fact", "own_cited")
FIX = ("uncited_fact", "own_cited")
BATCH_SIZE = 40


def evidence_of(run_dir, sentence, evidence):
    out = []
    for i in dict.fromkeys(rc.marker_ids(sentence)):
        e = evidence.get(i)
        if e is None:
            continue
        if e.get("paper"):
            context = sc.paper_abstract(run_dir, e) or e["quote"]
        else:
            text = ck.page_text(run_dir, e["url"])
            context = ck.context_of(text, e["quote"]) if text else e["quote"]
        out.append({"id": i, "claim": e.get("claim", ""), "quote": e["quote"], "context": context})
    return out


def write(run_dir):
    with open(os.path.join(run_dir, "report.md"), encoding="utf-8") as f:
        report = f.read()
    evidence = {e["id"]: e for e in rc.read_jsonl(os.path.join(run_dir, "evidence.jsonl"))}
    picked = [(sec, s) for sec, s in rc.report_sentences(report) if sec in SECTIONS]
    rows = [{"sid": f"S{n}", "section": sec[3:], "sentence": s,
             "evidence": evidence_of(run_dir, s, evidence)} for n, (sec, s) in enumerate(picked, 1)]
    screen_dir = os.path.join(run_dir, "screen")
    os.makedirs(screen_dir, exist_ok=True)
    # a rerun must not leave the batches, labels or result of an earlier report behind
    for old in glob.glob(os.path.join(screen_dir, "*.json")) + [os.path.join(run_dir, "screen.json")]:
        if os.path.exists(old):
            os.remove(old)
    paths = []
    for k in range(0, len(rows), BATCH_SIZE):
        path = os.path.join(screen_dir, f"batch_{k // BATCH_SIZE + 1}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows[k:k + BATCH_SIZE], f, ensure_ascii=False, indent=2)
        paths.append(path)
    print("\n".join(paths))
    print(f"{len(rows)} sentences in {len(paths)} batches")
    return 0


def load_all(pattern):
    rows = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected a JSON list")
        rows += data
    return rows


def apply(run_dir):
    screen_dir = os.path.join(run_dir, "screen")
    batches = load_all(os.path.join(screen_dir, "batch_*.json"))
    labels = load_all(os.path.join(screen_dir, "labels_*.json"))
    by_sid = {s["sid"]: s for s in batches}
    errors, seen = [], {}
    for n, lab in enumerate(labels, 1):
        sid = lab.get("sid") if isinstance(lab, dict) else None
        if not isinstance(lab, dict):
            errors.append(f"label entry {n} is not a JSON object")
        elif sid not in by_sid:
            errors.append(f"label for unknown sid {sid!r}")
        elif sid in seen:
            errors.append(f"{sid}: more than one label")
        elif lab.get("label") not in LABELS:
            errors.append(f"{sid}: unknown label {lab.get('label')!r}")
        else:
            seen[sid] = lab
    named = {lab.get("sid") for lab in labels if isinstance(lab, dict)}
    errors += [f"{sid}: no label" for sid in by_sid if sid not in named]
    if errors:
        print("\n".join(errors))
        return 1

    counts = collections.Counter(seen[sid]["label"] for sid in by_sid)
    priority = [by_sid[sid]["sentence"] for sid in by_sid if seen[sid]["label"] in PRIORITY]
    fix = [{"sid": sid, "label": seen[sid]["label"], "sentence": by_sid[sid]["sentence"],
            "reason": seen[sid].get("reason", "")} for sid in by_sid if seen[sid]["label"] in FIX]
    with open(os.path.join(run_dir, "screen.json"), "w", encoding="utf-8") as f:
        json.dump({"counts": {k: counts[k] for k in LABELS}, "priority": priority, "fix": fix},
                  f, ensure_ascii=False, indent=2)
    print(f"screened {len(by_sid)} sentences: {counts['drift']} drift, {counts['uncited_fact']} "
          f"uncited facts, {counts['own_cited']} readings under a source marker")
    for x in fix:
        print(f"{x['sid']} {x['label']}: {x['reason']} | {x['sentence']}")
    return 0


def main():
    rc._configure_stdout()
    ap = argparse.ArgumentParser(description="Compare every report sentence with its cited quotes.")
    ap.add_argument("--run-dir", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write screen/batch_{k}.json")
    mode.add_argument("--apply", action="store_true", help="merge the labels into screen.json")
    args = ap.parse_args()
    try:
        return write(args.run_dir) if args.write else apply(args.run_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
