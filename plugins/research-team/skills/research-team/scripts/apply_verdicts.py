#!/usr/bin/env python3
"""apply_verdicts.py - apply the verifiers' verdicts to the evidence ledger deterministically.

Used in research-team Step 3. It reads the verdicts_{BATCH_ID}.json files written by
research-verifier and applies them to the verification block of each unit in
evidence_log.json. This removes the path where the orchestrator copies verdicts out of an
agent's message by hand, so a verdict cannot land on the wrong evidence unit.

Where a verdict overwrites the corroboration already on the ledger, the change is recorded
in changes rather than made silently. An ID the ledger does not hold, or an invalid status,
is not applied and goes to errors; an evidence unit that was selected for verification but
came back without a verdict goes to missing.

Examples:
    python apply_verdicts.py evidence_log.json --verdicts-dir verification/
    python apply_verdicts.py evidence_log.json --verdicts-dir verification/ \\
        --expected E1,E3,E7 --json

Exit codes: 0 = everything applied / 1 = there are errors or missing verdicts / 2 = usage
or I/O error
"""

import argparse
import glob
import json
import os
import sys

VALID_VERDICT = {"confirmed", "plausible", "disputed", "refuted", "unchecked"}
VALID_CORROBORATION = {"corroborated", "single_source", "conflicting"}
# Optional fields carried over from the verdict into the verification block
CARRY_FIELDS = ("method", "note", "quote_check", "attribution_check",
                "counter_evidence", "confidence_band")


def _configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load_verdicts(verdicts_dir):
    """Read verdicts_*.json in filename order. Returns a list of (verdict, source_file)."""
    rows = []
    read_errors = []
    for path in sorted(glob.glob(os.path.join(verdicts_dir, "verdicts_*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            read_errors.append({"file": path, "reason": f"cannot read the file: {e}"})
            continue
        except json.JSONDecodeError as e:
            read_errors.append({"file": path, "reason": f"not valid JSON: {e}"})
            continue
        items = data.get("verdicts") if isinstance(data, dict) else data
        if not isinstance(items, list):
            read_errors.append({"file": path, "reason": "no verdicts array"})
            continue
        for v in items:
            rows.append((v, os.path.basename(path)))
    return rows, read_errors


def apply(log, verdict_rows, expected_ids):
    by_id = {e.get("id"): e for e in log.get("evidence", [])}
    errors = []
    changes = []
    applied = []

    for v, src_file in verdict_rows:
        if not isinstance(v, dict):
            errors.append({"file": src_file, "id": None, "reason": "the verdict is not an object"})
            continue
        eid = v.get("id")
        target = by_id.get(eid)
        if target is None:
            errors.append({"file": src_file, "id": eid, "reason": "no such ID in the ledger"})
            continue
        status = v.get("verdict")
        if status not in VALID_VERDICT:
            errors.append({"file": src_file, "id": eid,
                           "reason": f"invalid verdict: {status!r}"})
            continue

        ver = dict(target.get("verification") or {})
        prev = ver.get("status")
        ver["status"] = status
        for key in CARRY_FIELDS:
            if v.get(key) not in (None, "", [], {}):
                ver[key] = v[key]
        target["verification"] = ver
        if prev and prev != status:
            changes.append({"id": eid, "field": "verification.status",
                            "before": prev, "after": status, "file": src_file})

        corroboration_field = v.get("corroboration")
        corr_source = (corroboration_field.get("corroborating_source")
                      if isinstance(corroboration_field, dict) else None)
        corr = (corroboration_field.get("status") if isinstance(corroboration_field, dict)
               else corroboration_field)
        if corr:
            if corr not in VALID_CORROBORATION:
                errors.append({"file": src_file, "id": eid,
                               "reason": f"invalid corroboration: {corr!r}"})
            else:
                if target.get("corroboration") != corr:
                    changes.append({"id": eid, "field": "corroboration",
                                    "before": target.get("corroboration"), "after": corr,
                                    "file": src_file})
                    target["corroboration"] = corr
                # The verifier's own find: the object the auditor checks against the
                # unit's own domain when the merge attached no corroborating_ids entry.
                if isinstance(corr_source, dict) and corr_source:
                    if ver.get("corroborating_source") != corr_source:
                        changes.append({"id": eid, "field": "verification.corroborating_source",
                                        "before": ver.get("corroborating_source"),
                                        "after": corr_source, "file": src_file})
                    ver["corroborating_source"] = corr_source
        applied.append(eid)

    missing = []
    if expected_ids:
        got = set(applied)
        missing = [i for i in expected_ids if i not in got]
    return {"applied": applied, "errors": errors, "changes": changes, "missing": missing}


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Apply the verifiers' verdicts to the evidence ledger deterministically")
    parser.add_argument("log", help="path to evidence_log.json")
    parser.add_argument("--verdicts-dir", required=True,
                        help="directory holding the verdicts_*.json files")
    parser.add_argument("--expected", default=None,
                        help="comma-separated evidence IDs selected for verification "
                             "(used to detect missing verdicts)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the result without writing the ledger back")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    try:
        with open(args.log, encoding="utf-8") as f:
            log = json.load(f)
    except OSError as e:
        print(f"error: cannot read the evidence ledger: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: the evidence ledger is not valid JSON: {e}", file=sys.stderr)
        return 2

    if not os.path.isdir(args.verdicts_dir):
        print(f"error: no such verdicts directory: {args.verdicts_dir}", file=sys.stderr)
        return 2

    verdict_rows, read_errors = load_verdicts(args.verdicts_dir)
    expected = [x.strip() for x in args.expected.split(",") if x.strip()] if args.expected else None
    result = apply(log, verdict_rows, expected)
    result["errors"] = read_errors + result["errors"]

    if not args.dry_run:
        try:
            with open(args.log, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"error: cannot write the evidence ledger: {e}", file=sys.stderr)
            return 2

    result["verdict_files"] = len(set(src for _, src in verdict_rows))
    result["applied_count"] = len(result["applied"])

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"applied: {result['applied_count']} verdict(s) "
              f"from {result['verdict_files']} file(s)"
              + (" / the ledger was left unchanged (--dry-run)" if args.dry_run else ""))
        for c in result["changes"]:
            print(f"  changed {c['id']}.{c['field']}: {c['before']} -> {c['after']}")
        for e in result["errors"]:
            print(f"  error {e.get('id') or e.get('file')}: {e['reason']}")
        if result["missing"]:
            print(f"  not applied (no verdict came back): {', '.join(result['missing'])}")

    return 1 if (result["errors"] or result["missing"]) else 0


if __name__ == "__main__":
    sys.exit(main())
