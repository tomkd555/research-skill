#!/usr/bin/env python3
"""Checks that the numbers quoted in the agent definitions and pipeline.md equal the scripts'.

The collector and scholar definitions carry the collection floors operatively (no agent reads
collection_standards.md at run time), and pipeline.md quotes the verification batch size and
cap. A number edited on one side and forgotten on the other would let an agent pass its own
check and fail the audit after the merge, so this test is the tripwire.

1. The floors table in research-collector.md and research-scholar.md equals evidence_auditor.FLOORS
2. The per-role minimum in both definitions equals evidence_auditor.MIN_ROLE_ALLOCATION
3. pipeline.md quotes select_verification_targets.MAX_BATCHES and BATCH_SIZE
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "research-team")
SCRIPTS = os.path.join(PLUGIN, "skills", "research-team", "scripts")
AGENTS = os.path.join(PLUGIN, "agents")
PIPELINE = os.path.join(PLUGIN, "skills", "research-team", "references", "pipeline.md")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, SCRIPTS)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


ROW_RE = re.compile(r"^\|\s*(Search queries|Independent sources|Disconfirmation queries)\s*\|"
                    r"\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|", re.MULTILINE)
KEYS = {"Search queries": "queries", "Independent sources": "independent_sources",
        "Disconfirmation queries": "counter_queries"}


def floors_in(text):
    """The floors table of one definition as {mode: {key: number}}."""
    out = {"DEEP": {}, "STANDARD": {}, "LIGHT": {}}
    for m in ROW_RE.finditer(text):
        key = KEYS[m.group(1)]
        for mode, cell in zip(("DEEP", "STANDARD", "LIGHT"), m.groups()[1:]):
            num = re.search(r"\d+", cell)
            out[mode][key] = int(num.group()) if num else 0
    return out


def main():
    ea = load("evidence_auditor")
    svt = load("select_verification_targets")
    ok = True

    def check(cond, label):
        nonlocal ok
        print(("  OK   " if cond else "  NG   ") + label)
        ok = ok and cond

    print("[the floors quoted in the definitions equal evidence_auditor.FLOORS]")
    for name in ("research-collector.md", "research-scholar.md"):
        text = read(os.path.join(AGENTS, name))
        quoted = floors_in(text)
        for mode in ("DEEP", "STANDARD", "LIGHT"):
            check(quoted[mode] == ea.FLOORS[mode],
                  "%s %s %s == %s" % (name, mode, quoted[mode], ea.FLOORS[mode]))
        alloc = ea.MIN_ROLE_ALLOCATION
        pattern = r"%d or more\s+queries and %d or more disconfirmation quer" % (
            alloc["queries"], alloc["counter_queries"])
        check(re.search(pattern, text) is not None,
              "%s quotes the per-role minimum %s" % (name, alloc))

    print("[pipeline.md quotes the verification batch constants]")
    text = read(PIPELINE)
    for mode, cap in svt.MAX_BATCHES.items():
        check(re.search(r"\b%d\s+in\s+%s\b" % (cap, mode), text) is not None,
              "pipeline.md quotes the %s cap %d" % (mode, cap))
    words = {3: "three", 4: "four", 5: "five", 6: "six"}
    size = svt.BATCH_SIZE
    check(re.search(r"\b(%s|%d) claims" % (words.get(size, "?"), size), text) is not None,
          "pipeline.md quotes the batch size %d" % size)

    print("OK" if ok else "NG")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
