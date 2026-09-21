#!/usr/bin/env python3
"""research_plan_linter.py — check the research plan (research_brief.md) for its required parts.

Run it in research-team Step 1. Standard library only.

Examples:
    python research_plan_linter.py research_brief.md --mode DEEP
    python research_plan_linter.py research_brief.md --json

Exit codes: 0 = PASS or WARN only / 1 = at least one FAIL / 2 = usage or I/O error
"""

import argparse
import json
import math
import os
import re
import sys

import select_verification_targets as svt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels

VALID_MODES = ("LIGHT", "STANDARD", "DEEP")

REQUIRED_SECTIONS = labels.BRIEF_SECTIONS

# Competing hypotheses are required in DEEP only, so they are handled separately.
HYPOTHESIS_SECTION = labels.HYPOTHESIS_SECTION

# Queries per KQ, per role (the floors of collection_standards.md §1).
QUERIES_PER_ROLE = {"DEEP": 12, "STANDARD": 6, "LIGHT": 0}
# Disconfirmation queries in the verification stage: two per claim (research-verifier
# step 4). The number of claims follows select_verification_targets.py's cap (batches ×
# BATCH_SIZE claims per batch) alone; it is independent of the number of KQs.
COUNTER_QUERIES_PER_CLAIM = 2
# Academic API calls do not consume the WebSearch cap, so the scholar estimate is scaled.
SCHOLAR_API_FACTOR = 0.4
DEFAULT_SEARCH_LIMIT = 200
ROLE_ASSIGN_RE = re.compile(r"KQ(\d+)\s*[=:]\s*")
ROLE_ASSIGN_LABEL_RE = re.compile(r"role assignment", re.IGNORECASE)
VALID_ROLES = ("collector", "scholar")

# Decision relevance (collection_standards.md §1). In DEEP every KQ line ends in
# [decision] or [background].
RELEVANCE_RE = labels.RELEVANCE_RE
MAX_DECISION_KQS = 4
# The mode whose floors a background KQ gets.
BACKGROUND_MODE = "STANDARD"

# Tool calls per KQ per role (the median of the budget in collection_standards.md §2).
TOOL_CALLS_PER_ROLE = {"DEEP": 24, "STANDARD": 13, "LIGHT": 6}
# The verification estimate: the batch cap (select_verification_targets.py's
# MAX_BATCHES) and the calls one batch makes.
VERIFY_BATCHES = dict(svt.MAX_BATCHES, LIGHT=0)
VERIFY_CLAIMS_PER_BATCH = svt.BATCH_SIZE
TOOL_CALLS_PER_VERIFY_BATCH = 12
# The audit stage: one agent, ten calls.
AUDITOR_AGENTS = {"DEEP": 1, "STANDARD": 1, "LIGHT": 0}
TOOL_CALLS_PER_AUDITOR = 10
# The cap for one study (DEEP). A plan above it is cut back.
MAX_AGENTS = {"DEEP": 18, "STANDARD": 12}
MAX_TOOL_CALLS = {"DEEP": 300, "STANDARD": 180}

# The rival analyst (research-rival.md): one agent, launched whenever the question type is
# anything but descriptive — including where the type cannot be read, which is costed as
# needing one so the estimate errs high when the type is unclear.
TOOL_CALLS_PER_RIVAL = 4

# The five required fields of the Question analysis section (labels.QA_FIELDS), and the
# rules that check its presuppositions and decision line.
PRESUP_HEAD_RE = re.compile(r"^-\s*presuppositions\b", re.IGNORECASE)
PRESUP_VERIFY_RE = re.compile(r"\bverify\b", re.IGNORECASE)
PRESUP_ACCEPT_RE = re.compile(r"\baccept\b", re.IGNORECASE)
PRESUP_KQ_REF_RE = re.compile(r"KQ\d+", re.IGNORECASE)
PRESUP_NONE_RE = re.compile(r"^none identified$", re.IGNORECASE)
DECISION_LINE_RE = re.compile(r"^-\s*Decision\s*:\s*(.*)$", re.IGNORECASE)
MIN_DECISION_CHARS = 15


def web_search_limit():
    """The WebSearch cap, from the environment (the default when it is unset)."""
    raw = os.environ.get("CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SEARCH_LIMIT
    return value if value > 0 else DEFAULT_SEARCH_LIMIT


def parse_role_assignment(source_plan_body):
    """{KQ number: [role, …]} from the source plan's role-assignment line, {} if unreadable."""
    if not source_plan_body:
        return {}
    line = next((ln for ln in source_plan_body.splitlines()
                 if ROLE_ASSIGN_LABEL_RE.search(ln)), None)
    if line is None:
        return {}
    assignment = {}
    matches = list(ROLE_ASSIGN_RE.finditer(line))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        roles_text = line[m.end():end].lower()
        roles = [r for r in VALID_ROLES if r in roles_text]
        if roles:
            assignment[m.group(1)] = roles
    return assignment


def effective_mode(mode, relevance):
    """The mode whose floors this KQ gets. A background KQ in DEEP gets STANDARD's."""
    return BACKGROUND_MODE if (mode == "DEEP" and relevance == "background") else mode


def roles_of(assignment, kq_num):
    """This KQ's collection roles. Where they cannot be read, assume both."""
    return assignment.get(str(kq_num)) or list(VALID_ROLES)


def estimate_search_queries(mode, n_kq, assignment, relevance=None):
    """Estimate the total WebSearch calls. Returns (estimate, breakdown)."""
    relevance = relevance or {}

    def per_role_for(kq_num):
        return QUERIES_PER_ROLE.get(effective_mode(mode, relevance.get(str(kq_num))), 0)

    collection = 0.0
    for i in range(1, n_kq + 1):
        for role in roles_of(assignment, i):
            collection += per_role_for(i) * (SCHOLAR_API_FACTOR if role == "scholar" else 1.0)

    # The verification stage scales with the number of claims verified alone, and that
    # number is capped by the batch cap — so one more KQ adds no verification searches.
    verification = (VERIFY_BATCHES.get(mode, 0) * VERIFY_CLAIMS_PER_BATCH
                    * COUNTER_QUERIES_PER_CLAIM)
    total = math.ceil(collection) + verification
    return total, {"collection": math.ceil(collection), "verification": verification}


def estimate_cost(mode, n_kq, assignment, relevance=None, question_type=None):
    """Estimate the subagent count and the total tool calls. Returns (agents, calls, breakdown).

    question_type adds the rival analyst's cost (one agent, TOOL_CALLS_PER_RIVAL calls)
    whenever it is anything but "descriptive", including when it is None.
    """
    relevance = relevance or {}
    collect_agents = 0
    collect_calls = 0
    for i in range(1, n_kq + 1):
        for _role in roles_of(assignment, i):
            collect_agents += 1
            collect_calls += TOOL_CALLS_PER_ROLE.get(
                effective_mode(mode, relevance.get(str(i))), 0)

    verify_agents = VERIFY_BATCHES.get(mode, 0)
    verify_calls = verify_agents * TOOL_CALLS_PER_VERIFY_BATCH
    audit_agents = AUDITOR_AGENTS.get(mode, 0)
    audit_calls = audit_agents * TOOL_CALLS_PER_AUDITOR
    rival_agents = 0 if question_type == "descriptive" else 1
    rival_calls = 0 if question_type == "descriptive" else TOOL_CALLS_PER_RIVAL

    agents = collect_agents + verify_agents + audit_agents + rival_agents
    calls = collect_calls + verify_calls + audit_calls + rival_calls
    return agents, calls, {
        "collection_agents": collect_agents, "collection_calls": collect_calls,
        "verification_agents": verify_agents, "verification_calls": verify_calls,
        "audit_agents": audit_agents, "audit_calls": audit_calls,
        "rival_agents": rival_agents, "rival_calls": rival_calls,
    }


def qa_presupposition_lines(body):
    """The sub-bullets under 'Presuppositions:' in a Question analysis section's body."""
    lines = []
    in_presup = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        indented = raw[:1].isspace()
        if not indented and PRESUP_HEAD_RE.match(stripped):
            in_presup = True
            continue
        if not indented and stripped.startswith("-"):
            in_presup = False
            continue
        if in_presup and stripped.startswith("-"):
            lines.append(stripped[1:].strip())
    return lines


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def split_sections(text):
    """Split on the headings (# to ###) and return {heading: body}."""
    sections = {}
    current = "_preamble"
    buf = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if m:
            sections[current] = "\n".join(buf)
            current = m.group(1)
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf)
    return sections


def find_section(sections, keywords):
    for heading, body in sections.items():
        low = heading.lower()
        if any(k.lower() in low for k in keywords):
            return heading, body
    return None, None


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def lint(text, mode):
    findings = []  # {severity, code, message}

    def add(severity, code, message):
        findings.append({"severity": severity, "code": code, "message": message})

    text_nc = strip_comments(text)
    sections = split_sections(text_nc)

    # The mode declaration (the placeholder {LIGHT | STANDARD | DEEP} counts as unfilled).
    declared_mode = None
    m_line = re.search(r"mode\s*:\s*([^\n]*)", text_nc, re.IGNORECASE)
    if m_line and "{" not in m_line.group(1):
        m = re.match(r"\s*(LIGHT|STANDARD|DEEP)\b", m_line.group(1))
        declared_mode = m.group(1) if m else None
    if mode is None:
        mode = declared_mode
    if declared_mode is None:
        add("FAIL", "P-MODE", "no mode is declared (Mode: LIGHT|STANDARD|DEEP)")
    if mode is None:
        mode = "STANDARD"
        add("WARN", "P-MODE-DEFAULT", "the mode is unknown, so it was linted as STANDARD")

    # The as-of date.
    if not re.search(r"as_of[^\n]*\d{4}-\d{2}-\d{2}", text_nc):
        add("FAIL", "P-ASOF", "no as-of date (as_of: YYYY-MM-DD)")

    # The required sections.
    for code, keywords in REQUIRED_SECTIONS.items():
        heading, body = find_section(sections, keywords)
        if heading is None:
            add("FAIL", f"P-SEC-{code.upper()}", f"the required section \"{keywords[0]}\" is missing")
        elif not body.strip():
            add("FAIL", f"P-EMPTY-{code.upper()}", f"the section \"{heading}\" is empty")

    # The Question analysis section's five fields, its question type, its presuppositions
    # and its Decision line. Presence and emptiness are already checked above; these rules
    # run only where the section exists and carries text.
    _, qa_body = find_section(sections, REQUIRED_SECTIONS["question_analysis"])
    question_type = None
    if qa_body and qa_body.strip():
        missing_fields = [f for f in labels.QA_FIELDS if f.lower() not in qa_body.lower()]
        if missing_fields:
            add("FAIL", "P-QA-FIELDS",
                f"the Question analysis section is missing: {', '.join(missing_fields)}")
        question_type = labels.question_type_of(qa_body)
        if question_type is None:
            add("FAIL", "P-QA-TYPE",
                "the Question analysis section names no valid question type "
                f"(one of {', '.join(labels.QUESTION_TYPES)})")
        for presup in qa_presupposition_lines(qa_body):
            if PRESUP_NONE_RE.match(presup):
                continue
            has_verify = bool(PRESUP_VERIFY_RE.search(presup))
            has_accept = bool(PRESUP_ACCEPT_RE.search(presup))
            if not has_verify and not has_accept:
                add("WARN", "P-QA-PRESUP",
                    f"a presupposition names neither verify nor accept: {presup[:60]}")
            elif has_verify and not PRESUP_KQ_REF_RE.search(presup):
                add("WARN", "P-QA-PRESUP",
                    f"a presupposition marked verify names no KQ: {presup[:60]}")
        decision_line = next((m for m in (DECISION_LINE_RE.match(ln.strip())
                                          for ln in qa_body.splitlines()) if m), None)
        if decision_line and len(decision_line.group(1).strip()) < MIN_DECISION_CHARS:
            add("WARN", "P-QA-DECISION",
                "the Decision line is too short to name who does what differently and by "
                f"when ({len(decision_line.group(1).strip())} characters after the colon)")

    # The key questions, taken from that section's body alone: another section quoting a
    # KQ line would otherwise read as a duplicate.
    _, kq_body = find_section(sections, REQUIRED_SECTIONS["key_questions"])
    kqs = re.findall(r"KQ(\d+)\s*:\s*(.+)", kq_body if kq_body is not None else text_nc)
    if not (2 <= len(kqs) <= 7):
        add("FAIL", "P-KQ-COUNT", f"between 2 and 7 key questions are required ({len(kqs)} found)")
    seen = set()
    relevance = {}
    for num, kq_text in kqs:
        if num in seen:
            add("FAIL", "P-KQ-DUP", f"KQ{num} appears twice")
        seen.add(num)
        rel = RELEVANCE_RE.search(kq_text)
        if rel:
            relevance[num] = labels.relevance_of(rel)
        stripped = RELEVANCE_RE.sub("", kq_text).strip().rstrip("}").rstrip()
        if not stripped.endswith("?"):
            add("WARN", "P-KQ-FORM", f"KQ{num} is not written as a question: {stripped[:40]}")

    # Decision relevance (required in DEEP; collection_standards.md §1).
    if mode == "DEEP" and kqs:
        missing = [f"KQ{num}" for num, _ in kqs if num not in relevance]
        if missing:
            add("FAIL", "P-KQ-RELEVANCE",
                "DEEP requires a decision relevance [decision] / [background] on every KQ "
                f"(missing on {', '.join(missing)}; an unmarked KQ counts as a decision KQ, "
                "so its floors do not drop)")
        n_decision = sum(1 for num, _ in kqs if relevance.get(num, "decision") == "decision")
        if n_decision > MAX_DECISION_KQS:
            add("FAIL", "P-KQ-DECISION-MAX",
                f"at most {MAX_DECISION_KQS} decision KQs are allowed ({n_decision} found); "
                "mark the ones that do not drive the conclusion [background]")

    # Competing hypotheses (two or more required in DEEP).
    hyps = re.findall(r"H(\d+)\s*:\s*(\S.*)", text_nc)
    if mode == "DEEP" and len(hyps) < 2:
        add("FAIL", "P-HYP",
            f"DEEP requires two or more mutually conflicting hypotheses ({len(hyps)} found)")

    # The disconfirmation plan's substance (a row per hypothesis).
    _, disc_body = find_section(sections, REQUIRED_SECTIONS["disconfirmation_plan"])
    if disc_body is not None and hyps:
        for num, _ in hyps:
            if not re.search(rf"\bH{num}\b", disc_body):
                add("WARN", "P-DISC-HYP", f"the disconfirmation plan has no row for H{num}")

    # The role assignment: a required part of the source plan, naming the collection
    # role each KQ gets.
    _, source_body = find_section(sections, REQUIRED_SECTIONS["source_plan"])
    assignment = parse_role_assignment(source_body)
    if source_body is None or not ROLE_ASSIGN_LABEL_RE.search(source_body):
        add("FAIL", "P-SEC-ROLE_ASSIGNMENT",
            "the source plan is missing the required \"Role assignment\" line "
            "(which of collector / scholar each KQ gets)")
    elif not assignment:
        add("WARN", "P-ROLE-UNREADABLE",
            "the role assignment cannot be read per KQ (the search budget was estimated "
            "assuming both roles)")

    # The search budget (the WebSearch cap; collection_standards.md §1).
    if mode in ("STANDARD", "DEEP"):
        limit = web_search_limit()
        estimate, breakdown = estimate_search_queries(mode, len(kqs), assignment, relevance)
        detail = (f"an estimated {estimate} calls (collection {breakdown['collection']} + "
                  f"verification {breakdown['verification']}) against a cap of {limit}")
        if estimate > limit:
            add("FAIL", "P-BUDGET",
                detail + " — over the cap. Raise CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION, or "
                "revisit the number of KQs and the role assignment (the cap counts the whole "
                "session, so splitting the work across turns does not reset it)")
        else:
            add("INFO", "P-BUDGET", detail + " — within it")

    # The agent and tool-call budget. A plan above it is cut back (fewer KQs, or a
    # decision KQ moved to background).
    if mode in MAX_AGENTS:
        agents, calls, cost = estimate_cost(mode, len(kqs), assignment, relevance, question_type)
        max_agents, max_calls = MAX_AGENTS[mode], MAX_TOOL_CALLS[mode]
        detail = (f"an estimated {agents} agents and {calls} calls "
                  f"(collection {cost['collection_agents']} agents {cost['collection_calls']} calls + "
                  f"verification {cost['verification_agents']} agents {cost['verification_calls']} calls + "
                  f"audit {cost['audit_agents']} agents {cost['audit_calls']} calls + "
                  f"rival {cost['rival_agents']} agents {cost['rival_calls']} calls) "
                  f"against a cap of {max_agents} agents and {max_calls} calls")
        if agents > max_agents or calls > max_calls:
            add("FAIL", "P-COST",
                detail + " — over the cap. Cut the number of KQs, or move a decision KQ to "
                "background (record what you did in the stopping rules)")
        else:
            add("INFO", "P-COST", detail + " — within it")

    # Placeholders left unfilled from the template.
    placeholders = re.findall(r"\{[^{}\n]{1,40}\}", text_nc)
    if placeholders:
        add("WARN", "P-PLACEHOLDER",
            f"{len(placeholders)} template placeholders are still unfilled "
            f"(the first is {placeholders[0]})")

    return findings, mode


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Check the research plan (research_brief.md) for its required parts")
    parser.add_argument("brief", help="path to research_brief.md")
    parser.add_argument("--mode", choices=VALID_MODES, default=None,
                        help="state the mode (otherwise the declaration in the document is used)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()

    try:
        with open(args.brief, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"error: cannot read the file: {e}", file=sys.stderr)
        return 2

    findings, mode = lint(text, args.mode)
    fails = [f for f in findings if f["severity"] == "FAIL"]
    warns = [f for f in findings if f["severity"] == "WARN"]
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")

    result = {"verdict": verdict, "mode": mode,
              "fail_count": len(fails), "warn_count": len(warns), "findings": findings}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"verdict: {verdict} (mode: {mode} / FAIL {len(fails)} / WARN {len(warns)})")
        for f in findings:
            print(f"  [{f['severity']}] {f['code']}: {f['message']}")
        if verdict == "PASS":
            print("  Every required part is present. Step 2 (parallel collection) may start.")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
