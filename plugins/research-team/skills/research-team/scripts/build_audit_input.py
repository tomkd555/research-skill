#!/usr/bin/env python3
"""build_audit_input.py — build what the audit agent is given, deterministically.

Run it in research-team Step 5. The auditor (research-auditor) does not need the whole
ledger. What the R1-R15 rubric asks of the ledger is the disconfirmation records, the
gaps, the list of key figures, and the evidence units that atomic-fact sampling lands on.
No item of the rubric needs the search log.

There are two outputs.
    audit_digest.json  the key questions, the disconfirmation records, the gaps, the key figures
    audit_sample.json  the sampled evidence units in full, with the report lines citing them

The sampling is the even spacing over the evidence IDs that evaluation_protocol.md §4
prescribes, over the evidence the report body cites (a reference from the source list or
the search log does not count).

Examples:
    python build_audit_input.py evidence_log.json --report report.md --run-dir DIR --mode DEEP
    python build_audit_input.py evidence_log.json --report report.md --run-dir DIR \\
        --mode STANDARD --json

Exit codes: 0 = fine / 1 = fewer samples than the rubric asks for / 2 = usage or I/O error
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels
from report_auditor import (EVIDENCE_MARKER_RE, _configure_stdout, classify_lines,
                            section_matches)

SAMPLE_N = {"DEEP": 10, "STANDARD": 5, "LIGHT": 0}
# A reference from the source list or the search log is not a body citation — the same
# rule report_auditor.py applies.
EXEMPT_SECTIONS = labels.section_keywords("SEARCHLOG") + labels.section_keywords("SOURCES")


def body_citations(report_text):
    """The evidence IDs the report body cites, and the lines. {id: [{line, text}]}"""
    cites = {}
    for i, line, section, in_code in classify_lines(report_text):
        if in_code or section_matches(section, EXEMPT_SECTIONS):
            continue
        for m in EVIDENCE_MARKER_RE.finditer(line):
            cites.setdefault(f"E{m.group(1)}", []).append(
                {"line": i, "text": line.strip()})
    return cites


def evenly_spaced(items, n):
    """Even spacing over the evidence IDs. Below n items, everything comes back."""
    if n <= 0 or len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def build_digest(log):
    key_figures = []
    for e in log.get("evidence", []):
        if not e.get("is_key_figure"):
            continue
        src = e.get("source") or {}
        key_figures.append({
            "id": e.get("id"), "claim": e.get("claim"),
            "corroboration": e.get("corroboration"),
            "corroborating_ids": e.get("corroborating_ids") or [],
            "self_reported": bool(e.get("self_reported")),
            "source": {"publisher": src.get("publisher"), "url": src.get("url"),
                       "published": src.get("published"), "grade": src.get("grade"),
                       "origin_cluster": src.get("origin_cluster")},
            "verification": e.get("verification") or {},
        })
    return {
        "topic": log.get("topic"), "as_of": log.get("as_of"), "mode": log.get("mode"),
        "key_questions": log.get("key_questions", []),
        "disconfirmation": log.get("disconfirmation", []),
        "gaps": log.get("gaps", []),
        "key_figures": key_figures,
        "counts": {
            "evidence": len(log.get("evidence", [])),
            "search_log": len(log.get("search_log", [])),
            "key_figures": len(key_figures),
        },
    }


def build_sample(log, report_text, sample_n):
    by_id = {e.get("id"): e for e in log.get("evidence", [])}
    cites = body_citations(report_text)
    cited_ids = sorted((i for i in cites if i in by_id),
                       key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    picked = evenly_spaced(cited_ids, sample_n)
    return {
        "mode": log.get("mode"), "requested": sample_n, "picked": len(picked),
        "cited_total": len(cited_ids),
        "method": "evenly spaced over the evidence IDs (evaluation_protocol.md §4-1)",
        "items": [{"id": eid, "evidence": by_id[eid], "report_lines": cites[eid]}
                  for eid in picked],
    }


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Build what the audit agent is given")
    parser.add_argument("log", help="path to evidence_log.json")
    parser.add_argument("--report", required=True, help="path to report.md")
    parser.add_argument("--run-dir", required=True, help="the deliverable directory")
    parser.add_argument("--mode", choices=list(SAMPLE_N), default=None,
                        help="which sets the sample size (otherwise the ledger's own mode)")
    parser.add_argument("--sample-n", type=int, default=None,
                        help="state the sample size directly")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args()

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
        with open(args.report, encoding="utf-8") as f:
            report_text = f.read()
    except OSError as e:
        print(f"error: cannot read the file: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: not valid JSON: {e}", file=sys.stderr)
        return 2

    mode = args.mode or log.get("mode", "STANDARD")
    sample_n = args.sample_n if args.sample_n is not None else SAMPLE_N.get(mode, 5)

    digest = build_digest(log)
    sample = build_sample(log, report_text, sample_n)

    run_dir = os.path.abspath(args.run_dir)
    paths = {"digest": os.path.join(run_dir, "audit_digest.json"),
             "sample": os.path.join(run_dir, "audit_sample.json")}
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(paths["digest"], "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
        with open(paths["sample"], "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"error: cannot write the output: {e}", file=sys.stderr)
        return 2

    short = sample["picked"] < sample_n
    summary = {"mode": mode, "sample_requested": sample_n, "sample_picked": sample["picked"],
               "cited_total": sample["cited_total"],
               "key_figures": digest["counts"]["key_figures"], "outputs": paths}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"digest: {digest['counts']['key_figures']} key figures / "
              f"{len(digest['disconfirmation'])} disconfirmation records / "
              f"{len(digest['gaps'])} gaps")
        print(f"sample: {sample['picked']}/{sample_n}, spaced evenly over the "
              f"{sample['cited_total']} evidence units the body cites")
        for p in paths.values():
            print(f"  {p}")
        if short:
            print("needs attention: the body cites fewer evidence units than the sample "
                  "size the rubric asks for")
    return 1 if short else 0


if __name__ == "__main__":
    sys.exit(main())
