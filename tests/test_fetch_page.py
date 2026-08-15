#!/usr/bin/env python3
"""Checks for fetch_page.py.

1. A quote taken from the cache passes citation_verifier's match against the live body
2. Wrapping does not change the text (identical once whitespace is removed)
3. Pages whose body cannot be taken (PDF, thin) get a status and are not cached
4. A second fetch returns the cache (the no-duplicate-fetch rule held by the path itself)
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")
sys.path.insert(0, SKILL_SCRIPTS)  # fetch_page imports citation_verifier


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fp = load(os.path.join(SKILL_SCRIPTS, "fetch_page.py"), "fp_new")
cv = load(os.path.join(SKILL_SCRIPTS, "citation_verifier.py"), "cv_for_fp")

SENTENCE = ("Research firm X puts the domestic generative AI market at 101.6 billion yen for fiscal 2025. "
            "The same report puts the 2026 forecast at 148.0 billion yen, a 45.7% increase.")
PAGE_HTML = ("<html><head><style>.x{color:red}</style></head><body><p>"
             + "An introductory passage sits ahead of the figure. " * 20 + SENTENCE
             + " Supplementary passages follow the figure. " * 20 + "</p></body></html>").encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/page":
            body, ctype = PAGE_HTML, "text/html; charset=utf-8"
        elif self.path == "/pdf":
            body, ctype = b"%PDF-1.7\n" + b"x" * 2000, "application/pdf"
        else:
            body, ctype = b"<html><body>loading...</body></html>", "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_fetch_and_quote_round_trip():
    srv, base = start_server()
    run_dir = tempfile.mkdtemp(prefix="fetchpage-")
    try:
        throttle = cv.HostThrottle((0.0, 0.0))
        r = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched", r
        with open(r["path"], encoding="utf-8") as f:
            cached = f.read()

        # wrapping does not change the text
        body_lines = cached.split("\n\n", 1)[1]
        expected = cv.normalize_text(cv.html_to_text(PAGE_HTML, "utf-8"))
        assert re.sub(r"\s+", "", body_lines) == re.sub(r"\s+", "", expected), "wrapping altered the body"
        assert "color:red" not in cached, "style contents leaked into the body"

        # a quote taken from one cache line passes the match against the live body
        line = next(l for l in body_lines.splitlines() if "101.6 billion yen" in l)
        quote = line.strip()[:60]
        status, detail = cv.check_quote_match(quote, expected)
        assert status == "found", f"a quote from the cache did not match: {status} {detail}"

        # the second fetch returns the cache
        again = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert again["status"] == "cached", again

        # pages whose body cannot be taken are not cached
        pdf = fp.fetch_one(f"{base}/pdf", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert pdf["status"] == "unsupported" and pdf["path"] is None, pdf
        thin = fp.fetch_one(f"{base}/thin", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert thin["status"] == "thin" and thin["path"] is None, thin

        index_path = fp.update_index(run_dir, [r, pdf, thin])
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        assert list(index) == [f"{base}/page"], f"an unfetched URL reached the index: {index}"

        print(f"[1] quote match found ({detail}); wrapping non-destructive; PDF and thin bodies "
              "fall back; second fetch cached")
    finally:
        srv.shutdown()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_wrap_width():
    s = "a" * 1000
    wrapped = fp.wrap_text(s, 200)
    assert max(len(l) for l in wrapped.splitlines()) <= 200, "a line exceeded the wrap width"
    assert re.sub(r"\s+", "", wrapped) == s
    print("[2] a body with no break characters keeps the width and loses no character")


if __name__ == "__main__":
    test_fetch_and_quote_round_trip()
    test_wrap_width()
    print("all passed")
