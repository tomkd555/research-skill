#!/usr/bin/env python3
"""Regression checks for the parallelism in citation_verifier.py.

1. Drive every online path through a stub and confirm --workers 1 and --workers 8 agree
2. Drive a local HTTP server and confirm the per-host throttle holds (the spacing between
   requests to one host, and the overlap between requests to different hosts)
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")
sys.path.insert(0, SKILL_SCRIPTS)  # fetch_page.py (loaded in test_local_file_quote_offline) imports citation_verifier


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cv = load(os.path.join(SKILL_SCRIPTS, "citation_verifier.py"), "cv_new")

# ------------------------------------------------------------- 1. determinism of every path

RESPONSES = {
    # (host_marker, method) -> (status, body, ctype, err)
    "ok-head": (200, b"<html><body>alpha beta gamma delta epsilon zeta eta theta</body></html>", "utf-8", None),
}


def make_stub(calls):
    real_sleep = time.sleep

    def stub(url, timeout, method="GET", throttle=None):
        ctx = throttle.slot(url) if throttle is not None else None
        if ctx is not None:
            ctx.__enter__()
        try:
            calls.append((url, method))
            real_sleep(0.002)  # stand in for the network wait
            if "api.crossref.org" in url:
                if "10.9999" in url:
                    return 404, None, None, "HTTP Error 404"
                if "10.5555" in url:
                    return 500, None, None, "HTTP Error 500"
                return 200, b'{"status":"ok"}', "utf-8", None
            if "doi.org/ra/" in url:
                if "10.9999" in url:
                    return 200, b'[{"DOI":"10.9999/x"}]', "utf-8", None  # no RA -> not_found
                return 200, b'[{"DOI":"x","RA":"DataCite"}]', "utf-8", None
            if "export.arxiv.org" in url:
                if "9999.99999" in url:
                    return 200, b"<opensearch:totalResults>0</opensearch:totalResults>", "utf-8", None
                return 200, b"<opensearch:totalResults>1</opensearch:totalResults><entry></entry>", "utf-8", None
            if "archive.org" in url:
                return 200, b'{"archived_snapshots":{"closest":{"available":true,"url":"http://web.archive.org/x","timestamp":"2020"}}}', "utf-8", None
            if "nohead.example" in url:
                if method == "HEAD":
                    return 405, None, None, "HTTP Error 405"
                return 200, b"<html>alpha beta gamma delta epsilon zeta eta theta</html>", "utf-8", None
            if "dead.example" in url:
                return None, None, None, "URLError"
            if "quotefail.example" in url:
                return 200, b"<html>totally unrelated content here</html>", "utf-8", None
            return 200, b"<html>alpha beta gamma delta epsilon zeta eta theta</html>", "utf-8", None
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)

    return stub


def build_log(n=40):
    ev = []
    variants = [
        ("https://ok{}.example/a", "alpha beta gamma delta", "10.1234/ok{}", None),
        ("https://nohead{}.example/a", "alpha beta gamma delta", None, None),
        ("https://dead{}.example/a", "alpha beta gamma delta", None, None),
        ("https://quotefail{}.example/a", "alpha beta gamma delta", None, None),
        ("https://ok{}.example/b", "alpha beta gamma delta", "10.9999/bad{}", None),
        ("https://ok{}.example/c", "alpha beta gamma delta", "10.5555/err{}", None),
        ("https://ok{}.example/d", "alpha beta gamma delta", None, "9999.99999"),
        ("https://ok{}.example/e", "alpha beta gamma delta", None, "2402.14207"),
    ]
    for i in range(n):
        url, quote, doi, ax = variants[i % len(variants)]
        ev.append({
            "id": f"E{i + 1}",
            "claim": "x",
            "verbatim_quote": quote,
            "source": {
                "url": url.format(i),
                **({"doi": doi.format(i)} if doi else {}),
                **({"arxiv_id": ax} if ax else {}),
            },
        })
    return {"evidence": ev}


def test_determinism():
    log = build_log(40)
    orig = cv.http_request
    outs = []
    try:
        for run_idx in range(20):
            for workers in (1, 8):
                calls = []
                cv.http_request = make_stub(calls)
                cv.REQUEST_INTERVAL = (0.0, 0.0)  # drop the wait for the determinism check
                out = cv.run(log, None, 5.0, False, workers)
                outs.append((workers, json.dumps(out, ensure_ascii=False, sort_keys=True)))
    finally:
        cv.http_request = orig
        cv.REQUEST_INTERVAL = (0.5, 1.0)

    baseline = outs[0][1]
    mismatches = [w for w, s in outs if s != baseline]
    ids = [r["id"] for r in json.loads(baseline)["results"]]
    assert ids == [f"E{i + 1}" for i in range(40)], f"the order broke: {ids[:5]}"
    assert not mismatches, \
        f"{len(mismatches)}/{len(outs)} outputs disagree (workers={set(mismatches)})"
    summary = json.loads(baseline)
    print(f"[1] determinism: all {len(outs)} runs agree (20 rounds x workers 1 and 8), "
          f"ordered by evidence ID. verdict={summary['verdict']} "
          f"CRITICAL={summary['critical_count']} WARN={summary['warn_count']}")


# ------------------------------------------------------------------ 1b. fewer HTTP requests

def test_no_head_when_body_needed():
    """Evidence carrying a quote gets a GET only, never a HEAD."""
    log = {"evidence": [
        {"id": "E1", "verbatim_quote": "alpha beta gamma delta",
         "source": {"url": "https://ok1.example/a"}},
        {"id": "E2", "verbatim_quote": "alpha beta gamma delta",
         "source": {"url": "https://ok2.example/a"}},
        {"id": "E3", "verbatim_quote": "",
         "source": {"url": "https://ok3.example/a"}},
    ]}
    orig = cv.http_request
    calls = []
    try:
        cv.http_request = make_stub(calls)
        cv.REQUEST_INTERVAL = (0.0, 0.0)
        out = cv.run(log, None, 5.0, False, 4)
    finally:
        cv.http_request = orig
        cv.REQUEST_INTERVAL = (0.5, 1.0)

    quoted = [m for u, m in calls if "ok1.example" in u or "ok2.example" in u]
    unquoted = [m for u, m in calls if "ok3.example" in u]
    assert quoted == ["GET", "GET"], f"a HEAD went out for evidence carrying a quote: {quoted}"
    assert unquoted == ["HEAD"], f"a GET went out for evidence carrying no quote: {unquoted}"
    assert all(r["url_status"] == "reachable" for r in out["results"]), \
        f"the reachability verdict changed: {[r['url_status'] for r in out['results']]}"
    print(f"[1b] request methods: 2 with a quote={quoted}, 1 without={unquoted}, "
          f"{len(calls)} requests in total (HEAD plus GET would make 5)")


def test_throttle_does_not_chain_response_time():
    """The wait on a host does not chain onto the response time of the request ahead of it."""
    real_sleep = time.sleep

    def slow_stub(url, timeout, method="GET", throttle=None):
        ctx = throttle.slot(url) if throttle is not None else None
        if ctx is not None:
            ctx.__enter__()
        try:
            real_sleep(0.5)  # stand in for a host that answers slowly
            return 200, b"<html>alpha beta gamma delta epsilon</html>", "utf-8", None
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)

    log = {"evidence": [
        {"id": f"E{i}", "verbatim_quote": "alpha beta gamma delta",
         "source": {"url": f"https://slow.example/{i}"}} for i in range(6)]}
    orig = cv.http_request
    try:
        cv.http_request = slow_stub
        cv.REQUEST_INTERVAL = (0.5, 0.5)
        t0 = time.monotonic()
        cv.run(log, None, 5.0, False, 8)
        elapsed = time.monotonic() - t0
    finally:
        cv.http_request = orig
        cv.REQUEST_INTERVAL = (0.5, 1.0)

    # The spacing counts from the start of each request: the last start at 2.5s plus a
    # 0.5s response is about 3.0s. Counting from completion gives 6 x (0.5 + 0.5) = 6.0s.
    assert elapsed < 4.5, f"the response time chained onto the wait: {elapsed:.2f}s"
    print(f"[1c] 6 requests to a host answering in 0.5s: {elapsed:.2f}s "
          f"(counting from completion would take 6.0s or more)")


# ----------------------------------------------------------- 2. the throttle in real traffic

ACCESS_LOG = []
LOG_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _record(self):
        host = self.headers.get("Host", "").split(":")[0]
        with LOG_LOCK:
            ACCESS_LOG.append((host, time.monotonic()))

    def do_HEAD(self):
        self._record()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        self._record()
        body = "<html>alpha beta gamma delta epsilon zeta eta theta</html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_throttle():
    # Listen on every interface, because the cross-host check also uses 127.0.0.2.
    # localhost is avoided: it resolves to ::1 first, and the connection to an IPv4-only
    # server then fails.
    srv = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # (a) 10 requests to one host -> consecutive accesses stay at least the minimum apart
        ACCESS_LOG.clear()
        log = {"evidence": [
            {"id": f"E{i}", "verbatim_quote": "alpha beta gamma delta",
             "source": {"url": f"http://127.0.0.1:{port}/p{i}"}} for i in range(10)]}
        cv.run(log, None, 5.0, False, 8)
        same = sorted(ts for h, ts in ACCESS_LOG if h == "127.0.0.1")
        gaps = [b - a for a, b in zip(same, same[1:])]
        min_gap = min(gaps)
        assert min_gap >= cv.REQUEST_INTERVAL[0] * 0.95, \
            f"the interval between requests to one host was not held: minimum {min_gap:.3f}s"
        print(f"[2a] one host: {len(same)} accesses, smallest gap {min_gap:.3f}s "
              f"(the rule asks for {cv.REQUEST_INTERVAL[0]}s or more)")

        # (b) split across 2 hosts -> the access windows overlap in time
        ACCESS_LOG.clear()
        log2 = {"evidence": []}
        for i in range(6):
            host = "127.0.0.1" if i % 2 == 0 else "127.0.0.2"
            log2["evidence"].append(
                {"id": f"E{i}", "verbatim_quote": "alpha beta gamma delta",
                 "source": {"url": f"http://{host}:{port}/q{i}"}})
        t0 = time.monotonic()
        cv.run(log2, None, 5.0, False, 8)
        elapsed = time.monotonic() - t0
        a = [ts for h, ts in ACCESS_LOG if h == "127.0.0.1"]
        b = [ts for h, ts in ACCESS_LOG if h == "127.0.0.2"]
        assert a and b, f"one of the two hosts was never accessed: {len(a)} / {len(b)}"
        overlap = min(max(a), max(b)) - max(min(a), min(b))
        assert overlap > 0, "the two hosts were accessed one after the other, not in parallel"
        serial_est = (len(a) + len(b)) * cv.REQUEST_INTERVAL[0]
        assert elapsed < serial_est, \
            f"the elapsed {elapsed:.2f}s did not beat the serial floor of {serial_est:.2f}s"
        print(f"[2b] two hosts: 127.0.0.1={len(a)} / 127.0.0.2={len(b)}, "
              f"overlap {overlap:.2f}s, total {elapsed:.2f}s "
              f"(serial would take {serial_est:.2f}s or more)")
    finally:
        srv.shutdown()


def test_quote_match_is_independent_of_offset():
    """The quote verdict does not depend on where in the page the quote sits.

    The earlier implementation stepped its window by the quote length, so the offset
    between window and quote was charged against the similarity: the same quote in the
    same body flipped between found and not_found when it moved by three characters.
    """
    quote = ("Domestic RPA market revenue reached 100 billion yen in fiscal 2025, "
             "research firm X estimates")
    filler = "Elsewhere the editorial staff attended briefings all afternoon and kept notes. "
    altered = quote.replace("100 billion", "100billion")   # one character of spelling variance
    verdicts = {}
    for pad in range(0, 22, 3):
        body = filler * 4 + "x" * pad + altered + filler * 4
        verdicts[pad] = cv.check_quote_match(quote, body)[0]
    assert set(verdicts.values()) == {"found"}, f"the verdict moved with the offset: {verdicts}"

    # a paraphrase (four words replaced) stays a mismatch
    paraphrased = (filler * 4
                   + quote.replace("research firm X estimates", "several analysts now expect")
                   + filler * 4)
    assert cv.check_quote_match(quote, paraphrased)[0] == "not_found", "a paraphrase came back found"

    # when the body was cut at the fetch limit, a mismatch is a failed fetch, not a fabrication
    assert cv.check_quote_match(quote, filler * 4, truncated=True)[0] == "unfetchable"
    print(f"[3] the verdict holds across offsets of 0-21 characters ({set(verdicts.values())}); "
          "a paraphrase is not_found; a cut body is unfetchable")


def test_local_file_quote_offline():
    """A file:// source verifies from fetch_page.py's local cache with no network, even
    under --offline: a local check costs no network, so the flag lets it run anyway.
    A missing cache file reports WARN through the normal unreachable/unfetchable path."""
    fp_path = os.path.join(SKILL_SCRIPTS, "fetch_page.py")
    fp_spec = importlib.util.spec_from_file_location("fp_for_cv", fp_path)
    fp = importlib.util.module_from_spec(fp_spec)
    fp_spec.loader.exec_module(fp)

    tmpdir = tempfile.mkdtemp(prefix="localcv-")
    try:
        run_dir = os.path.join(tmpdir, "run")
        content = ("Filler text ahead of the figure gives background and methodology. " * 6
                   + "Domestic RPA market revenue reached 100 billion yen in fiscal 2025, "
                     "research firm X estimates."
                   + " Filler text after the figure carries the discussion further." * 6)
        src_path = os.path.join(tmpdir, "material.txt")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(content)
        ingested = fp.ingest_one(src_path, run_dir)
        assert ingested["status"] == "ingested", ingested
        pages_dir = os.path.join(run_dir, "pages")

        log = {"evidence": [{
            "id": "E1",
            "verbatim_quote": "Domestic RPA market revenue reached 100 billion yen in fiscal 2025",
            "source": {"url": ingested["url"], "doi": "10.1234/example"},
        }]}
        out = cv.run(log, None, 5.0, True, pages_dir=pages_dir)  # offline=True
        r1 = out["results"][0]
        assert r1["url_status"] == "local" and r1["quote_match"] == "found" \
            and r1["severity"] == "PASS", r1
        # a doi on a local source stays offline too: skipped, no Crossref request sent
        assert r1["doi_status"] == "skipped", r1

        missing_log = {"evidence": [{
            "id": "E2", "verbatim_quote": "anything",
            "source": {"url": "file:///C:/nonexistent/path/gone.txt"},
        }]}
        out2 = cv.run(missing_log, None, 5.0, True, pages_dir=pages_dir)
        r2 = out2["results"][0]
        assert r2["url_status"] == "unreachable" and r2["quote_match"] == "unfetchable" \
            and r2["severity"] == "WARN", r2

        print("[4] a local file:// source verifies offline (url_status=local, quote_match=found); "
              "a missing cache file comes back WARN (url_status=unreachable, quote_match=unfetchable)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_found_cached_when_live_differs():
    """A live re-fetch whose page hyphenates a word across a footnote break, unlike
    fetch_page.py's cached extraction, still verifies through the cache: the CRITICAL a
    plain not_found would raise never fires, and the result records found_cached."""
    quote = "Domestic RPA market revenue reached 100 billion yen in fiscal 2025"
    half = len(quote) // 2
    footnote = " [1] See methodology note on page 42 for the detailed breakdown of this figure. "
    live_text = ("Filler paragraph one keeps the page busy. " * 3
                + quote[:half] + "-" + footnote + quote[half:] + "."
                + " Filler paragraph two closes things out." * 3)
    cached_text = ("Filler paragraph one keeps the page busy. " * 3
                  + quote + "."
                  + " Filler paragraph two closes things out." * 3)
    assert cv.check_quote_match(quote, live_text)[0] == "not_found", \
        "test setup is broken: the live text should already fail a plain match"

    class LiveHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"<html>{live_text}</html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), LiveHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    tmpdir = tempfile.mkdtemp(prefix="cvcache-")
    try:
        url = f"http://127.0.0.1:{port}/report"
        pages_dir = os.path.join(tmpdir, "pages")
        os.makedirs(pages_dir)
        with open(os.path.join(pages_dir, cv.cache_name(url)), "w", encoding="utf-8") as f:
            f.write(cached_text)

        log = {"evidence": [{"id": "E1", "verbatim_quote": quote, "source": {"url": url}}]}
        out = cv.run(log, None, 5.0, False, pages_dir=pages_dir)
        r = out["results"][0]
        assert r["quote_match"] == "found_cached" and r["severity"] == "PASS", r
        assert "cache" in r["detail"], r["detail"]

        print("[5] a live page differing from the cache (a hyphen break across a footnote) "
              f"still verifies through it: quote_match={r['quote_match']} "
              f"severity={r['severity']}")
    finally:
        srv.shutdown()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_determinism()
    test_no_head_when_body_needed()
    test_throttle_does_not_chain_response_time()
    test_throttle()
    test_quote_match_is_independent_of_offset()
    test_local_file_quote_offline()
    test_found_cached_when_live_differs()
    print("all passed")
