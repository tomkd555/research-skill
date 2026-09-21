#!/usr/bin/env python3
"""evidence_auditor.py — the deterministic audit of the evidence ledger (evidence_log.json).

Run it in research-team Step 5. It checks the structure (schema, URLs, grades, the
consistency of the cross-references) and the quality (the collection floors, freshness,
the disconfirmation record). Standard library only.

Examples:
    python evidence_auditor.py evidence_log.json
    python evidence_auditor.py evidence_log.json --mode DEEP --json
    python evidence_auditor.py --sample > evidence_log.json

Exit codes: 0 = PASS or WARN only / 1 = at least one FAIL / 2 = usage or I/O error
"""

import argparse
import datetime
import json
import re
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels

try:
    from triage_sources import registrable_domain
except ImportError:
    def registrable_domain(url):
        """Fallback: the last two labels of the host (www. dropped)."""
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        labels_ = host.split(".")
        return ".".join(labels_[-2:]) if len(labels_) >= 2 else host

SCHEMA_MAJOR = 1
SCHEMA_MINOR = 4  # 1.4 added source.local_path and source.user_supplied (local materials)

FLOORS = {
    "DEEP": {"queries": 12, "independent_sources": 5, "counter_queries": 2},
    "STANDARD": {"queries": 6, "independent_sources": 3, "counter_queries": 1},
    "LIGHT": {"queries": 0, "independent_sources": 1, "counter_queries": 0},
}

# A background KQ in DEEP gets STANDARD's floors (collection_standards.md §1). A KQ with
# no relevance recorded counts as a decision KQ, so leaving it out cannot lower a floor.
BACKGROUND_FLOOR_MODE = "STANDARD"
VALID_RELEVANCE = ("decision", "background")

# The three early-stop conditions (collection_standards.md §1). A shortfall drops from
# FAIL to WARN only for a group whose record meets all three and which still clears
# STANDARD's floors.
BASE_FLOOR_MODE = "STANDARD"
EARLY_STOP_MIN_SOURCES = 3
EARLY_STOP_MIN_ZERO_STREAK = 2
EARLY_STOP_CONFIDENCE = labels.EARLY_STOP_CONFIDENCE

# STANDARD judges a key question's floors on the total across roles. A minimum share per
# launched role stops one role passing on zero queries (collection_standards.md §1).
MIN_ROLE_ALLOCATION = {"queries": 3, "counter_queries": 1}
ROLES = ("collector", "scholar")

VALID_GRADES = {"A", "B", "C"}
VALID_CLAIM_TYPES = {"fact", "estimate", "opinion"}
VALID_CORROBORATION = {"corroborated", "single_source", "conflicting"}
VALID_VERIFICATION = {"confirmed", "plausible", "disputed", "refuted", "unchecked"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PUBLISHED_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
URL_RE = re.compile(r"^(https?|file)://\S+$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")

VALID_LINEAGE_COLLECTORS = {"collector", "scholar", "lead"}


def enum_ok(value, valid):
    """True when value is a member of the enum valid. A dict or any other unhashable
    value stays safe here too: it counts as a wrong value with no exception raised."""
    return isinstance(value, str) and value in valid


def has_external_corroboration(e, src):
    """True when verification.corroborating_source names a source outside this unit's
    own domain: a verifier's own find, carrying no corroborating_ids entry from the
    merge, that still stands as an independent corroboration (collection_standards.md
    §1)."""
    ver = e.get("verification")
    corr_src = ver.get("corroborating_source") if isinstance(ver, dict) else None
    if not isinstance(corr_src, dict):
        return False
    other_url = corr_src.get("url")
    if not isinstance(other_url, str) or not other_url:
        return False
    own_domain = registrable_domain(src.get("url") or "")
    other_domain = registrable_domain(other_url)
    return bool(other_domain) and other_domain != own_domain


SELF_REPORTED_MARKER = "self-reported"
USER_SUPPLIED_MARKER = "user-supplied"

SAMPLE = {
    "schema": "research-evidence-1.3",
    "topic": "{the research topic}",
    "as_of": "2026-07-03",
    "mode": "STANDARD",
    "key_questions": [
        {"id": "KQ1", "text": "{the first key question, as a question}"},
    ],
    "evidence": [
        {
            "id": "E1",
            "kq_ids": ["KQ1"],
            "claim": "{one falsifiable proposition, in the third person}",
            "claim_type": "estimate",
            "verbatim_quote": "{a verbatim passage from the source, up to about 40 words}",
            "source": {
                "publisher": "{publisher}",
                "title": "{title}",
                "url": "https://example.com/a",
                "published": "2026-04",
                "grade": "B",
                "origin_cluster": "src-a",
            },
            "accessed": "2026-07-03",
            "is_key_figure": True,
            "corroboration": "corroborated",
            "corroborating_ids": ["E2"],
            "self_reported": False,
            "lineage": {"collected_by": "collector", "kq_id": "KQ1",
                        "fragment_file": "evidence_fragments/kq1_collector.json"},
            "verification": {"status": "confirmed",
                             "method": "citation existence plus two independent sources"},
        },
        {
            "id": "E2",
            "kq_ids": ["KQ1"],
            "claim": "{a second proposition, from an independent source}",
            "claim_type": "estimate",
            "verbatim_quote": "{a verbatim passage from that source}",
            "source": {
                "publisher": "{publisher}",
                "title": "{title}",
                "url": "https://example.org/b",
                "published": "2026-02",
                "grade": "B",
                "origin_cluster": "src-b",
            },
            "accessed": "2026-07-03",
            "is_key_figure": True,
            "corroboration": "corroborated",
            "corroborating_ids": ["E1"],
            "verification": {"status": "confirmed"},
        },
        {
            "id": "E3",
            "kq_ids": ["KQ1"],
            "claim": "{a proposition resting on one source alone}",
            "claim_type": "fact",
            "verbatim_quote": "{a verbatim passage from that source}",
            "source": {
                "publisher": "{publisher}",
                "title": "{title}",
                "url": "https://example.net/c",
                "published": "2026-05",
                "grade": "B",
                "origin_cluster": "src-c",
            },
            "accessed": "2026-07-03",
            "is_key_figure": False,
            "corroboration": "single_source",
            "corroborating_ids": [],
            "verification": {"status": "plausible"},
        },
    ],
    "disconfirmation": [
        {
            "hypothesis": "H1: {the hypothesis}",
            "expected_if_false": "{what would be observed if H1 were false}",
            "queries": ["{disconfirming query 1}", "{disconfirming query 2}"],
            "found": "{what the disconfirming search returned, or that it returned nothing}",
            "impact": "{what that does to the hypothesis}",
        }
    ],
    "search_log": [
        {"query": "{query %d}" % i, "tool": "WebSearch",
         "kind": "counter" if i > 6 else "normal", "adopted": 1 if i < 4 else 0,
         "kq_id": "KQ1", "role": "collector"}
        for i in range(1, 9)
    ],
    "gaps": [],
    "floor_status": [
        {"kq_id": "KQ1", "role": "collector",
         "queries": 8, "independent_sources": 3,
         "counter_queries": 2, "met": True},
    ],
}


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_date(s):
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def validate_early_stop(record):
    """Does an early-stop record meet the three conditions? Returns (valid, why not).

    With no record at all it returns (False, None). A reason comes back only when a
    record exists and falls short (collection_standards.md §1).
    """
    if record is None:
        return False, None
    if not isinstance(record, dict):
        return False, "early_stop is not an object"
    sources = record.get("independent_sources")
    streak = record.get("consecutive_zero_new")
    label = record.get("conclusion_confidence")
    if not isinstance(sources, int) or sources < EARLY_STOP_MIN_SOURCES:
        return False, f"independent_sources is below {EARLY_STOP_MIN_SOURCES}: {sources!r}"
    if not isinstance(streak, int) or streak < EARLY_STOP_MIN_ZERO_STREAK:
        return False, f"consecutive_zero_new is below {EARLY_STOP_MIN_ZERO_STREAK}: {streak!r}"
    if str(label).lower() not in [c.lower() for c in EARLY_STOP_CONFIDENCE]:
        return False, f"conclusion_confidence is below \"likely\": {label!r}"
    return True, None


class Auditor:
    def __init__(self, log, mode_override=None):
        self.log = log
        self.findings = []
        self.mode = mode_override or log.get("mode", "STANDARD")
        self.status_groups = {}   # check_floors fills it: {(kq_id, role): floor_status row}

    def add(self, severity, code, message, location=""):
        self.findings.append(
            {"severity": severity, "code": code, "message": message, "location": location})

    # ---- structure ------------------------------------------------

    def check_top(self):
        for key in ("schema", "topic", "as_of", "mode", "key_questions",
                    "evidence", "search_log"):
            if key not in self.log:
                self.add("FAIL", "E-TOP", f"the required top-level key {key} is missing")
        schema = str(self.log.get("schema", ""))
        m = re.match(r"^research-evidence-(\d+)\.(\d+)$", schema)
        if not m:
            self.add("FAIL", "E-SCHEMA", f"malformed schema: {schema!r}")
        elif int(m.group(1)) != SCHEMA_MAJOR:
            self.add("FAIL", "E-SCHEMA-MAJOR", f"the schema major is not {SCHEMA_MAJOR}: {schema}")
        elif int(m.group(2)) > SCHEMA_MINOR:
            # An older minor of the same major (1.0 and the like) is accepted as it is.
            self.add("WARN", "E-SCHEMA-MINOR",
                     f"the schema minor is newer than the {SCHEMA_MAJOR}.{SCHEMA_MINOR} this "
                     f"audit knows: {schema} (its unknown fields go unchecked)")
        if self.log.get("mode") not in FLOORS:
            self.add("FAIL", "E-MODE", f"invalid mode: {self.log.get('mode')!r}")
        if not parse_date(self.log.get("as_of", "")):
            self.add("FAIL", "E-ASOF", f"malformed as_of date: {self.log.get('as_of')!r}")

    def relevance_of(self, kq_id):
        """This KQ's decision relevance. Absent, it counts as a decision KQ."""
        for k in self.log.get("key_questions", []):
            if isinstance(k, dict) and k.get("id") == kq_id:
                rel = k.get("relevance")
                return rel if rel in VALID_RELEVANCE else "decision"
        return "decision"

    def floors_for(self, kq_id):
        """The floors this KQ gets. A background KQ in DEEP gets STANDARD's."""
        if self.mode == "DEEP" and self.relevance_of(kq_id) == "background":
            return FLOORS[BACKGROUND_FLOOR_MODE]
        return FLOORS.get(self.mode, FLOORS["STANDARD"])

    def check_kqs(self):
        kqs = self.log.get("key_questions", [])
        ids = [k.get("id") for k in kqs if isinstance(k, dict)]
        for k in kqs:
            if isinstance(k, dict) and k.get("relevance") not in (None,) + VALID_RELEVANCE:
                self.add("FAIL", "E-KQ-RELEVANCE",
                         f"{k.get('id')} has an invalid relevance: {k.get('relevance')!r} "
                         f"(one of {' / '.join(VALID_RELEVANCE)})")
        # The planning stage requires 2 to 7 (research_plan_linter.py checks it); the
        # ledger's floor is 1, so that a study escalated from LIGHT with a single KQ passes.
        if not (1 <= len(kqs) <= 7):
            self.add("FAIL", "E-KQ-COUNT",
                     f"key_questions must hold between 1 and 7 entries ({len(kqs)} found)")
        if len(ids) != len(set(ids)):
            self.add("FAIL", "E-KQ-DUP", "key_questions holds a duplicate id")
        return set(i for i in ids if i)

    def check_evidence(self, kq_ids):
        evidence = self.log.get("evidence", [])
        as_of = parse_date(self.log.get("as_of", "")) or datetime.date.today()
        seen_ids = set()
        all_ids = {e.get("id") for e in evidence if isinstance(e, dict)}

        if not evidence:
            self.add("FAIL", "E-EMPTY", "evidence is empty")

        for e in evidence:
            eid = e.get("id", "?")
            loc = f"evidence[{eid}]"
            if not re.match(r"^E\d+$", str(eid)):
                self.add("FAIL", "E-ID", f"malformed id: {eid!r}", loc)
            if eid in seen_ids:
                self.add("FAIL", "E-ID-DUP", f"the id {eid} appears twice", loc)
            seen_ids.add(eid)

            for kq in e.get("kq_ids", []) or ["(none)"]:
                if kq not in kq_ids:
                    self.add("FAIL", "E-KQ-REF", f"reference to an undefined KQ: {kq}", loc)

            claim = e.get("claim", "")
            if len(claim) < 10:
                self.add("FAIL", "E-CLAIM",
                         "claim is too short (one falsifiable proposition is required)", loc)
            if not enum_ok(e.get("claim_type"), VALID_CLAIM_TYPES):
                self.add("FAIL", "E-CLAIM-TYPE", f"invalid claim_type: {e.get('claim_type')!r}", loc)
            quote = e.get("verbatim_quote", "")
            if not quote:
                self.add("FAIL", "E-QUOTE", "verbatim_quote is missing and is required", loc)
            elif len(quote) < 8:
                self.add("WARN", "E-QUOTE-SHORT", f"verbatim_quote is short: {quote!r}", loc)

            src = e.get("source", {})
            for field in ("publisher", "title", "url", "published", "grade", "origin_cluster"):
                if not src.get(field):
                    self.add("FAIL", "E-SRC", f"source.{field} is missing", loc)
            url = src.get("url", "")
            if url and (not URL_RE.match(url) or "..." in url or "…" in url):
                self.add("FAIL", "E-URL", f"the URL is not a full absolute URL: {url!r}", loc)
            if src.get("grade") and not enum_ok(src["grade"], VALID_GRADES):
                self.add("FAIL", "E-GRADE", f"invalid grade: {src['grade']!r}", loc)
            if src.get("published") and not PUBLISHED_RE.match(str(src["published"])):
                self.add("FAIL", "E-PUB", f"malformed published: {src['published']!r}", loc)
            if not parse_date(e.get("accessed", "")):
                self.add("FAIL", "E-ACCESSED", f"malformed accessed date: {e.get('accessed')!r}", loc)

            # The optional fields added in 1.1.
            doi = src.get("doi")
            if doi and not DOI_RE.match(str(doi)):
                self.add("FAIL", "E-DOI", f"malformed source.doi: {doi!r}", loc)
            arxiv_id = src.get("arxiv_id")
            if arxiv_id and not ARXIV_ID_RE.match(str(arxiv_id)):
                self.add("FAIL", "E-ARXIV", f"malformed source.arxiv_id: {arxiv_id!r}", loc)
            sup = e.get("superseded_by")
            if sup:
                if sup == eid:
                    self.add("FAIL", "E-SUP-SELF", "superseded_by points at itself", loc)
                elif sup not in all_ids:
                    self.add("FAIL", "E-SUP-REF",
                             f"superseded_by points at an undefined id: {sup}", loc)
            lineage = e.get("lineage")
            if lineage:
                if not enum_ok(lineage.get("collected_by"), VALID_LINEAGE_COLLECTORS):
                    self.add("FAIL", "E-LIN-BY",
                             f"invalid lineage.collected_by: {lineage.get('collected_by')!r}", loc)
                if lineage.get("kq_id") not in kq_ids:
                    self.add("FAIL", "E-LIN-KQ",
                             f"lineage.kq_id points at an undefined KQ: {lineage.get('kq_id')!r}",
                             loc)

            corr = e.get("corroboration")
            if not enum_ok(corr, VALID_CORROBORATION):
                self.add("FAIL", "E-CORR", f"invalid corroboration: {corr!r}", loc)
            corr_ids = e.get("corroborating_ids", [])
            for cid in corr_ids:
                if cid not in all_ids:
                    self.add("FAIL", "E-CORR-REF",
                             f"corroborating_ids points at an undefined id: {cid}", loc)
                if cid == eid:
                    self.add("FAIL", "E-CORR-SELF", "corroborating_ids points at itself", loc)
            if (corr == "corroborated" and not corr_ids
                    and not has_external_corroboration(e, src)):
                self.add("FAIL", "E-CORR-EMPTY",
                         "corroboration is corroborated but corroborating_ids is empty", loc)

            ver = e.get("verification", {})
            if ver and not enum_ok(ver.get("status"), VALID_VERIFICATION):
                self.add("FAIL", "E-VER",
                         f"invalid verification.status: {ver.get('status')!r}", loc)

            # The rules for a key figure.
            if e.get("is_key_figure"):
                grades = {src.get("grade")}
                for cid in corr_ids:
                    other = next((x for x in evidence if x.get("id") == cid), None)
                    if other:
                        grades.add(other.get("source", {}).get("grade"))
                if grades <= {"C"}:
                    self.add("FAIL", "E-KEY-CGRADE",
                             "a key figure resting on grade-C sources alone "
                             "(collection_standards.md §4)", loc)
                if corr == "corroborated":
                    # R3: corroborated needs two independent clusters (evaluation_protocol.md §3).
                    clusters = {src.get("origin_cluster")}
                    for cid in corr_ids:
                        other = next((x for x in evidence if x.get("id") == cid), None)
                        if other:
                            clusters.add(other.get("source", {}).get("origin_cluster"))
                    clusters.discard(None)
                    if len(clusters) < 2 and not has_external_corroboration(e, src):
                        self.add("FAIL", "E-KEY-CLUSTER",
                                 f"a corroborated key figure rests on {len(clusters)} independent "
                                 "cluster (two are the rule; a reprint of the same origin is not "
                                 "corroboration)", loc)
                if corr == "single_source":
                    # Two independent clusters are the rule, so a single-source key figure
                    # has to say why.
                    if (ver.get("note") or "").strip():
                        self.add("WARN", "E-KEY-SINGLE",
                                 "a key figure rests on a single source (the reason is recorded; "
                                 "say so in the report)", loc)
                    else:
                        self.add("FAIL", "E-KEY-SINGLE",
                                 "a key figure rests on a single source and verification.note "
                                 "gives no reason (two independent clusters are the rule)", loc)
                if e.get("self_reported"):
                    note = ver.get("note") or ""
                    if (SELF_REPORTED_MARKER not in claim.lower()
                            and SELF_REPORTED_MARKER not in note.lower()):
                        self.add("FAIL", "E-KEY-SELFREP",
                                 "a self_reported key figure is marked \"self-reported\" in "
                                 "neither claim nor verification.note", loc)
                if src.get("user_supplied"):
                    note = ver.get("note") or ""
                    if (USER_SUPPLIED_MARKER not in claim.lower()
                            and USER_SUPPLIED_MARKER not in note.lower()):
                        self.add("FAIL", "E-KEY-USERSUP",
                                 "a user-supplied key figure is marked \"user-supplied\" in "
                                 "neither claim nor verification.note", loc)
                # Freshness: three years for a key figure of type fact.
                pub = str(src.get("published", ""))[:4]
                if pub.isdigit() and e.get("claim_type") == "fact":
                    if as_of.year - int(pub) > 3 and not e.get("staleness_note"):
                        self.add("WARN", "E-STALE",
                                 f"published in {pub}, over three years before the as-of date, "
                                 "with no staleness_note", loc)

        return evidence

    # ---- quality: the floors and the disconfirmation ---------------

    def floor_status_groups(self, kq_ids):
        """{(kq_id, role): row} from the ledger's floor_status array."""
        groups = {}
        for row in self.log.get("floor_status") or []:
            if not isinstance(row, dict):
                continue
            key = (row.get("kq_id"), row.get("role"))
            if key[0] in kq_ids and key[1] in ROLES:
                groups[key] = row
        return groups

    def early_stop_of(self, kq, role=None):
        """The early-stop record of a group (of any of this KQ's groups if role is None).

        Returns (valid, record, why not). A record that exists but misses one of the
        three conditions is not valid and comes back with a reason, which the caller
        reports as a FAIL.
        """
        keys = [k for k in self.status_groups
                if k[0] == kq and (role is None or k[1] == role)]
        for key in sorted(keys):
            record = (self.status_groups.get(key) or {}).get("early_stop")
            if record is None:
                continue
            ok, reason = validate_early_stop(record)
            return ok, record, reason
        return False, None, None

    def check_query_floor(self, scope, rows, need_queries, need_counter,
                          shortfall, code_prefix="E-FLOOR",
                          base_queries=None, base_counter=None):
        """Check one group's query floors.

        Passing base_queries / base_counter (STANDARD's floors) reports a shortfall that
        still clears them as relaxed. Pass them only for a group with an early-stop record.
        """
        def relaxable(actual, base):
            return base is not None and actual >= base

        if len(rows) < need_queries:
            shortfall(f"{code_prefix}-QUERY",
                      f"{scope} ran {len(rows)} queries, below the floor of {need_queries}",
                      relaxed=relaxable(len(rows), base_queries))
        n_counter = sum(1 for s in rows if s.get("kind") == "counter")
        if n_counter < need_counter:
            shortfall(f"{code_prefix}-COUNTER",
                      f"{scope} ran {n_counter} disconfirmation queries, below the floor of "
                      f"{need_counter}",
                      relaxed=relaxable(n_counter, base_counter))

    def check_floors(self, kq_ids):
        search_log = self.log.get("search_log", [])
        evidence = self.log.get("evidence", [])
        unmet = []

        per_kq_attribution = all(s.get("kq_id") for s in search_log) if search_log else False
        self.status_groups = self.floor_status_groups(kq_ids)
        status_groups = self.status_groups

        def shortfall(code, message, relaxed=False):
            # A shortfall drops to WARN only where an early-stop record passed all three
            # conditions (collection_standards.md §1). gaps cannot serve that purpose: it
            # is a required output of collection and almost every study has one, so
            # relaxing the floors on its presence would disable the gate.
            if relaxed:
                self.add("WARN", code,
                         message + " (an early stop is recorded and STANDARD's floors are met)")
            else:
                self.add("FAIL", code, message + " (no early stop is recorded)")
            unmet.append(code)

        def base_floors(kq, role=None):
            """STANDARD's floors, for a group with an early-stop record. Else (None, None)."""
            ok, _, bad_reason = self.early_stop_of(kq, role)
            if bad_reason:
                self.add("FAIL", "E-EARLYSTOP-FORM",
                         f"the early_stop record for {kq}{'/' + role if role else ''} misses one "
                         f"of the three conditions: {bad_reason}")
            if not ok:
                return None, None
            base = FLOORS[BASE_FLOOR_MODE]
            return base["queries"], base["counter_queries"]

        def roles_of(kq, rows):
            """The collection roles launched for this KQ, from floor_status and search_log."""
            found = {k[1] for k in status_groups if k[0] == kq}
            found |= {s.get("role") for s in rows if s.get("role") in ROLES}
            return sorted(found)

        # The query floors, switching per KQ on decision relevance (collection_standards.md §1).
        if not per_kq_attribution:
            mode_floors = FLOORS.get(self.mode, FLOORS["STANDARD"])
            need = mode_floors["queries"]
            if need > 0:
                if search_log:
                    self.add("INFO", "E-SL-NOKQ",
                             "search_log carries no kq_id, so the floors were checked on the "
                             "total across every KQ")
                multiplier = max(1, len(kq_ids))
                self.check_query_floor("all KQs together", search_log, need * multiplier,
                                       mode_floors["counter_queries"] * multiplier, shortfall)
        elif self.mode == "DEEP":
            # DEEP judges per role: collector and scholar each clear the floors themselves.
            groups = sorted(set(status_groups) |
                            {(s.get("kq_id"), s.get("role")) for s in search_log
                             if s.get("role") in ROLES and s.get("kq_id") in kq_ids})
            if groups:
                for kq, role in groups:
                    floors = self.floors_for(kq)
                    if floors["queries"] <= 0:
                        continue
                    base_queries, base_counter = base_floors(kq, role)
                    rows = [s for s in search_log
                            if s.get("kq_id") == kq and s.get("role") == role]
                    self.check_query_floor(f"{kq}/{role}", rows, floors["queries"],
                                           floors["counter_queries"], shortfall,
                                           base_queries=base_queries, base_counter=base_counter)
            else:
                self.add("INFO", "E-SL-NOROLE",
                         "search_log carries no role, so the floors were checked per key question")
                for kq in sorted(kq_ids):
                    floors = self.floors_for(kq)
                    if floors["queries"] <= 0:
                        continue
                    base_queries, base_counter = base_floors(kq)
                    rows = [s for s in search_log if s.get("kq_id") == kq]
                    self.check_query_floor(kq, rows, floors["queries"],
                                           floors["counter_queries"], shortfall,
                                           base_queries=base_queries, base_counter=base_counter)
        else:
            # STANDARD totals per key question, and adds a minimum share per role.
            for kq in sorted(kq_ids):
                floors = self.floors_for(kq)
                if floors["queries"] <= 0:
                    continue
                min_queries = min(floors["queries"], MIN_ROLE_ALLOCATION["queries"])
                min_counter = min(floors["counter_queries"],
                                  MIN_ROLE_ALLOCATION["counter_queries"])
                rows = [s for s in search_log if s.get("kq_id") == kq]
                self.check_query_floor(kq, rows, floors["queries"],
                                       floors["counter_queries"], shortfall)
                for role in roles_of(kq, rows):
                    rrows = [s for s in rows if s.get("role") == role]
                    self.check_query_floor(f"{kq}/{role} (the per-role minimum)", rrows,
                                           min_queries, min_counter, shortfall,
                                           code_prefix="E-FLOOR-ROLE")

        # The independent-source floor. A cluster whose evidence is all user_supplied counts
        # at most once per KQ (five internal PDFs must not clear a DEEP floor by themselves).
        for kq in sorted(kq_ids):
            floors = self.floors_for(kq)
            by_cluster = {}
            for e in evidence:
                if kq not in (e.get("kq_ids") or []):
                    continue
                oc = e.get("source", {}).get("origin_cluster")
                if oc is not None:
                    by_cluster.setdefault(oc, []).append(e)
            clusters = set()
            has_user_supplied_cluster = False
            for oc, items in by_cluster.items():
                if all(it.get("source", {}).get("user_supplied") for it in items):
                    has_user_supplied_cluster = True
                else:
                    clusters.add(oc)
            if has_user_supplied_cluster:
                clusters.add("[user-supplied]")
            if len(clusters) < floors["independent_sources"]:
                early_ok, _, _ = self.early_stop_of(kq)
                base = FLOORS[BASE_FLOOR_MODE]["independent_sources"]
                shortfall("E-FLOOR-SOURCE",
                          f"{kq} rests on {len(clusters)} independent sources, below the floor "
                          f"of {floors['independent_sources']}",
                          relaxed=early_ok and len(clusters) >= base)

        # The early stops, which the report's limitations section has to carry.
        for (kq, role) in sorted(status_groups):
            ok, record, _ = self.early_stop_of(kq, role)
            if ok:
                self.add("WARN", "E-EARLYSTOP",
                         f"{kq}/{role} finished on an early stop "
                         f"(independent sources {record.get('independent_sources')} / "
                         f"{record.get('consecutive_zero_new')} consecutive queries with nothing "
                         f"new / conclusion \"{record.get('conclusion_confidence')}\"). "
                         "Transcribe what was cut into the report's limitations section")

        # The disconfirmation record (required in STANDARD and DEEP).
        if self.mode in ("STANDARD", "DEEP") and not self.log.get("disconfirmation"):
            self.add("FAIL", "E-DISC",
                     "disconfirmation is empty (the disconfirmation search is a duty; where it "
                     "finds nothing, record the queries run and that they found nothing)")

        return unmet

    def run(self):
        self.check_top()
        kq_ids = self.check_kqs()
        self.check_evidence(kq_ids)
        self.check_floors(kq_ids)
        return self.findings


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="The deterministic audit of the evidence ledger (evidence_log.json)")
    parser.add_argument("log", nargs="?", help="path to evidence_log.json")
    parser.add_argument("--mode", choices=list(FLOORS), default=None,
                        help="the mode whose floors apply (otherwise the ledger's own mode)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--sample", action="store_true", help="print a sample ledger and stop")
    args = parser.parse_args()

    if args.sample:
        print(json.dumps(SAMPLE, ensure_ascii=False, indent=2))
        return 0

    if not args.log:
        parser.error("give the path to evidence_log.json, or pass --sample")

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
    except OSError as e:
        print(f"error: cannot read the file: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: not valid JSON: {e}", file=sys.stderr)
        return 2

    auditor = Auditor(log, args.mode)
    findings = auditor.run()
    fails = [f for f in findings if f["severity"] == "FAIL"]
    warns = [f for f in findings if f["severity"] == "WARN"]
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")

    n_evidence = len(log.get("evidence", []))
    n_key = sum(1 for e in log.get("evidence", []) if e.get("is_key_figure"))
    summary = {
        "verdict": verdict, "mode": auditor.mode,
        "evidence_count": n_evidence, "key_figure_count": n_key,
        "fail_count": len(fails), "warn_count": len(warns),
        "findings": findings,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"verdict: {verdict} (mode: {auditor.mode} / {n_evidence} evidence units / "
              f"{n_key} key figures / FAIL {len(fails)} / WARN {len(warns)})")
        for f in findings:
            loc = f" @{f['location']}" if f.get("location") else ""
            print(f"  [{f['severity']}] {f['code']}{loc}: {f['message']}")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
