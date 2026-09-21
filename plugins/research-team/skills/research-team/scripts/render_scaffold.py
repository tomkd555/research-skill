#!/usr/bin/env python3
"""render_scaffold.py — build the report skeleton and the per-KQ slices from the ledger.

Run it before the writing in research-team Step 4. Everything in the report that is a
transcription of the ledger — the header metrics, the search-log table, the source list —
is generated here, so the orchestrator never copies the same rows twice across the two
writing passes. The analysis sections (the answer to the decision, the summary, the
per-KQ conclusions, disconfirmation, insight, limitations) get their headings only; the
writer fills them. The `## Analysis` section gets its headings and placeholder tables the
same way: the writer edits the placeholders in place, so those blocks carry no markers of
their own. The KQ coverage table carries no markers either: its evidence and verification
columns come from the ledger, but its Conclusion and Confidence columns are the writer's,
so it is rendered once and left in place afterwards.

Every ledger-derived block sits between a `<!-- generated:NAME -->` / `<!-- /generated:NAME -->`
pair. `--merge` uses those markers to refresh a report's generated regions in place, after
a resubmission changes the ledger, without touching the writer's own prose; it locates a
missing Analysis block or a missing KQ coverage table by its heading and appends it whole.

A per-KQ slice (kq_slices/KQ{n}.md) tabulates that key question's evidence alone. It is
the unit of split synthesis (interpretation_contract.md §3), and reading one is
equivalent to reading the ledger.

Examples:
    python render_scaffold.py evidence_log.json --out report_scaffold.md --slices kq_slices/ \\
        --question-type diagnostic
    python render_scaffold.py evidence_log.json --slices kq_slices/
    python render_scaffold.py evidence_log.json --merge report.md
    python render_scaffold.py evidence_log.json --out report.md --slices kq_slices/ --json

Exit codes: 0 = fine / 2 = usage or I/O error
"""

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels
from labels import T

CROSS_SLICE_NAME = "cross_cutting.md"


def gen_begin(name):
    return f"<!-- generated:{name} -->"


def gen_end(name):
    return f"<!-- /generated:{name} -->"


# Markers around a generated region. report_auditor.py's emptiness check for the
# disconfirmation section discounts the lines between each pair, so transcribing the
# ledger cannot on its own satisfy the check. The Analysis blocks carry no markers: the
# writer edits their placeholder tables and bullets in place, so a generated region
# there would mean --merge overwrote that editing.
DISCONFIRMATION_BEGIN = gen_begin("disconfirmation")
DISCONFIRMATION_END = gen_end("disconfirmation")
EARLY_STOP_BEGIN = gen_begin("early_stop")
EARLY_STOP_END = gen_end("early_stop")

# A whole generated region, wherever it sits: begin marker, its content, matching end
# marker. Used by --merge to line up a fresh region with the one it replaces.
MARKER_RE = re.compile(
    r"<!--\s*generated:(\w+)\s*-->.*?<!--\s*/generated:\1\s*-->", re.DOTALL)

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
    """The KQ coverage table. The Conclusion and Confidence columns carry the scaffold's
    placeholders; the writer fills them in place. The evidence and verification columns
    come from the ledger, so a fresh render always states them correctly."""
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


def coverage_section(log):
    """The `## KQ coverage` heading plus its table. Rendered once, with no
    generated:NAME markers around it; --merge locates it by the heading."""
    return [T("sec_coverage"), "", coverage_table(log), ""]


def has_coverage_heading(text):
    """Does text already carry a heading naming the KQ coverage section?"""
    keywords = labels.section_keywords("COVERAGE")
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if m and any(k in m.group(1).lower() for k in keywords):
            return True
    return False


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
        suffix = " (user-supplied local file)" if s.get("user_supplied") else ""
        lines.append(f"- [{e.get('id')}] {s.get('publisher', '')}. {s.get('title', '')}. "
                     f"{s.get('published', '')}. {T('grade_prefix')}"
                     f"{s.get('grade', '')}. {s.get('url', '')}{suffix}")
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


# ----------------------------------------------------------- the Analysis section

def _plus_one_year(as_of):
    """The as_of date, twelve months on (the Premortem's "it is {…} and it failed")."""
    try:
        d = datetime.date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return f"{as_of} + 12 months" if as_of else "{as_of + 12 months}"
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        # as_of was a leap day; there is no such day a non-leap year later.
        return d.replace(year=d.year + 1, day=28).isoformat()


def _ach_body(log):
    rows = [T("tbl_ach"), "|---|---|---|---|", "| E# | + | − | high |"]
    return "\n".join(rows) + "\n\n" + T("tbl_ach_legend") + "\n\n" + T("blk_ach_lines")


def _mechanism_body(log):
    return T("blk_mechanism")


def _outside_body(log):
    return T("blk_outside")


def _incentive_body(log):
    rows = [T("tbl_incentive"), "|---|---|---|---|---|"]
    figures = [e for e in log.get("evidence", []) if e.get("is_key_figure")]
    for e in figures:
        s = e.get("source") or {}
        self_reported = "true" if e.get("self_reported") else "false"
        rows.append(f"| {esc(e.get('id'))} | {esc(s.get('publisher'))} | {{…}} | "
                    f"{self_reported} | {esc(', '.join(e.get('corroborating_ids') or []))} |")
    if not figures:
        rows.append(T("tbl_incentive_empty"))
    rows += ["", T("blk_incentive_line")]
    return "\n".join(rows)


def _second_body(log):
    return "\n".join([T("tbl_second"), "|---|---|---|---|---|", T("tbl_second_row")])


def _premortem_body(log):
    return T("blk_premortem") % _plus_one_year(log.get("as_of", ""))


def _rival_body(log):
    return T("blk_rival")


ANALYSIS_BODY = {
    "ACH": _ach_body,
    "MECHANISM": _mechanism_body,
    "OUTSIDE": _outside_body,
    "INCENTIVE": _incentive_body,
    "SECOND": _second_body,
    "PREMORTEM": _premortem_body,
    "RIVAL": _rival_body,
}


def analysis_block(code, log):
    """One Analysis block: its H3 heading plus the placeholder table or bullets the
    writer edits in place. No markers: --merge must never overwrite that editing."""
    heading = labels.ANALYSIS_BLOCKS[code]
    return [T("blk_head") % heading, "", ANALYSIS_BODY[code](log), ""]


def analysis_has_block(text, code):
    """Does text already carry this block's H3 heading?"""
    heading = labels.ANALYSIS_BLOCKS[code]
    return bool(re.search(r"(?m)^###[ \t]+.*" + re.escape(heading), text, re.IGNORECASE))


def analysis_section(log, question_type):
    """The `## Analysis` section: only the blocks labels.ANALYSIS_REQUIRED names."""
    parts = [T("sec_analysis"), "", T("analysis_note"), ""]
    for code in labels.ANALYSIS_REQUIRED.get(question_type, ()):
        parts += analysis_block(code, log)
    return parts


def build_scaffold(log, question_type="descriptive"):
    m = header_metrics(log)
    kqs = log.get("key_questions", [])
    evidence = live_evidence(log.get("evidence", []))
    bd = m["verification_breakdown"]
    sep = T("hdr_sep")
    parts = [
        T("report_title") % log.get("topic", ""),
        "",
        gen_begin("header"),
        T("hdr_meta") % (m["as_of"], m["mode"]),
        T("hdr_counts") % (m["independent_sources"], m["evidence_units"])
        + (T("hdr_excluded") % m["excluded_units"] if m["excluded_units"] else "")
        + T("hdr_verified") % m["verified_claims"],
        T("hdr_breakdown") + sep.join(f"{s} {bd[s]}" for s in VERIFICATION_STATES),
        gen_end("header"),
        T("hdr_qtype") % question_type,
        T("hdr_overall"),
        "",
        T("sec_decision"),
        "",
        T("decision_placeholder"),
        "",
        T("decision_overturn"),
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
        marker = f"kq_{kq_id}" if kq_id else "kq_"
        parts += [
            f"### {kq_id}: {kq.get('text', '')}",
            "",
            gen_begin(marker),
            T("ceil_line") % (ceiling, reason),
            "",
            evidence_table(mine),
            gen_end(marker),
            "",
            T("placeholder"),
            "",
        ]
    parts += analysis_section(log, question_type)
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
        gen_begin("gaps"),
        gaps_table(log),
        gen_end("gaps"),
        "",
        EARLY_STOP_BEGIN,
        early_stop_table(log),
        EARLY_STOP_END,
        "",
        T("placeholder"),
        "",
        *coverage_section(log),
        T("sec_searchlog"),
        "",
        gen_begin("searchlog"),
        search_log_table(log),
        gen_end("searchlog"),
        "",
        T("sec_sources"),
        "",
        gen_begin("sources"),
        sources_list(log),
        gen_end("sources"),
        "",
    ]
    return "\n".join(parts)


def merge_scaffold(fresh_text, existing_text, log, question_type):
    """Refresh every generated:NAME region of existing_text with fresh_text's region of
    the same name, leaving everything outside the markers untouched. The Analysis blocks
    and the KQ coverage table carry no markers, so none of the writer's editing there is
    ever replaced; a required Analysis block existing_text does not already have (found
    by its H3 heading) is appended whole before sec_counter, and a KQ coverage table
    (found by its heading) is appended whole before sec_searchlog. Returns
    (merged_text, missing_regions).
    """
    fresh_blocks = {m.group(1): m.group(0) for m in MARKER_RE.finditer(fresh_text)}
    existing_names = {m.group(1) for m in MARKER_RE.finditer(existing_text)}

    def repl(m):
        return fresh_blocks.get(m.group(1), m.group(0))

    merged = MARKER_RE.sub(repl, existing_text)
    missing = [name for name in fresh_blocks if name not in existing_names]

    to_append = [code for code in labels.ANALYSIS_REQUIRED.get(question_type, ())
                if not analysis_has_block(merged, code)]
    if to_append:
        insert = "\n".join("\n".join(analysis_block(code, log)) for code in to_append)
        idx = merged.find(T("sec_counter"))
        if idx == -1:
            missing = missing + [f"analysis:{labels.ANALYSIS_BLOCKS[code]}" for code in to_append]
        else:
            merged = merged[:idx] + insert + "\n" + merged[idx:]

    if not has_coverage_heading(merged):
        insert = "\n".join(coverage_section(log))
        idx = merged.find(T("sec_searchlog"))
        if idx == -1:
            missing = missing + ["coverage"]
        else:
            merged = merged[:idx] + insert + "\n" + merged[idx:]

    return merged, missing


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
    out_group = parser.add_mutually_exclusive_group()
    out_group.add_argument("--out", default=None,
                           help="where the skeleton goes (report_scaffold.md and the like); "
                                "required unless --slices or --merge is given")
    out_group.add_argument("--merge", default=None, metavar="INTO.md",
                           help="refresh the generated regions of an existing report in "
                                "place, leaving the writer's prose untouched")
    parser.add_argument("--slices", default=None, help="output directory for the per-KQ slices")
    parser.add_argument("--question-type", choices=labels.QUESTION_TYPES, default=None,
                        help="which Analysis blocks are required (default: descriptive)")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--force", action="store_true",
                        help="overwrite --out even if it exists (any writing there is "
                             "lost; --merge is how a resubmission refreshes a report in place)")
    args = parser.parse_args()

    if not args.out and not args.merge and not args.slices:
        parser.error("one of --out, --merge or --slices is required")

    existing_text = None
    if args.merge:
        try:
            with open(args.merge, encoding="utf-8") as f:
                existing_text = f.read()
        except OSError as e:
            print(f"error: cannot read the file to merge into: {e}", file=sys.stderr)
            return 2

    question_type = args.question_type
    if question_type is None and existing_text is not None:
        question_type = labels.question_type_of(existing_text)
    if question_type is None:
        question_type = "descriptive"
        print("note: --question-type not given; defaulting to descriptive", file=sys.stderr)

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
    except OSError as e:
        print(f"error: cannot read the ledger: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: the ledger is not valid JSON: {e}", file=sys.stderr)
        return 2

    if args.out and os.path.exists(args.out) and not args.force:
        print(f"error: the output already exists: {args.out}\n"
              "  It is not overwritten, so that writing already done survives. Use\n"
              "  --merge INTO.md to refresh the generated regions of a report already\n"
              "  written. Pass --force to rebuild it anyway.",
              file=sys.stderr)
        return 2

    scaffold = build_scaffold(log, question_type)
    slice_paths = []
    missing_regions = None
    try:
        if args.out:
            out_dir = os.path.dirname(os.path.abspath(args.out))
            os.makedirs(out_dir, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(scaffold)
        if args.merge:
            merged, missing_regions = merge_scaffold(scaffold, existing_text, log, question_type)
            with open(args.merge, "w", encoding="utf-8") as f:
                f.write(merged)
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
        "out": os.path.abspath(args.out) if args.out else None,
        "merge": os.path.abspath(args.merge) if args.merge else None,
        "slices": slice_paths,
        "source_lines": len(log.get("evidence", [])),
        "search_log_rows": len(log.get("search_log", [])),
        **header_metrics(log),
    }
    if missing_regions is not None:
        summary["missing_regions"] = missing_regions
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if summary["out"]:
            print(f"skeleton: {summary['out']}")
        if summary["merge"]:
            print(f"merged into: {summary['merge']}")
            if missing_regions:
                print(f"  regions the target lacks: {', '.join(missing_regions)}")
        print(f"  sources {summary['source_lines']} rows / "
              f"search log {summary['search_log_rows']} rows / "
              f"independent sources {summary['independent_sources']} / "
              f"confirmed {summary['verified_claims']}")
        for p in slice_paths:
            print(f"  slice: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
