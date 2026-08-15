#!/usr/bin/env python3
"""fetch_page.py - fetch a source page and cache its text.

The default fetch path for research-team Step 2 (collection), used instead of WebFetch.
WebFetch returns a small model's answer to a prompt, so it cannot guarantee the wording of
the original. This script stores the extracted page text as it is; the collection agent then
greps the cache for the passage it needs and copies the verbatim_quote out of it. The text
goes through the same extraction and normalisation as citation_verifier.py, so the Step 3
quote check matches by construction rather than by the agent following an instruction.

Pages whose text cannot be taken (PDF, JavaScript-rendered, paywalled) come back with a
status instead of a file; fall back to WebFetch for those (collection_standards.md §9).

Output: {RUN_DIR}/pages/{first 16 hex of the URL's SHA1}.txt and {RUN_DIR}/pages/index.json
The body is wrapped at about 200 characters. The wrapping belongs to the cache, not to the
original text.

Examples:
    python fetch_page.py --run-dir research/20260816-topic https://example.com/a https://example.com/b
    python fetch_page.py --run-dir . https://example.com/a --json

Exit codes: 0 = every URL is in the cache (including cached) / 1 = some URL could not be
fetched / 2 = usage or I/O error
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import sys

from citation_verifier import (DEFAULT_TIMEOUT, HostThrottle, _configure_stdout,
                               html_to_text, http_request, normalize_text)

WRAP_WIDTH = 200        # target line length; one grep hit is one line of reading
MIN_CHARS = 400         # below this, the body was not really fetched (JS-rendered, paywalled)
DEFAULT_WORKERS = 4
BREAK_CHARS = (" ", ".", ",", ";")


def cache_name(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".txt"


def wrap_text(s, width=WRAP_WIDTH):
    """Wrap the body at about `width`, breaking after a break character where there is one."""
    lines = []
    i, n = 0, len(s)
    while i < n:
        if n - i <= width:
            lines.append(s[i:])
            break
        window = s[i:i + width]
        cut = max(window.rfind(c) for c in BREAK_CHARS)
        cut = width if cut < width // 2 else cut + 1
        lines.append(s[i:i + cut])
        i += cut
    return "\n".join(lines)


def fetch_one(url, run_dir, timeout, min_chars, force, throttle):
    """Fetch one URL into the cache. Returns the result dict."""
    path = os.path.join(run_dir, "pages", cache_name(url))
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            body = f.read()
        return {"url": url, "status": "cached", "path": path,
                "chars": len(body), "detail": "already fetched (no duplicate fetch)"}

    status, raw, ctype, err = http_request(url, timeout, method="GET", throttle=throttle)
    if status is None or status >= 400 or raw is None:
        return {"url": url, "status": "unreachable", "path": None, "chars": 0,
                "detail": f"GET failed: {err or status}"}
    if raw[:5] == b"%PDF-":
        return {"url": url, "status": "unsupported", "path": None, "chars": 0,
                "detail": "PDF (no text extraction here; fall back to WebFetch)"}

    text = normalize_text(html_to_text(raw, ctype))
    if len(text) < min_chars:
        return {"url": url, "status": "thin", "path": None, "chars": len(text),
                "detail": f"only {len(text)} characters of body"
                          " (JavaScript-rendered or paywalled; fall back to WebFetch)"}

    accessed = datetime.date.today().isoformat()
    header = (f"# url: {url}\n# accessed: {accessed}\n# chars: {len(text)}\n"
              "# Line breaks belong to this cache, not to the source. Quote from inside one line.\n\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + wrap_text(text) + "\n")
    return {"url": url, "status": "fetched", "path": path, "chars": len(text),
            "detail": f"HTTP {status}"}


def update_index(run_dir, results):
    """Update pages/index.json (the URL-to-cache map)."""
    index_path = os.path.join(run_dir, "pages", "index.json")
    index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
        except (OSError, json.JSONDecodeError):
            index = {}
    for r in results:
        if r["status"] in ("fetched", "cached"):
            index[r["url"]] = {"path": os.path.basename(r["path"]), "chars": r["chars"]}
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2, sort_keys=True)
    return index_path


def main():
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Fetch source pages and cache their text")
    parser.add_argument("urls", nargs="+", help="URLs to fetch")
    parser.add_argument("--run-dir", required=True, help="output directory (pages/ is created under it)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--min-chars", type=int, default=MIN_CHARS,
                        help=f"minimum characters to count as a body (default {MIN_CHARS})")
    parser.add_argument("--force", action="store_true", help="fetch again even when cached")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    throttle = HostThrottle()
    urls = list(dict.fromkeys(args.urls))  # drop repeated URLs in the arguments
    workers = max(1, min(args.workers, len(urls)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_one, u, args.run_dir, args.timeout,
                               args.min_chars, args.force, throttle) for u in urls]
        results = [f.result() for f in futures]  # keep the input order

    try:
        index_path = update_index(args.run_dir, results)
    except OSError as e:
        print(f"error: cannot write index.json: {e}", file=sys.stderr)
        return 2

    failed = [r for r in results if r["status"] not in ("fetched", "cached")]
    if args.json:
        print(json.dumps({"results": results, "index": index_path,
                          "failed": len(failed)}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"[{r['status']}] {r['url']}"
                  + (f" -> {r['path']} ({r['chars']} chars)" if r["path"] else f" - {r['detail']}"))
        if failed:
            print(f"{len(failed)} URL(s) fall back to WebFetch (collection_standards.md §9)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
