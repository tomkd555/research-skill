#!/usr/bin/env python3
"""merge_fragments.py — merge the evidence fragments into the ledger (evidence_log.json).

Run it at the intake of research-team Step 2. Everything the orchestrator used to do by
hand — reading the fragments, merging them into the ledger, renumbering the provisional
IDs into the real ones, attaching a kq_id to every search-log row — happens here. What is
left to a person is the one part that needs judgement: uniting the independence clusters
across fragments.

The numbering follows a stable order taken from the file names: KQ number ascending, then
role (collector, then scholar), then the order within the fragment. The same input always
produces the same ledger.

A fragment or an evidence unit that cannot be taken in is never dropped in silence; it
goes into unmerged_report.json with the reason.

Examples:
    python merge_fragments.py --run-dir research/20260725-topic \\
        --brief research/20260725-topic/research_brief.md \\
        --mode STANDARD --as-of 2026-07-25 --topic "the research topic"
    python merge_fragments.py --run-dir DIR --topic X --as-of 2026-07-25 --mode DEEP --json

Outputs:
    {RUN_DIR}/evidence_log.json    the merged ledger
    {RUN_DIR}/id_map.json          provisional ID within a fragment -> real ID
    {RUN_DIR}/unmerged_report.json what could not be taken in (written empty if nothing)

Exit codes: 0 = everything merged / 1 = something was left out / 2 = usage or I/O error
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels

SCHEMA_VERSION = "research-evidence-1.3"
DEFAULT_DELIVERABLE_LANGUAGE = "en"
ROLE_ORDER = {"collector": 0, "scholar": 1}
# The decision-relevance tag at the end of a KQ line (collection_standards.md §1).
RELEVANCE_RE = labels.RELEVANCE_RE
FRAGMENT_RE = re.compile(r"^kq(\d+)_(collector|scholar)\.json$", re.IGNORECASE)
# The required fields of an evidence unit (kept in step with evidence_log.schema.json).
REQUIRED_EVIDENCE = ("kq_ids", "claim", "claim_type", "verbatim_quote",
                     "source", "accessed", "is_key_figure", "corroboration")
REQUIRED_SOURCE = ("publisher", "title", "url", "published", "grade")


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def discover_fragments(fragment_dir):
    """List the fragment files in a stable order. Returns [(path, kq_id, role)]."""
    if not os.path.isdir(fragment_dir):
        return []
    found = []
    for name in os.listdir(fragment_dir):
        m = FRAGMENT_RE.match(name)
        if m:
            found.append((os.path.join(fragment_dir, name),
                          f"KQ{int(m.group(1))}", m.group(2).lower()))
    found.sort(key=lambda t: (int(t[1][2:]), ROLE_ORDER.get(t[2], 9), t[0]))
    return found


def parse_brief_kqs(brief_path):
    """The KQ ids, texts and decision relevance from research_brief.md ([] if unreadable).

    The relevance is the [decision] / [background] tag at the end of a KQ line
    (collection_standards.md §1). A KQ without one gets no relevance field, and the later
    stages treat an absent one as a decision KQ.
    """
    if not brief_path or not os.path.isfile(brief_path):
        return []
    try:
        with open(brief_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    seen = {}
    for m in re.finditer(r"^[-*\s|]*\**(KQ(\d+))\**\s*[:|]\s*(.+?)\s*$", text, re.MULTILINE):
        kq_id, body = m.group(1), m.group(3)
        body = body.strip().strip("|").strip()
        rel = RELEVANCE_RE.search(body)
        relevance = labels.relevance_of(rel) if rel else None
        body = RELEVANCE_RE.sub("", body).strip()
        if kq_id not in seen and body:
            seen[kq_id] = (body, relevance)
    out = []
    for k, (text_body, relevance) in sorted(seen.items(), key=lambda kv: int(kv[0][2:])):
        kq = {"id": k, "text": text_body}
        if relevance:
            kq["relevance"] = relevance
        out.append(kq)
    return out


def validate_evidence(e):
    """Check one evidence unit's required fields. Returns why it fails, or None."""
    if not isinstance(e, dict):
        return "the evidence is not an object"
    missing = [k for k in REQUIRED_EVIDENCE if k not in e or e[k] in (None, "", [])]
    # False is a legitimate is_key_figure, so only its presence matters.
    if "is_key_figure" in e and "is_key_figure" in missing:
        missing.remove("is_key_figure")
    src = e.get("source")
    if not isinstance(src, dict):
        missing.append("source")
    else:
        missing += [f"source.{k}" for k in REQUIRED_SOURCE
                    if k not in src or src[k] in (None, "")]
    if missing:
        return "required fields are missing: " + ", ".join(sorted(set(missing)))
    return None


def merge(fragments, topic, as_of, mode, key_questions,
          deliverable_language=DEFAULT_DELIVERABLE_LANGUAGE):
    """Merge the fragments into the ledger. Returns (log, id_map, unmerged, per_fragment)."""
    evidence = []
    search_log = []
    disconfirmation = []
    gaps = []
    alternatives = []
    floor_status = []
    id_map = {}          # (fragment_path, tmp_id) -> E#
    per_fragment = []    # what came out of each fragment
    unmerged = {"fragments": [], "evidence": []}

    next_id = 1
    for path, kq_id, role in fragments:
        try:
            with open(path, encoding="utf-8") as f:
                frag = json.load(f)
        except OSError as exc:
            unmerged["fragments"].append({"file": path, "reason": f"unreadable: {exc}"})
            continue
        except json.JSONDecodeError as exc:
            unmerged["fragments"].append({"file": path, "reason": f"not valid JSON: {exc}"})
            continue
        if not isinstance(frag, dict):
            unmerged["fragments"].append({"file": path, "reason": "the top level is not an object"})
            continue

        frag_kq = frag.get("kq_id") or kq_id
        taken = 0
        for e in frag.get("evidence") or []:
            reason = validate_evidence(e)
            tmp_id = (e or {}).get("id") if isinstance(e, dict) else None
            if reason:
                unmerged["evidence"].append({"file": path, "tmp_id": tmp_id, "reason": reason})
                continue
            new = json.loads(json.dumps(e, ensure_ascii=False))  # leave the fragment alone
            new_id = f"E{next_id}"
            next_id += 1
            id_map[f"{path}::{tmp_id}"] = new_id
            new["id"] = new_id
            if not new.get("kq_ids"):
                new["kq_ids"] = [frag_kq]
            lineage = new.get("lineage") or {}
            lineage.setdefault("collected_by", role)
            lineage.setdefault("kq_id", frag_kq)
            lineage.setdefault("fragment_file", os.path.basename(path))
            new["lineage"] = lineage
            new["_src_fragment"] = path   # used to map the IDs, dropped at the end
            new["_tmp_id"] = tmp_id
            evidence.append(new)
            taken += 1

        for row in frag.get("search_log") or []:
            if isinstance(row, dict):
                r = dict(row)
                r["kq_id"] = frag_kq        # the per-KQ floor check needs it
                r["role"] = role            # the per-role floor check needs it
                search_log.append(r)
        for d in frag.get("disconfirmation") or []:
            if isinstance(d, dict):
                d = dict(d)
                d["kq_id"] = frag_kq    # so a per-KQ slice carries only its own records
                d["role"] = role
            disconfirmation.append(d)
        for g in frag.get("gaps") or []:
            gaps.append(g)
        for a in frag.get("alternatives") or []:
            alternatives.append(a)

        fs = frag.get("floor_status")
        floor_status.append({"kq_id": frag_kq, "role": role,
                             **(fs if isinstance(fs, dict) else {})})
        per_fragment.append({"file": os.path.basename(path), "kq_id": frag_kq,
                             "role": role, "evidence_taken": taken,
                             "floor_status": fs})

    # Map the reference fields (corroborating_ids / superseded_by) onto the real IDs.
    for e in evidence:
        path = e.pop("_src_fragment")
        e.pop("_tmp_id", None)
        cids = []
        for cid in e.get("corroborating_ids") or []:
            mapped = id_map.get(f"{path}::{cid}")
            if mapped:
                cids.append(mapped)
            elif re.fullmatch(r"E\d+", str(cid)):
                cids.append(cid)   # a fragment that already wrote a real ID passes through
            else:
                unmerged["evidence"].append(
                    {"file": path, "tmp_id": e["id"],
                     "reason": f"the corroborating_ids reference {cid} does not resolve "
                               "(the reference was dropped)"})
        if "corroborating_ids" in e:
            e["corroborating_ids"] = cids
        sup = e.get("superseded_by")
        if sup:
            e["superseded_by"] = id_map.get(f"{path}::{sup}", sup)

    log = {
        "schema": SCHEMA_VERSION,
        "topic": topic,
        "as_of": as_of,
        "mode": mode,
        "deliverable_language": deliverable_language,
        "key_questions": key_questions,
        "evidence": evidence,
        "disconfirmation": disconfirmation,
        "search_log": search_log,
        "gaps": gaps,
        "floor_status": floor_status,
    }
    if alternatives:
        log["alternatives"] = alternatives
    return log, id_map, unmerged, per_fragment


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Merge the evidence fragments into the ledger (evidence_log.json)")
    parser.add_argument("--run-dir", required=True, help="the deliverable directory")
    parser.add_argument("--topic", required=True, help="the research topic")
    parser.add_argument("--as-of", required=True, help="the as-of date (YYYY-MM-DD)")
    parser.add_argument("--mode", required=True, choices=["LIGHT", "STANDARD", "DEEP"])
    parser.add_argument("--brief", default=None,
                        help="path to research_brief.md (its KQ ids and texts are taken in)")
    parser.add_argument("--deliverable-language", default=DEFAULT_DELIVERABLE_LANGUAGE,
                        help="the language of the request, which the prose of the report and "
                             "the brief is written in")
    parser.add_argument("--fragment-dir", default=None,
                        help="the fragment directory (default: {RUN_DIR}/evidence_fragments)")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    fragment_dir = args.fragment_dir or os.path.join(run_dir, "evidence_fragments")
    fragments = discover_fragments(fragment_dir)
    if not fragments:
        print(f"error: there is no fragment file at all: {fragment_dir}", file=sys.stderr)
        return 2

    key_questions = parse_brief_kqs(args.brief)
    if not key_questions:
        # With nothing readable in the brief, raise the KQs from the fragment file names
        # (the text is the ID rather than empty).
        seen = []
        for _, kq_id, _ in fragments:
            if kq_id not in seen:
                seen.append(kq_id)
        key_questions = [{"id": k, "text": k} for k in
                         sorted(seen, key=lambda x: int(x[2:]))]

    log, id_map, unmerged, per_fragment = merge(
        fragments, args.topic, args.as_of, args.mode, key_questions,
        args.deliverable_language)

    paths = {
        "evidence_log": os.path.join(run_dir, "evidence_log.json"),
        "id_map": os.path.join(run_dir, "id_map.json"),
        "unmerged_report": os.path.join(run_dir, "unmerged_report.json"),
    }
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(paths["evidence_log"], "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        with open(paths["id_map"], "w", encoding="utf-8") as f:
            json.dump(id_map, f, ensure_ascii=False, indent=2)
        with open(paths["unmerged_report"], "w", encoding="utf-8") as f:
            json.dump(unmerged, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"error: cannot write the output: {e}", file=sys.stderr)
        return 2

    missing_cluster = [e["id"] for e in log["evidence"]
                       if not (e.get("source") or {}).get("origin_cluster")]
    summary = {
        "fragments": len(fragments),
        "evidence_merged": len(log["evidence"]),
        "search_log_rows": len(log["search_log"]),
        "disconfirmation_rows": len(log["disconfirmation"]),
        "unmerged_fragments": len(unmerged["fragments"]),
        "unmerged_evidence": len(unmerged["evidence"]),
        "origin_cluster_missing": missing_cluster,
        "per_fragment": per_fragment,
        "outputs": paths,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"merged: {summary['fragments']} fragments -> "
              f"{summary['evidence_merged']} evidence units / "
              f"{summary['search_log_rows']} search-log rows / "
              f"{summary['disconfirmation_rows']} disconfirmation records")
        print(f"output: {paths['evidence_log']}")
        for row in per_fragment:
            print(f"  {row['file']}: {row['kq_id']} / {row['role']} / "
                  f"{row['evidence_taken']} evidence units")
        if missing_cluster:
            print(f"needs attention: {len(missing_cluster)} evidence units have no "
                  f"origin_cluster ({', '.join(missing_cluster[:10])}). Work out their origin "
                  "across the fragments and assign one")
        if unmerged["fragments"] or unmerged["evidence"]:
            print(f"left out: {len(unmerged['fragments'])} fragments / "
                  f"{len(unmerged['evidence'])} evidence units -> {paths['unmerged_report']}")

    return 1 if (unmerged["fragments"] or unmerged["evidence"]) else 0


if __name__ == "__main__":
    sys.exit(main())
