#!/usr/bin/env python3
"""report_auditor.py — the deterministic audit of the research report (report.md).

Run it in research-team Step 4 (right after the draft and the revision) and in Step 5
(the deterministic audit). It resolves the evidence IDs and checks the required
sections, vague expressions, uncited figures, KQ coverage and the confidence
vocabulary, plus the items of the evaluation_protocol.md rubric a machine can decide:
R1 (a heading and a coverage row per KQ), R3 (both sides of a conflict), R4 (the
disconfirmation section has a body), R5 (point estimates and probability bands), R13
(citation checking covers every unit) and R14 (thin evidence stated as fact). Standard
library only.

Examples:
    python report_auditor.py report.md --evidence evidence_log.json
    python report_auditor.py report.md --evidence evidence_log.json --citation citation_check.json --json

Exit codes: 0 = PASS or WARN only / 1 = at least one FAIL / 2 = usage or I/O error
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels

# Required sections: (code, the keywords a heading must contain). labels.py holds them,
# so the generator and this auditor cannot drift apart.
REQUIRED_SECTIONS = labels.REPORT_SECTIONS

AMBIGUOUS_PATTERNS = labels.AMBIGUOUS_PATTERNS

CONFIDENCE_LABELS = labels.CONFIDENCE_LABELS

EVIDENCE_MARKER_RE = re.compile(r"\[E(\d+)\]")

# The markers around what render_scaffold.py generated from the ledger. Lines between
# the pair are not the writer's own, so they do not count towards the disconfirmation
# section having a body.
GENERATED_BEGIN_RE = re.compile(r"^\s*<!--\s*generated:\w+\s*-->\s*$")
GENERATED_END_RE = re.compile(r"^\s*<!--\s*/generated:\w+\s*-->\s*$")
NUMERIC_ASSERTION_RE = labels.NUMERIC_ASSERTION_RE

# A probability band (65-80%). Excluded from point-estimate detection.
PROB_BAND_RE = labels.PROB_BAND_RE
# A point estimate ("confidence 75%"), which the seven labels plus a band replace.
POINT_ESTIMATE_RE = labels.POINT_ESTIMATE_RE

# The R14 qualifiers. A claim on thin evidence carrying one is not an assertion.
HEDGE_PATTERNS = labels.HEDGE_PATTERNS
# The verification.status values that count as thin (unchecked included).
THIN_VERIFICATION = {"plausible", "disputed", "unchecked", ""}
# The severity of R-THIN and R-CONFLICT-PAIR. Drop either to "WARN" if false positives
# get out of hand.
THIN_SEVERITY = "FAIL"
CONFLICT_PAIR_SEVERITY = "FAIL"


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def classify_lines(text):
    """Tag each line with (number, line, the heading it sits under, inside a code block)."""
    rows = []
    section = "_preamble"
    in_code = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
            rows.append((i, line, section, True))
            continue
        m = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if m and not in_code:
            section = m.group(1)
        rows.append((i, line, section, in_code))
    return rows


def section_matches(section, keywords):
    """Does the heading contain one of the keywords? Case-insensitive."""
    low = section.lower()
    return any(k.lower() in low for k in keywords)


def split_sentences(line):
    """Split a line into sentences, keeping the terminating punctuation."""
    parts = labels.SENTENCE_SPLIT_RE.split(line)
    return [p for p in (s.strip() for s in parts) if p]


def is_substantive(line):
    """Is this a line of substance — not a heading, a blank, a comment or a rule?"""
    s = line.strip()
    if not s or s.startswith(("#", "<!--", "---", "***")):
        return False
    return True


def audit(report_text, evidence_log, citation_check=None):
    findings = []

    def add(severity, code, message, location=""):
        findings.append({"severity": severity, "code": code,
                         "message": message, "location": location})

    rows = classify_lines(report_text)
    evidence = evidence_log.get("evidence", [])
    known_ids = {e.get("id") for e in evidence}
    kq_ids = [k.get("id") for k in evidence_log.get("key_questions", [])]

    # 1. Resolving the evidence markers.
    # used_ids counts every reference (for undefined references and unused evidence).
    # body_ids counts only references outside the source list and the search log: the
    # source list enumerates the whole ledger mechanically, so counting it would hide
    # both "the body cites nothing" and "the body rests on refuted evidence".
    exempt = labels.section_keywords("SEARCHLOG") + labels.section_keywords("SOURCES")
    coverage = labels.section_keywords("COVERAGE")
    used_ids = set()
    body_ids = set()
    for i, line, section, in_code in rows:
        for m in EVIDENCE_MARKER_RE.finditer(line):
            eid = f"E{m.group(1)}"
            used_ids.add(eid)
            if not in_code and not section_matches(section, exempt):
                body_ids.add(eid)
            if eid not in known_ids:
                add("FAIL", "R-EREF", f"reference to an undefined evidence ID {eid}", f"line {i}")
    if not body_ids:
        add("FAIL", "R-NOEVIDENCE", "the report body cites no evidence ID [E#] at all")

    # 2. The required sections.
    sections_present = {s for _, _, s, _ in rows}
    for code, keywords in REQUIRED_SECTIONS:
        if not any(section_matches(s, keywords) for s in sections_present):
            add("FAIL", f"R-SEC-{code}", f"the required section ({'/'.join(keywords)}) is missing")
    # A section on the limits of the work is demanded separately and by narrower words,
    # because LIMITS also matches "gaps" and COUNTER also matches "conflicting".
    limit_words = ("limitations", "disconfirmation")
    if not any(section_matches(s, limit_words) for s in sections_present):
        add("FAIL", "R-SEC-LIMITWORD",
            "no heading contains \"limitations\" or \"disconfirmation\" "
            "(a section stating where the method applies is required)")

    # 3. The as-of date.
    if not re.search(r"as_of[^\n]*\d{4}-\d{2}-\d{2}", report_text):
        add("WARN", "R-ASOF", "no as-of date (as_of: YYYY-MM-DD) is stated")

    # 4. Vague expressions (code blocks, the search log and the sources excepted).
    for i, line, section, in_code in rows:
        if in_code or section_matches(section, exempt):
            continue
        low = line.lower()
        for pat in AMBIGUOUS_PATTERNS:
            if pat in low:
                add("WARN", "R-VAGUE",
                    f"the vague expression \"{pat}\" is used; replace it with one of the "
                    "seven confidence labels plus its band", f"line {i}")

    # 5. Figures asserted without a citation (tables, headings and the excepted sections aside).
    uncited = []
    for i, line, section, in_code in rows:
        if in_code or section_matches(section, exempt + coverage):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", ">", "<!--")):
            continue
        # A confidence label or a probability band (65-80%) is not an asserted figure.
        if labels.contains_confidence(line) or PROB_BAND_RE.search(line):
            continue
        if NUMERIC_ASSERTION_RE.search(line) and not EVIDENCE_MARKER_RE.search(line):
            uncited.append(i)
    for i in uncited[:20]:
        add("WARN", "R-UNCITED", "a figure is stated with no evidence ID", f"line {i}")
    if len(uncited) > 20:
        add("WARN", "R-UNCITED",
            f"{len(uncited) - 20} further lines state a figure with no evidence ID")

    # 6. KQ coverage (does every KQ appear in the report?).
    for kq in kq_ids:
        if not re.search(rf"\b{kq}\b", report_text):
            add("FAIL", "R-KQ",
                f"{kq} is never mentioned (it needs a conclusion, or a statement that it "
                "is unresolved)")

    # 7. The confidence vocabulary. Every report states an overall confidence, so a report
    # carrying no English label has had its labels translated along with the prose.
    labels_used = [lb for lb in CONFIDENCE_LABELS if lb in report_text.lower()]
    if not labels_used:
        add("FAIL", "R-CONF",
            "the report carries none of the seven confidence labels; they stay in the English "
            "wording labels.py holds, whatever language the prose is in")

    # 8. Refuted evidence must not be used.
    refuted = {e.get("id") for e in evidence
               if (e.get("verification") or {}).get("status") == "refuted"}
    for eid in sorted(body_ids & refuted):
        add("FAIL", "R-REFUTED", f"the report body cites refuted evidence {eid}")

    # 8b. Nor must superseded evidence.
    superseded = {e.get("id"): e.get("superseded_by")
                  for e in evidence if e.get("superseded_by")}
    for eid in sorted(body_ids & set(superseded)):
        add("FAIL", "R-SUPERSEDED",
            f"the report body cites superseded evidence {eid} "
            f"(cite its replacement {superseded[eid]})")

    # 9. Unused evidence (informational).
    unused = sorted(known_ids - body_ids, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    if unused:
        add("INFO", "R-UNUSED",
            f"{len(unused)} evidence units are never cited: {', '.join(unused[:10])}")

    # 10. R1: a heading and a coverage row per KQ (appearing somewhere is not enough).
    heading_sections = {s for _, line, s, in_code in rows
                        if not in_code and re.match(r"^#{1,4}\s+", line)}
    coverage_rows = [line for _, line, section, in_code in rows
                     if not in_code and section_matches(section, coverage)
                     and line.strip().startswith("|")]
    for kq in kq_ids:
        if not any(kq in s for s in heading_sections):
            add("FAIL", "R-KQ2", f"no heading carries {kq}'s conclusion (a heading must name it)")
        if not any(kq in r for r in coverage_rows):
            add("FAIL", "R-KQ2", f"{kq} has no row in the KQ coverage table")

    # 11. R14: a claim on thin evidence (single_source, or plausible and below) stated as fact.
    thin_ids = set()
    for e in evidence:
        status = ((e.get("verification") or {}).get("status") or "").strip()
        if e.get("corroboration") == "single_source" or status in THIN_VERIFICATION:
            thin_ids.add(e.get("id"))
    for i, line, section, in_code in rows:
        if in_code or section_matches(section, exempt + coverage):
            continue
        if not is_substantive(line):
            continue
        for sentence in split_sentences(line):
            cited = {f"E{m.group(1)}" for m in EVIDENCE_MARKER_RE.finditer(sentence)}
            hit = sorted(cited & thin_ids)
            if not hit:
                continue
            if labels.contains_confidence(sentence):
                continue
            if any(h in sentence.lower() for h in HEDGE_PATTERNS):
                continue
            # What is left once the markers and the trailing punctuation are gone.
            body = EVIDENCE_MARKER_RE.sub("", sentence).strip()
            body = labels.SENTENCE_TAIL_RE.sub("", body)
            if body.strip():
                add(THIN_SEVERITY, "R-THIN",
                    f"a claim resting on thin evidence ({', '.join(hit)}) is stated as fact; "
                    "give it one of the seven confidence labels or a qualifier", f"line {i}")

    # 12. R3: a conflicting unit needs the other side cited too.
    for e in evidence:
        if e.get("corroboration") != "conflicting":
            continue
        eid = e.get("id")
        if eid not in body_ids:
            continue
        counterparts = set(e.get("corroborating_ids") or [])
        if counterparts and not (counterparts & body_ids):
            add(CONFLICT_PAIR_SEVERITY, "R-CONFLICT-PAIR",
                f"the body cites the conflicting evidence {eid} without citing any of the "
                f"other side ({', '.join(sorted(counterparts))})")

    # 13. R4: the disconfirmation section must not be empty.
    counter_heads = [i for i, line, _, in_code in rows
                     if not in_code and re.match(r"^#{1,4}\s+", line)
                     and section_matches(line, labels.section_keywords("COUNTER"))]
    for head in counter_heads:
        body_lines = []
        in_generated = False
        for i, line, _, in_code in rows:
            if i <= head:
                continue
            if not in_code and re.match(r"^#{1,4}\s+", line):
                break
            if GENERATED_BEGIN_RE.match(line):
                in_generated = True
                continue
            if GENERATED_END_RE.match(line):
                in_generated = False
                continue
            if in_generated:
                continue
            if is_substantive(line):
                body_lines.append(line)
        if not body_lines:
            add("FAIL", "R-COUNTER-EMPTY",
                "the disconfirmation section holds nothing the writer wrote (a table "
                "generated from the ledger does not satisfy it; state what the "
                "disconfirmation search means for the conclusion)",
                f"line {head}")

    # 14. R5: no point estimates, and a label carries its band.
    for i, line, section, in_code in rows:
        if in_code or section_matches(section, exempt):
            continue
        if POINT_ESTIMATE_RE.search(line) and not PROB_BAND_RE.search(line):
            add("FAIL", "R-POINT",
                "confidence is given as a point estimate (use one of the seven labels "
                "plus its band)", f"line {i}")
        if labels.contains_confidence(line) and not PROB_BAND_RE.search(line):
            add("WARN", "R-BAND", "a confidence label is given without its band", f"line {i}")

    # 15. R13: citation_check.json covers every unit, and its CRITICAL count.
    citation_summary = None
    if citation_check is not None:
        checked = {r.get("id") for r in citation_check.get("results", [])}
        missing = sorted(known_ids - checked,
                         key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
        if missing:
            add("FAIL", "R-CITECOMP",
                f"{len(missing)} evidence units have no result in citation_check.json: "
                f"{', '.join(missing[:10])}")
        crit = [r.get("id") for r in citation_check.get("results", [])
                if r.get("severity") == "CRITICAL"]
        if crit:
            add("FAIL", "R-CITECOMP",
                f"the citation check reports {len(crit)} CRITICAL: {', '.join(crit[:10])}")
        citation_summary = {"checked": len(checked), "missing": len(missing),
                            "critical": len(crit)}

    coverage = {
        "kq_total": len(kq_ids),
        "kq_mentioned": sum(1 for kq in kq_ids if re.search(rf"\b{kq}\b", report_text)),
        "evidence_total": len(known_ids),
        "evidence_used": len(body_ids & known_ids),
        "citation_check": citation_summary,
    }
    return findings, coverage


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="The deterministic audit of the research report (report.md)")
    parser.add_argument("report", help="path to report.md")
    parser.add_argument("--evidence", required=True, help="path to evidence_log.json")
    parser.add_argument("--citation", default=None,
                        help="path to citation_check.json (checks R13 completeness and CRITICAL)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()

    citation_check = None
    try:
        with open(args.report, encoding="utf-8") as f:
            report_text = f.read()
        with open(args.evidence, encoding="utf-8") as f:
            evidence_log = json.load(f)
        if args.citation:
            with open(args.citation, encoding="utf-8") as f:
                citation_check = json.load(f)
    except OSError as e:
        print(f"error: cannot read the file: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: not valid JSON: {e}", file=sys.stderr)
        return 2

    findings, coverage = audit(report_text, evidence_log, citation_check)
    fails = [f for f in findings if f["severity"] == "FAIL"]
    warns = [f for f in findings if f["severity"] == "WARN"]
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")

    result = {"verdict": verdict, "coverage": coverage,
              "fail_count": len(fails), "warn_count": len(warns), "findings": findings}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"verdict: {verdict} (KQ mentioned {coverage['kq_mentioned']}/{coverage['kq_total']} / "
              f"evidence used {coverage['evidence_used']}/{coverage['evidence_total']} / "
              f"FAIL {len(fails)} / WARN {len(warns)})")
        for f in findings:
            loc = f" @{f['location']}" if f.get("location") else ""
            print(f"  [{f['severity']}] {f['code']}{loc}: {f['message']}")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
