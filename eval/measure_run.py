"""measure_run.py - token use and wall time of research-team agents in one Claude Code session.

Reads the session transcript and the subagent transcripts beside it
(`~/.claude/projects/<project>/<session>.jsonl` and `<session>/subagents/*.jsonl`), keeps the
agents whose type starts with `research-team:`, and sums the `usage` fields per role. A message
is written as several transcript lines that repeat its id, so usage is counted once per id, taking
the largest value seen for each field. Wall time is the span of a transcript's timestamps.

Examples:
    python eval/measure_run.py ~/.claude/projects/<project>/<session-id>.jsonl
    python eval/measure_run.py SESSION.jsonl --json

Exit codes: 0 = printed / 2 = the session file does not exist
"""

import argparse
import collections
import datetime
import glob
import json
import os
import sys

FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def read_agent(path):
    per_message, stamps, tools = {}, [], collections.Counter()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("timestamp"):
                stamps.append(rec["timestamp"])
            msg = rec.get("message") or {}
            if rec.get("type") != "assistant":
                continue
            usage, mid = msg.get("usage") or {}, msg.get("id")
            prev = per_message.get(mid, {})
            per_message[mid] = {k: max(prev.get(k, 0), usage.get(k) or 0) for k in FIELDS}
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools[block["name"]] += 1
    usage = collections.Counter()
    for v in per_message.values():
        usage.update(v)
    minutes = 0.0
    if len(stamps) > 1:
        t0 = datetime.datetime.fromisoformat(stamps[0].replace("Z", "+00:00"))
        t1 = datetime.datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
        minutes = (t1 - t0).total_seconds() / 60
    return usage, len(per_message), tools, minutes


def measure(session):
    roles = collections.defaultdict(lambda: {"agents": 0, "turns": 0, "minutes": 0.0,
                                             "usage": collections.Counter(),
                                             "tools": collections.Counter()})
    for path in glob.glob(os.path.join(session[:-len(".jsonl")], "subagents", "*.jsonl")):
        meta = path[:-len(".jsonl")] + ".meta.json"
        kind = "?"
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as fh:
                kind = json.load(fh).get("agentType", "?")
        if not kind.startswith("research-team:"):
            continue
        usage, turns, tools, minutes = read_agent(path)
        r = roles[kind.split(":", 1)[1]]
        r["agents"] += 1
        r["turns"] += turns
        r["minutes"] = max(r["minutes"], minutes)  # the slowest agent of a role sets the wait
        r["usage"].update(usage)
        r["tools"].update(tools)
    return roles


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session", help="path to the session .jsonl")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.session):
        print(f"no such file: {args.session}", file=sys.stderr)
        return 2
    roles = measure(args.session)
    rows, total_in, total_out = [], 0, 0
    for role, r in sorted(roles.items()):
        u = r["usage"]
        inp = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
        total_in += inp
        total_out += u["output_tokens"]
        rows.append({"role": role, "agents": r["agents"], "turns": r["turns"],
                     "input_tokens": inp, "cache_write": u["cache_creation_input_tokens"],
                     "output_tokens": u["output_tokens"], "slowest_minutes": round(r["minutes"], 1),
                     "web_search": r["tools"]["WebSearch"], "web_fetch": r["tools"]["WebFetch"]})
    if args.json:
        print(json.dumps({"roles": rows, "input_tokens": total_in, "output_tokens": total_out}, indent=2))
        return 0
    for row in rows:
        print(f"{row['role']:20s} agents={row['agents']:2d} turns={row['turns']:4d} "
              f"input={row['input_tokens'] / 1e6:6.2f}M output={row['output_tokens'] / 1e3:6.1f}k "
              f"slowest={row['slowest_minutes']:5.1f}min WS={row['web_search']} WF={row['web_fetch']}")
    print(f"TOTAL input={total_in / 1e6:.1f}M output={total_out / 1e3:.0f}k")
    return 0


if __name__ == "__main__":
    sys.exit(main())
