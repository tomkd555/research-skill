#!/usr/bin/env python3
"""Tests for research_plan_linter.py.

They cover the required role-assignment check and the WebSearch budget estimate.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")
PY = sys.executable
FAILURES = []


def check(label, cond, detail=""):
    print(("  OK   " if cond else "  NG   ") + label + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(label)


def lint(path, mode, limit="200"):
    env = dict(os.environ)
    env["CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION"] = limit
    cp = subprocess.run(
        [PY, os.path.join(SCRIPTS, "research_plan_linter.py"), path, "--mode", mode, "--json"],
        capture_output=True, text=True, encoding="utf-8", env=env)
    return cp.returncode, json.loads(cp.stdout)


def codes(result, severity=None):
    return [f["code"] for f in result["findings"]
            if severity is None or f["severity"] == severity]


def brief(mode, n_kq, roles_line="- Role assignment: KQ1=collector, KQ2=scholar"):
    kq_lines = "\n".join(f"- KQ{i}: Does proposition {i} hold?" for i in range(1, n_kq + 1))
    return f"""# Research plan: a test topic

- Mode: {mode}
- as_of: 2026-07-25

## Purpose

It feeds a decision.

## Key questions

{kq_lines}

## Competing hypotheses

- H1: It holds.
- H2: It does not.

## Disconfirmation plan

| Hypothesis | Observable if false | Disconfirming query |
|---|---|---|
| H1 | Observation A | Query A |
| H2 | Observation B | Query B |

## Source plan

- Preferred primary sources: government statistics
{roles_line}

## Stopping rules

- The floors are met and two consecutive queries return nothing new.

## Out of scope

- Markets outside the region.
"""


DECISION_BRIEF = """# Research plan: edge inference chips

- Mode: DEEP
- as_of: 2026-08-16

## Purpose

Decide which edge inference chip to standardise on for the 2027 product line.

## Key questions

- KQ1: Which vendors ship an edge inference chip under 5 W today? [decision]
- KQ2: How does throughput per watt compare across them? [decision]
- KQ3: What is the supply outlook through 2027? [background]

## Competing hypotheses

- H1: The incumbent vendor still leads on throughput per watt.
- H2: A newer entrant has overtaken it since 2025.

## Disconfirmation plan

| Hypothesis | Observable if false | Disconfirming query |
|---|---|---|
| H1 | Independent benchmarks put an entrant ahead | "edge NPU benchmark 2026 independent" |
| H2 | Entrant benchmarks come only from its own material | "entrant NPU third-party benchmark" |

## Source plan

- Role assignment: KQ1=collector, KQ2=collector+scholar, KQ3=collector

## Stopping rules

The collection floors are met and two consecutive queries return nothing new.

## Out of scope

Data-centre accelerators, and anything above 25 W.
"""


def write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="rt-linter-")
    try:
        print("[the role assignment is required]")
        p = write(tmp, "no_role.md", brief("STANDARD", 3,
                                           roles_line="- Likely publishers: e-Stat"))
        rc, res = lint(p, "STANDARD")
        check("no role assignment fails", "P-SEC-ROLE_ASSIGNMENT" in codes(res, "FAIL"),
              str(codes(res, "FAIL")))
        check("it exits 1", rc == 1, f"rc={rc}")

        p = write(tmp, "role_ok.md", brief(
            "STANDARD", 3,
            roles_line="- Role assignment: KQ1=collector, KQ2=scholar, KQ3=collector+scholar"))
        rc, res = lint(p, "STANDARD")
        check("a role assignment clears the FAILs", not codes(res, "FAIL"),
              str(codes(res, "FAIL")))
        check("a plan within the caps exits 0", rc == 0, f"rc={rc}")

        print("[the search budget estimate]")
        # DEEP, 7 KQs, both roles: collection ceil((12 + 4.8) * 7) = 118 plus
        # verification 60 = 178. The verification share follows the batch cap
        # (DEEP: 10 batches x 3 claims x 2 queries) and does not grow with the KQ count.
        deep_roles = ", ".join(f"KQ{i}=collector+scholar" for i in range(1, 8))
        p = write(tmp, "deep7.md", brief("DEEP", 7,
                                         roles_line=f"- Role assignment: {deep_roles}"))
        rc, res = lint(p, "DEEP", limit="150")
        check("a plan over the cap fails", "P-BUDGET" in codes(res, "FAIL"),
              str(codes(res, "FAIL")))
        check("it exits 1", rc == 1, f"rc={rc}")
        msg = next(f["message"] for f in res["findings"] if f["code"] == "P-BUDGET")
        check("it reports the estimate of 178", "178" in msg, msg)

        rc, res = lint(p, "DEEP", limit="400")
        check("a cap of 400 does not fail", "P-BUDGET" not in codes(res, "FAIL"),
              str(codes(res, "FAIL")))

        # scholar alone gets the 0.4 factor: collection ceil(4.8 * 7) = 34 plus 60 = 94.
        scholar_roles = ", ".join(f"KQ{i}=scholar" for i in range(1, 8))
        p = write(tmp, "deep7s.md", brief("DEEP", 7,
                                          roles_line=f"- Role assignment: {scholar_roles}"))
        rc, res = lint(p, "DEEP", limit="200")
        msg = next(f["message"] for f in res["findings"] if f["code"] == "P-BUDGET")
        check("scholar alone carries the 0.4 factor", "94" in msg, msg)

        # A role assignment that cannot be read per KQ is estimated as both roles.
        p = write(tmp, "vague.md",
                  brief("DEEP", 7, roles_line="- Role assignment: assigned by subject"))
        rc, res = lint(p, "DEEP", limit="200")
        msg = next(f["message"] for f in res["findings"] if f["code"] == "P-BUDGET")
        check("an unreadable assignment is estimated as both roles", "178" in msg, msg)
        check("and is reported as a WARN", "P-ROLE-UNREADABLE" in codes(res, "WARN"),
              str(codes(res, "WARN")))

        print("[decision relevance]")
        p = write(tmp, "decision.md", DECISION_BRIEF)
        rc, res = lint(p, "DEEP", limit="200")
        check("a DEEP plan tagging every KQ passes", rc == 0 and not codes(res, "FAIL"),
              codes(res, "FAIL"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
