#!/usr/bin/env python3
"""report_check.py - check report.md and write sources.md (research-team 2.0).

Used in research-team Step 5 (the machine check before the report is delivered) and again
after the translation is written. Standard library only, no network. The sentence splitter and
the marker parser defined here are shared with select_claims.py.

Examples:
    python report_check.py --run-dir research/20261024-topic
    python report_check.py --run-dir research/20261024-topic --translation report.ja.md

Checks on report.md (one line per failure):
    1. the headings "## Answer", "## Findings", "## Disagreements and limits" exist
    2. every marker id exists in evidence.jsonl with status pass or warn
    3. every sentence with a digit in Answer and Findings carries a marker
    4. no sentence in verdicts.json "patch" remains verbatim (skipped without verdicts.json)
Then sources.md: the cited items, the uncited passing items, gaps.json and the search log.
--translation FILE compares FILE with report.md: marker sequence, multiset of numbers and the
count of lines starting with "#".

Exit codes: 0 = all checks pass / 1 = at least one failure / 2 = usage or I/O error
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

REQUIRED_HEADINGS = ["## Answer", "## Findings", "## Disagreements and limits"]
MARKER = r"\[E\d+(?:\s*,\s*E\d+)*\]"
MARKER_RE = re.compile(MARKER)
TRAIL_RE = re.compile(r"(?:\s*" + MARKER + r")+")
END_RE = re.compile(r"[.?!。](?=\s|$|\[E\d)")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
NUMBER_RE = re.compile(r"[0-9][0-9,.]*")
ABBREVIATIONS = {"vs", "e.g", "i.e", "etc", "approx", "cf", "al", "inc", "ltd", "co", "no", "fig",
                 "dr", "mr", "ms", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
                 "oct", "nov", "dec"}
INITIALS_RE = re.compile(r"^(?:[A-Za-z]\.)*[A-Z]$")  # U.S, J


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def is_abbreviation(text, i):
    """Does the period at text[i] close an abbreviation or an initial?"""
    if text[i] != ".":
        return False
    m = re.search(r"([A-Za-z][A-Za-z.]*)$", text[:i])
    word = m.group(1) if m else ""
    return word.lower() in ABBREVIATIONS or bool(INITIALS_RE.match(word))


def split_sentences(text):
    """Split on . ? ! and the ideographic full stop before whitespace, end or a marker.

    Markers that follow the stop stay with the sentence they close.
    """
    out, pos = [], 0
    for m in END_RE.finditer(text):
        if m.start() < pos or is_abbreviation(text, m.start()):
            continue
        end = m.end()
        trail = TRAIL_RE.match(text, end)
        if trail:
            end = trail.end()
        out.append(text[pos:end].strip())
        pos = end
    if text[pos:].strip():
        out.append(text[pos:].strip())
    return out


def report_sentences(text):
    """Yield (h2 heading or None, sentence) for every sentence outside the headings.

    A paragraph is a run of plain lines, a list item is one unit, so each list item is a
    sentence boundary.
    """
    section, buf = None, []

    def flush():
        if buf:
            unit = " ".join(s.strip() for s in buf)
            buf.clear()
            return [(section, s) for s in split_sentences(unit)]
        return []

    for line in text.splitlines():
        if line.startswith("#"):
            yield from flush()
            if line.startswith("## "):
                section = line.strip()
        elif not line.strip():
            yield from flush()
        elif ITEM_RE.match(line):
            yield from flush()
            buf.append(ITEM_RE.sub("", line, count=1))
        else:
            buf.append(line)
    yield from flush()


def marker_ids(text):
    return [i for m in MARKER_RE.findall(text) for i in re.findall(r"E\d+", m)]


def has_digit_outside_marker(sentence):
    # a digit glued to a preceding letter belongs to a name such as GPT-4 or H100
    return bool(re.search(r"(?<![A-Za-z\d])(?<![A-Za-z]-)\d", MARKER_RE.sub("", sentence)))


def numbers_of(text):
    """The numbers of a text outside markers: commas stripped, a trailing period removed."""
    return collections.Counter(n.replace(",", "").rstrip(".")
                               for n in NUMBER_RE.findall(MARKER_RE.sub("", text)))


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check_report(text, status_of, patch):
    failures = []
    lines = text.splitlines()
    for h in REQUIRED_HEADINGS:
        if h not in lines:
            failures.append(f"missing heading: {h}")
    for _, s in report_sentences(text):
        for i in marker_ids(s):
            if status_of.get(i) not in ("pass", "warn"):
                failures.append(f"dangling marker {i} in: {s[:100]}")
    for section, s in report_sentences(text):
        if section in ("## Answer", "## Findings") and has_digit_outside_marker(s) \
                and not MARKER_RE.search(s):
            failures.append(f"uncited number in {section[3:]}: {s[:100]}")
    flat = squash(text)
    for p in patch:
        if squash(p["sentence"]) in flat:
            failures.append(f"patched sentence {p['cid']} ({p['verdict']}) remains: "
                            f"{p['sentence'][:100]}")
    return failures


def check_translation(report, translation):
    failures = []
    a, b = marker_ids(report), marker_ids(translation)
    if a != b:
        failures.append(f"marker sequence differs: report {a} / translation {b}")
    na, nb = numbers_of(report), numbers_of(translation)
    if na != nb:
        only_a, only_b = sorted((na - nb).elements()), sorted((nb - na).elements())
        failures.append(f"numbers differ: only in report {only_a} / only in translation {only_b}")
    ha = sum(1 for l in report.splitlines() if l.startswith("#"))
    hb = sum(1 for l in translation.splitlines() if l.startswith("#"))
    if ha != hb:
        failures.append(f"heading count differs: report {ha} / translation {hb}")
    return failures


def cell(v):
    return str(v).replace("|", "/").replace("\n", " ")


def write_sources(run_dir, evidence, cited, gaps):
    by_id = {e["id"]: e for e in evidence}
    rows = ["| id | publisher | title | date | grade | url | check |", "|---|---|---|---|---|---|---|"]
    for i in sorted(cited, key=lambda x: int(x[1:])):
        e = by_id.get(i)
        if e:
            rows.append("| " + " | ".join(cell(x) for x in (
                i, e["publisher"], e["title"], e["date"], e["grade"], e["url"],
                e["check"]["status"])) + " |")
    uncited = [e for e in evidence if e["id"] not in cited and e["check"]["status"] != "fail"]
    out = ["# Sources", "", "## Cited", "", *rows, "", "## Uncited passing items", ""]
    out += [f"- {e['id']}: {e['publisher']}, {e['title']}, {e['url']}" for e in uncited] or ["- none"]
    out += ["", "## Gaps", "", "```json", json.dumps(gaps, ensure_ascii=False, indent=2), "```", "",
            "## Search log", ""]
    for path in sorted(glob.glob(os.path.join(run_dir, "collect", "searches_SQ*_*.jsonl"))):
        name = os.path.basename(path)[len("searches_"):-len(".jsonl")]
        out += [f"### {name}", "", "| query | purpose | results | new sources |", "|---|---|---|---|"]
        out += ["| " + " | ".join(cell(r.get(k, "")) for k in
                                  ("query", "purpose", "results", "new_sources")) + " |"
                for r in read_jsonl(path)]
        out.append("")
    with open(os.path.join(run_dir, "sources.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def main():
    _configure_stdout()
    ap = argparse.ArgumentParser(description="Check report.md and write sources.md.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--translation", metavar="FILE", help="compare FILE with report.md")
    args = ap.parse_args()
    try:
        with open(os.path.join(args.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        evidence = read_jsonl(os.path.join(args.run_dir, "evidence.jsonl"))
        gaps = {"empty_sq": [], "failed": []}
        if os.path.exists(os.path.join(args.run_dir, "gaps.json")):
            with open(os.path.join(args.run_dir, "gaps.json"), encoding="utf-8") as f:
                gaps = json.load(f)
        patch = []
        vpath = os.path.join(args.run_dir, "verdicts.json")
        if os.path.exists(vpath):
            with open(vpath, encoding="utf-8") as f:
                patch = json.load(f).get("patch", [])
        translation = None
        if args.translation:
            tpath = args.translation if os.path.isabs(args.translation) \
                else os.path.join(args.run_dir, args.translation)
            with open(tpath, encoding="utf-8") as f:
                translation = f.read()
        status_of = {e["id"]: e["check"]["status"] for e in evidence}
        failures = check_report(report, status_of, patch)
        if translation is not None:
            failures += check_translation(report, translation)
        cited = set(marker_ids(report))
        write_sources(args.run_dir, evidence, cited, gaps)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in failures:
        print(line)
    print(f"{len(failures)} failures; {len(cited)} cited ids, {len(evidence)} evidence items; "
          "sources.md written")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
