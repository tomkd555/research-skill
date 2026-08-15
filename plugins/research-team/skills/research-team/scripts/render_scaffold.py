#!/usr/bin/env python3
"""render_scaffold.py — build the report skeleton and the per-KQ slices from the ledger.

Run it before the writing in research-team Step 4. Everything in the report that is a
transcription of the ledger — the header metrics, the evidence and verification columns
of the KQ coverage table, the search-log table, the source list — is generated here, so
the orchestrator never copies the same rows twice across the two writing passes. The
analysis sections (the answer to the decision, the summary, the per-KQ conclusions,
disconfirmation, insight, limitations) get their headings only; the writer fills them.

A per-KQ slice (kq_slices/KQ{n}.md) tabulates that key question's evidence alone. It is
the unit of split synthesis (interpretation_contract.md §3), and reading one is
equivalent to reading the ledger.

Examples:
    python render_scaffold.py evidence_log.json --out report_scaffold.md --slices kq_slices/
    python render_scaffold.py evidence_log.json --out report.md --slices kq_slices/ --json

Exit codes: 0 = fine / 2 = usage or I/O error
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels
from labels import T

CROSS_SLICE_NAME = "cross_cutting.md"

# Markers around a generated region. report_auditor.py's emptiness check for the
# disconfirmation section discounts the lines between each pair, so transcribing the
# ledger cannot on its own satisfy the check.
DISCONFIRMATION_BEGIN = "<!-- generated:disconfirmation -->"
DISCONFIRMATION_END = "<!-- /generated:disconfirmation -->"
EARLY_STOP_BEGIN = "<!-- generated:early_stop -->"
EARLY_STOP_END = "<!-- /generated:early_stop -->"

VERIFICATION_STATES = ("confirmed", "plausible", "disputed", "refuted", "unchecked")

# The top four of the seven estimative levels, which are the ones a ceiling can take.
# Held as ranks, strongest first (0 is strongest); labels.CONFIDENCE holds the wording
# and the probability band.
CEILING_RANKS = (0, 1, 2, 3)
# The ceiling for a KQ with no confirmed evidence at all (evaluation_protocol.md §5).
UNVERIFIED_CEILING = 2


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def esc(text):
    """Strip the newlines and pipes out of a string bound for a table cell."""
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def status_of(e):
    return (e.get("verification") or {}).get("status") or "unchecked"


def live_evidence(evidence):
    """The evidence minus what was refuted and what a later unit superseded."""
    return [e for e in evidence
            if status_of(e) != "refuted" and not e.get("superseded_by")]


def header_metrics(log):
    """The header metrics. Counts cover only evidence a conclusion may rest on.

    Counting the refuted and the superseded units too would put an independent-source
    count and an evidence count at the top of the report that overstate what the body
    can actually draw on.
    """
    evidence = log.get("evidence", [])
    live = live_evidence(evidence)
    clusters = {(e.get("source") or {}).get("origin_cluster") for e in live}
    clusters.discard(None)
    verified = sum(1 for e in live if status_of(e) == "confirmed")
    breakdown = {s: sum(1 for e in evidence if status_of(e) == s) for s in VERIFICATION_STATES}
    return {
        "as_of": log.get("as_of", ""),
        "mode": log.get("mode", ""),
        "independent_sources": len(clusters),
        "evidence_units": len(live),
        "excluded_units": len(evidence) - len(live),
        "verified_claims": verified,
        "verification_breakdown": breakdown,
    }


def source_ceiling(items):
    """The ceiling from source quality and independence alone. Returns (rank, reason key)."""
    if any(e.get("corroboration") == "conflicting" for e in items):
        return 3, "ceil_conflict"
    clusters = {(e.get("source") or {}).get("origin_cluster") for e in items}
    clusters.discard(None)
    a_clusters = {(e.get("source") or {}).get("origin_cluster") for e in items
                  if (e.get("source") or {}).get("grade") == "A"}
    a_clusters.discard(None)
    if len(a_clusters) >= 2:
        return 0, "ceil_two_a"
    grades = {(e.get("source") or {}).get("grade") for e in items}
    if len(clusters) >= 2:
        return 1, "ceil_two_clusters"
    if "A" in grades:
        return 1, "ceil_single_a"
    if "B" in grades:
        return 2, "ceil_single_b"
    return 3, "ceil_c_only"


def confidence_ceiling(items):
    """The confidence ceiling for one KQ's evidence (the calibration rule of §5).

    Returns (label, band, reason). The final choice of label stays with the writer.

    Source quality and independence do not settle it alone. A KQ with no evidence that
    the verification stage confirmed is capped at the third level, because §5 refuses a
    high confidence to a claim that never passed citation existence, attribution and a
    disconfirmation search, however good its sources look.
    """
    if not items:
        return "—", "", T("ceil_none")
    rank, reason_key = source_ceiling(items)
    reason = T(reason_key)
    confirmed = sum(1 for e in items
                    if (e.get("verification") or {}).get("status") == "confirmed")
    if not confirmed and rank < UNVERIFIED_CEILING:
        reason += T("ceil_capped") % labels.confidence_label(UNVERIFIED_CEILING)
        rank = UNVERIFIED_CEILING
    return labels.confidence_label(rank), labels.confidence_band(rank), reason


def evidence_table(items):
    """One KQ's evidence. The ID column is bare, so it is not counted as a body citation."""
    rows = [T("tbl_evidence"), "|---|---|---|---|---|"]
    for e in items:
        claim = esc(e.get("claim", ""))
        if len(claim) > 60:
            claim = claim[:59] + "…"
        rows.append(f"| {esc(e.get('id'))} | {claim} | "
                    f"{esc((e.get('source') or {}).get('grade'))} | "
                    f"{esc(e.get('corroboration'))} | {esc(status_of(e))} |")
    if len(rows) == 2:
        rows.append(T("tbl_evidence_empty"))
    return "\n".join(rows)


def disconfirmation_table(rows):
    lines = [T("tbl_disconf"), "|---|---|---|---|---|"]
    for d in rows:
        queries = d.get("queries") or []
        lines.append(f"| {esc(d.get('hypothesis'))} | {esc(d.get('expected_if_false'))} | "
                     f"{esc(', '.join(queries))} | {esc(d.get('found'))} | "
                     f"{esc(d.get('impact'))} |")
    if len(lines) == 2:
        lines.append(T("tbl_disconf_empty"))
    return "\n".join(lines)


def coverage_table(log):
    rows = [T("tbl_coverage"), "|---|---|---|---|---|"]
    evidence = log.get("evidence", [])
    for kq in log.get("key_questions", []):
        kq_id = kq.get("id", "")
        mine = [e for e in evidence if kq_id in (e.get("kq_ids") or [])]
        key_first = [e for e in mine if e.get("is_key_figure")] + \
                    [e for e in mine if not e.get("is_key_figure")]
        ids = [e.get("id") for e in key_first[:6]]
        states = []
        for e in key_first[:6]:
            states.append((e.get("verification") or {}).get("status") or "unchecked")
        uniq_states = sorted(set(states)) or ["unchecked"]
        rows.append(f"| {kq_id} | {T('coverage_conclusion')} | "
                    f"{T('coverage_label')} | {esc(', '.join(ids))} | "
                    f"{esc(', '.join(uniq_states))} |")
    return "\n".join(rows)


def search_log_table(log):
    rows = [T("tbl_searchlog"), "|---|---|---|---|---|"]
    for s in log.get("search_log", []):
        rows.append(f"| {esc(s.get('query'))} | {esc(s.get('tool'))} | "
                    f"{esc(s.get('adopted'))} | {esc(s.get('kind'))} | "
                    f"{esc(s.get('kq_id'))} |")
    return "\n".join(rows)


def sources_list(log):
    lines = []
    for e in log.get("evidence", []):
        s = e.get("source") or {}
        lines.append(f"- [{e.get('id')}] {s.get('publisher', '')}. {s.get('title', '')}. "
                     f"{s.get('published', '')}. {T('grade_prefix')}"
                     f"{s.get('grade', '')}. {s.get('url', '')}")
    return "\n".join(lines)


def gaps_table(log):
    rows = [T("tbl_gaps"), "|---|---|---|"]
    for g in log.get("gaps", []):
        tried = g.get("tried_queries") or []
        rows.append(f"| {esc(g.get('claim'))} | {esc(', '.join(tried))} | "
                    f"{esc(g.get('recommended'))} |")
    if len(rows) == 2:
        rows.append(T("tbl_gaps_empty"))
    return "\n".join(rows)


def early_stop_table(log):
    """The groups that stopped early. An early stop means "not looked into", not
    "not there", so it is transcribed mechanically into the limitations section
    (collection_standards.md §1)."""
    rows = [T("tbl_earlystop"), "|---|---|---|---|---|---|"]
    for s in log.get("floor_status") or []:
        record = (s or {}).get("early_stop")
        if not isinstance(record, dict):
            continue
        rows.append(f"| {esc(s.get('kq_id'))} | {esc(s.get('role'))} | "
                    f"{esc(record.get('independent_sources'))} | "
                    f"{esc(record.get('consecutive_zero_new'))} {T('queries_unit')} | "
                    f"{esc(record.get('conclusion_confidence'))} | "
                    f"{esc(record.get('note'))} |")
    if len(rows) == 2:
        rows.append(T("tbl_earlystop_empty"))
    return "\n".join(rows)


def build_scaffold(log):
    m = header_metrics(log)
    kqs = log.get("key_questions", [])
    evidence = live_evidence(log.get("evidence", []))
    bd = m["verification_breakdown"]
    sep = T("hdr_sep")
    parts = [
        T("report_title") % log.get("topic", ""),
        "",
        T("hdr_meta") % (m["as_of"], m["mode"]),
        T("hdr_counts") % (m["independent_sources"], m["evidence_units"])
        + (T("hdr_excluded") % m["excluded_units"] if m["excluded_units"] else "")
        + T("hdr_verified") % m["verified_claims"],
        T("hdr_breakdown") + sep.join(f"{s} {bd[s]}" for s in VERIFICATION_STATES),
        T("hdr_overall"),
        "",
        T("sec_decision"),
        "",
        T("decision_placeholder"),
        "",
        T("sec_summary"),
        "",
        T("placeholder"),
        "",
        T("sec_kq"),
        "",
    ]
    for kq in kqs:
        kq_id = kq.get("id", "")
        mine = [e for e in evidence if kq_id in (e.get("kq_ids") or [])]
        label, band, reason = confidence_ceiling(mine)
        ceiling = f"{label} ({band})" if band else label
        parts += [
            f"### {kq_id}: {kq.get('text', '')}",
            "",
            T("ceil_line") % (ceiling, reason),
            "",
            evidence_table(mine),
            "",
            T("placeholder"),
            "",
        ]
    parts += [
        T("sec_counter"),
        "",
        DISCONFIRMATION_BEGIN,
        disconfirmation_table(log.get("disconfirmation") or []),
        DISCONFIRMATION_END,
        "",
        T("placeholder"),
        "",
        T("sec_insight"),
        "",
        T("placeholder"),
        "",
        T("sec_limits"),
        "",
        gaps_table(log),
        "",
        EARLY_STOP_BEGIN,
        early_stop_table(log),
        EARLY_STOP_END,
        "",
        T("placeholder"),
        "",
        T("sec_coverage"),
        "",
        coverage_table(log),
        "",
        T("sec_searchlog"),
        "",
        search_log_table(log),
        "",
        T("sec_sources"),
        "",
        sources_list(log),
        "",
    ]
    return "\n".join(parts)


def evidence_entries(items):
    """How a slice describes one evidence unit. No URL, no independence cluster.

    The source list is generated on the skeleton side, so there is no route by which
    the writer copies a URL out by hand, and evidence_auditor.py checks the clusters
    mechanically.
    """
    lines = []
    for e in items:
        s = e.get("source") or {}
        ver = e.get("verification") or {}
        ids = ", ".join(e.get("corroborating_ids") or [])
        source = (f"{s.get('publisher', '')}. {s.get('title', '')}. "
                  f"{s.get('published', '')}. "
                  f"{T('grade_prefix')}{s.get('grade', '')}")
        corroboration = e.get("corroboration", "")
        if ids:
            corroboration += f" ({ids})"
        verification = ver.get("status", "unchecked")
        if ver.get("confidence_band"):
            verification += f" / {ver.get('confidence_band')}"
        if ver.get("note"):
            verification += f" / {ver.get('note')}"
        lines += [
            f"## {e.get('id')}" + (T("slice_key_figure") if e.get("is_key_figure") else ""),
            "",
            T("slice_claim") % e.get("claim", ""),
            T("slice_quote") % e.get("verbatim_quote", ""),
            T("slice_source") % source,
            T("slice_corroboration") % corroboration,
            T("slice_verification") % verification,
            "",
        ]
    return lines


def build_slice(log, kq):
    kq_id = kq.get("id", "")
    mine = [e for e in log.get("evidence", []) if kq_id in (e.get("kq_ids") or [])]
    lines = [f"# {kq_id}: {kq.get('text', '')}", "", T("slice_count") % len(mine), ""]
    lines += evidence_entries(mine)
    # Only the disconfirmation recorded while collecting for this KQ. A record with no
    # kq_id is of unknown provenance, so it goes into every slice.
    disc = [d for d in log.get("disconfirmation") or []
            if d.get("kq_id") in (None, "", kq_id)]
    if disc:
        lines += [T("slice_disc_head"), ""]
        for d in disc:
            lines.append(T("slice_disc_item") % (d.get("hypothesis", ""), d.get("found", ""))
                         + (f" — {d.get('impact')}" if d.get("impact") else ""))
        lines.append("")
    return "\n".join(lines)


def build_cross_slice(log):
    """The slice for evidence belonging to no key question.

    A section that cuts across the key questions — the summary, the insights — is
    short of material if the per-KQ slices are all the writer has.
    """
    kq_ids = {k.get("id") for k in log.get("key_questions", [])}
    orphans = [e for e in log.get("evidence", [])
               if not (set(e.get("kq_ids") or []) & kq_ids)]
    lines = [T("cross_title"), "", T("cross_count") % len(orphans), ""]
    if not orphans:
        lines += [T("cross_none"), ""]
    lines += evidence_entries(orphans)
    return "\n".join(lines)


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Build the report skeleton and the per-KQ slices from the ledger")
    parser.add_argument("log", help="path to evidence_log.json")
    parser.add_argument("--out", required=True,
                        help="where the skeleton goes (report_scaffold.md and the like)")
    parser.add_argument("--slices", default=None, help="output directory for the per-KQ slices")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the output even if it exists (any writing is lost)")
    args = parser.parse_args()

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
    except OSError as e:
        print(f"error: cannot read the ledger: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: the ledger is not valid JSON: {e}", file=sys.stderr)
        return 2

    if os.path.exists(args.out) and not args.force:
        print(f"error: the output already exists: {args.out}\n"
              "  It is not overwritten, so that writing already done survives. To regenerate\n"
              "  after a resubmission, write to --out report_scaffold.md and replace only the\n"
              "  generated tables in report.md. Pass --force to rebuild it anyway.",
              file=sys.stderr)
        return 2

    scaffold = build_scaffold(log)
    slice_paths = []
    try:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(scaffold)
        if args.slices:
            os.makedirs(args.slices, exist_ok=True)
            for kq in log.get("key_questions", []):
                p = os.path.join(args.slices, f"{kq.get('id', 'KQ')}.md")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(build_slice(log, kq))
                slice_paths.append(p)
            p = os.path.join(args.slices, CROSS_SLICE_NAME)
            with open(p, "w", encoding="utf-8") as f:
                f.write(build_cross_slice(log))
            slice_paths.append(p)
    except OSError as e:
        print(f"error: cannot write the output: {e}", file=sys.stderr)
        return 2

    summary = {
        "out": os.path.abspath(args.out),
        "slices": slice_paths,
        "source_lines": len(log.get("evidence", [])),
        "search_log_rows": len(log.get("search_log", [])),
        **header_metrics(log),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"skeleton: {summary['out']}")
        print(f"  sources {summary['source_lines']} rows / "
              f"search log {summary['search_log_rows']} rows / "
              f"independent sources {summary['independent_sources']} / "
              f"confirmed {summary['verified_claims']}")
        for p in slice_paths:
            print(f"  slice: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
