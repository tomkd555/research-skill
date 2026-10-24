#!/usr/bin/env python3
"""select_claims.py - pick the cited sentences of report.md for independent verification.

Used in research-team Step 4, before the verifiers start. Standard library only, no network.

Example:
    python select_claims.py --run-dir research/20261024-topic --cap 10

Candidates are the sentences of report.md that carry a marker. Order: sentences under
"## Answer", then sentences with a digit (report order), then the rest (report order). The
list is cut at --cap and written as claims/batch_{k}.json, 5 claims per file, each claim with
its evidence quotes, urls and cached page paths ("page" is null for a paper item or an
uncached url). Prints the batch paths and the number of candidates the cap dropped.

Exit codes: 0 = batches written / 2 = usage or I/O error
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import citation_verifier as cv  # noqa: E402
import report_check as rc  # noqa: E402

BATCH_SIZE = 5


def main():
    rc._configure_stdout()
    ap = argparse.ArgumentParser(description="Select cited report sentences for verification.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--cap", type=int, required=True, help="most claims to verify (10 STANDARD, 25 DEEP)")
    args = ap.parse_args()
    try:
        with open(os.path.join(args.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        evidence = {e["id"]: e for e in rc.read_jsonl(os.path.join(args.run_dir, "evidence.jsonl"))}

        cited = [(sec, s) for sec, s in rc.report_sentences(report) if rc.MARKER_RE.search(s)]
        answer = [s for sec, s in cited if sec == "## Answer"]
        rest = [(sec, s) for sec, s in cited if sec != "## Answer"]
        ordered = answer + [s for _, s in rest if rc.has_digit_outside_marker(s)] \
            + [s for _, s in rest if not rc.has_digit_outside_marker(s)]
        chosen = ordered[:max(args.cap, 0)]

        claims = []
        for n, s in enumerate(chosen, 1):
            ev = []
            for i in dict.fromkeys(rc.marker_ids(s)):
                e = evidence.get(i)
                if e is None:
                    continue
                # the cache file name derives from the url; index.json can lose entries
                name = cv.cache_name(e["url"])
                cached = os.path.exists(os.path.join(args.run_dir, "pages", name))
                page = None if e.get("paper") or not cached else "pages/" + name
                ev.append({"id": i, "quote": e["quote"], "url": e["url"], "page": page})
            claims.append({"cid": f"C{n}", "sentence": s, "evidence": ev})

        os.makedirs(os.path.join(args.run_dir, "claims"), exist_ok=True)
        # a rerun must not leave batches or verdicts of an earlier report behind
        for old in glob.glob(os.path.join(args.run_dir, "claims", "batch_*.json"))                 + glob.glob(os.path.join(args.run_dir, "claims", "verdicts_*.json")):
            os.remove(old)
        paths = []
        for k in range(0, len(claims), BATCH_SIZE):
            path = os.path.join(args.run_dir, "claims", f"batch_{k // BATCH_SIZE + 1}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(claims[k:k + BATCH_SIZE], f, ensure_ascii=False, indent=2)
            paths.append(path)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(paths))
    print(f"{len(claims)} claims in {len(paths)} batches; {len(ordered) - len(chosen)} candidates "
          "dropped by the cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
