#!/usr/bin/env python3
"""labels.py — the section names, the confidence vocabulary and the prose patterns.

Every string the check scripts match a deliverable against, and every string
render_scaffold.py writes into one, lives here rather than in each script. One
definition serves both sides, so a heading the generator writes is by construction a
heading the auditor accepts.

The structure of a deliverable is English: its section names, its table headers, its
confidence labels. The prose inside it — the claims, the conclusions, the report body —
is written in the language of the request, which the ledger records as
`deliverable_language`. Keeping the structure fixed is what lets one set of patterns
audit a report whatever language it was requested in.
"""
import re

# ------------------------------------------------------------------ sections

# report.md. code -> heading keywords; a heading matches on a case-insensitive substring.
REPORT_SECTIONS = [
    ("DECISION",  ("answer to the decision", "decision answer")),
    ("SUMMARY",   ("summary", "conclusion")),
    ("COUNTER",   ("disconfirmation", "conflicting", "counter-evidence")),
    ("LIMITS",    ("limitations", "gaps")),
    ("COVERAGE",  ("coverage",)),
    ("SEARCHLOG", ("search log",)),
    ("SOURCES",   ("sources", "references")),
]

# research_brief.md. code -> heading keywords.
BRIEF_SECTIONS = {
    "purpose":              ("purpose",),
    "key_questions":        ("key questions",),
    "disconfirmation_plan": ("disconfirmation plan",),
    "source_plan":          ("source plan",),
    "stop_rule":            ("stopping rules",),
    "out_of_scope":         ("out of scope",),
}

HYPOTHESIS_SECTION = ("competing hypotheses",)


def section_keywords(code):
    """One report section's heading keywords."""
    for c, keywords in REPORT_SECTIONS:
        if c == code:
            return keywords
    raise KeyError(code)


def section_of(code):
    """One report section's canonical heading keyword — for generating text."""
    return section_keywords(code)[0]


# --------------------------------------------------- decision relevance tags

# DEEP appends the decision relevance to the end of each key-question line.
RELEVANCE_TAGS = {"decision": "decision", "background": "background"}

RELEVANCE_RE = re.compile(
    r"\[\s*(%s)\s*\]" % "|".join(RELEVANCE_TAGS.values()), re.IGNORECASE)


def relevance_of(match):
    """decision / background from a RELEVANCE_RE match."""
    return match.group(1).lower()


# ------------------------------------------------------- confidence vocabulary

# The seven estimative labels and their probability bands, strongest first. The wording
# is the US ODNI ICD 203 estimative language (interpretation_contract.md §5).
CONFIDENCE = [
    ("almost certain",      (90, 100)),
    ("very likely",         (80, 90)),
    ("likely",              (65, 80)),
    ("roughly even chance", (45, 65)),
    ("unlikely",            (20, 45)),
    ("very unlikely",       (10, 20)),
    ("almost no chance",    (0, 10)),
]

CONFIDENCE_LABELS = tuple(row[0] for row in CONFIDENCE)
# The three labels at or above "likely", used for the early-stop condition.
EARLY_STOP_CONFIDENCE = CONFIDENCE_LABELS[:3]


def confidence_label(rank):
    """The estimative label at one rank (0 = strongest)."""
    return CONFIDENCE[rank][0]


def confidence_band(rank):
    """That rank's probability band."""
    low, high = CONFIDENCE[rank][1]
    return "%d-%d%%" % (low, high)


def contains_confidence(text):
    """Does the text carry one of the estimative labels?"""
    low = text.lower()
    return any(lb in low for lb in CONFIDENCE_LABELS)


# ------------------------------------------------------------ prose patterns

# Vague estimation the confidence vocabulary is meant to replace.
AMBIGUOUS_PATTERNS = (
    "maybe", "perhaps", "presumably", "arguably", "possibly",
    "it seems", "seems to be", "it would appear", "one would think",
)

# R14 qualifiers. A claim on thin evidence carrying one of these is not an assertion.
HEDGE_PATTERNS = (
    "single_source", "single source", "reportedly", "is said to", "claims to",
    "self-reported", "provisional", "estimated", "according to", "appears to",
    "suggests", "as far as", "within the limits of", "on this evidence",
)

# A probability band: 65-80% / 65% to 80%.
PROB_BAND_RE = re.compile(r"\d+\s*[%]?\s*(?:[-–—]|to)\s*\d+\s*[%]")

# A point estimate, which the seven-label vocabulary plus a band replaces.
POINT_ESTIMATE_RE = re.compile(
    r"(?:confidence|certainty|probability)\s*(?:is|of|at|=|:)?\s*\d+\s*%"
    r"|\d+\s*%\s*(?:confidence|certainty|probability|likely|certain)",
    re.IGNORECASE)

# A figure that needs a citation.
NUMERIC_ASSERTION_RE = re.compile(
    r"\d[\d,.]*\s*(?:%|percent|billion|million|trillion|bn|pts?|points?"
    r"|people|companies|cases|times|users|employees|years)"
    r"|[$€£¥]\s*\d",
    re.IGNORECASE)

# Sentence separators.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(?=\s)")

# Trailing punctuation stripped before looking at how a sentence ends.
SENTENCE_TAIL_RE = re.compile(r"[.!?\s)\]\"']+$")


# ------------------------------------------------------------ generated text

# What render_scaffold.py writes into report.md and the per-KQ slices.
TEXT = {
    "placeholder":
        "<!-- Write here. Take every fact from the slices under kq_slices/, re-read. -->",
    "decision_placeholder":
        ("<!-- Answer the decision that was asked for.\n"
         "     Line 1 the answer, line 2 the recommendation, line 3 the confidence\n"
         "     (one of the seven labels plus its band), line 4 what would overturn\n"
         "     this judgement. Mark every fact with [E#]. -->"),

    # confidence-ceiling reasons
    "ceil_conflict": "the sources conflict",
    "ceil_two_a": "two or more independent grade-A sources",
    "ceil_two_clusters": "two or more independent sources, but fewer than two of them grade A",
    "ceil_single_a": "a single grade-A source",
    "ceil_single_b": "a single grade-B source",
    "ceil_c_only": "grade-C sources only",
    "ceil_none": "no evidence",
    "ceil_capped": ", but with no confirmed evidence the ceiling drops to \"%s\"",
    "ceil_line": "- Confidence ceiling (computed): %s — %s. The writer picks the final label.",

    # tables
    "tbl_evidence": "| Evidence | Claim | Grade | Corroboration | Verification |",
    "tbl_evidence_empty": "| — | (no live evidence attached to this KQ) | — | — | — |",
    "tbl_disconf":
        "| Hypothesis | Observable if false | Queries run | Result | Effect on the hypothesis |",
    "tbl_disconf_empty": "| — | — | — | (the ledger's disconfirmation is empty) | — |",
    "tbl_coverage": "| KQ | Conclusion | Confidence | Key evidence | Verification |",
    "coverage_conclusion": "{one line}",
    "coverage_label": "{label}",
    "tbl_searchlog": "| Query | Tool | Adopted | Kind | KQ |",
    "tbl_gaps": "| Claim left uncorroborated | Queries tried | Further research suggested |",
    "tbl_gaps_empty": "| (the ledger's gaps is empty) | — | — |",
    "tbl_earlystop":
        "| KQ | Role | Independent sources | Consecutive zero-new | Confidence | Note |",
    "tbl_earlystop_empty": "| (no early stop) | — | — | — | — | — |",
    "queries_unit": "queries",
    "grade_prefix": "grade ",

    # report header and sections
    "report_title": "# %s — research report",
    "hdr_meta": "- as_of: %s / mode: %s",
    "hdr_counts": "- Independent sources: %s / evidence units: %s",
    "hdr_excluded": " (excluding %s refuted or superseded)",
    "hdr_verified": " / confirmed claims: %s",
    "hdr_breakdown": "- Verification breakdown: ",
    "hdr_sep": " / ",
    "hdr_overall": "- Overall confidence: {one of the seven labels} ({band})",
    "sec_decision": "## Answer to the decision",
    "sec_summary": "## Summary",
    "sec_kq": "## Conclusions per key question",
    "sec_counter": "## Disconfirmation and conflicting evidence",
    "sec_insight": "## Insight and implications",
    "sec_limits": "## Limitations and evidence gaps",
    "sec_coverage": "## KQ coverage",
    "sec_searchlog": "## Search log",
    "sec_sources": "## Sources",

    # per-KQ slices
    "slice_count": ("%d evidence units (this KQ's share of evidence_log.json; "
                    "equivalent to reading the ledger directly)"),
    "slice_key_figure": " (key figure)",
    "slice_claim": "- Claim: %s",
    "slice_quote": "- Quote: \"%s\"",
    "slice_source": "- Source: %s",
    "slice_corroboration": "- Corroboration: %s",
    "slice_verification": "- Verification: %s",
    "slice_disc_head": "## Disconfirmation recorded while collecting for this KQ",
    "slice_disc_item": "- Hypothesis \"%s\": %s",
    "cross_title": "# Cross-cutting (evidence belonging to no key question)",
    "cross_count": "%d evidence units",
    "cross_none": "There is none. The per-KQ slices hold all the material.",
}


def T(key):
    """One piece of generated text."""
    return TEXT[key]
