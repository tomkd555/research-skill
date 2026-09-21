#!/usr/bin/env python3
"""Checks for fetch_page.py.

1. A quote taken from the cache passes citation_verifier's match against the live body
2. Wrapping does not change the text (identical once whitespace is removed)
3. A web PDF is cached through its text layer (pypdf) like an HTML page; a thin body is not
4. A second fetch returns the cache (the no-duplicate-fetch rule held by the path itself)
5. A local .txt/.docx/.pdf file ingests, quote-matches, and caches on a second ingest
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import zipfile
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

try:
    import pypdf  # noqa: F401  (only probed for; fp.pdf_text does the real import)
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False

SENTENCE = ("Research firm X puts the domestic generative AI market at 101.6 billion yen for fiscal 2025. "
            "The same report puts the 2026 forecast at 148.0 billion yen, a 45.7% increase.")
PAGE_HTML = ("<html><head><style>.x{color:red}</style></head><body><p>"
             + "An introductory passage sits ahead of the figure. " * 20 + SENTENCE
             + " Supplementary passages follow the figure. " * 20 + "</p></body></html>").encode("utf-8")


def build_minimal_pdf(text):
    """A hand-built, valid one-page PDF whose content stream is a single Tj of `text`
    (no parentheses/backslashes in `text`). No dependency beyond stdlib to build it."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = ("BT /F1 12 Tf 72 712 Td (%s) Tj ET" % text).encode("latin-1")
    objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += ("xref\n0 %d\n" % (len(objects) + 1)).encode() + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (len(objects) + 1, xref_offset)).encode()
    return bytes(out)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/page":
            body, ctype = PAGE_HTML, "text/html; charset=utf-8"
        elif self.path == "/pdf":
            body, ctype = build_minimal_pdf(SENTENCE * 3), "application/pdf"
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

        # a web PDF goes through the same text-layer extraction as fetch_page.py's local
        # ingest, so it is cached like a page when pypdf is importable
        pdf = fp.fetch_one(f"{base}/pdf", run_dir, 10, fp.MIN_CHARS, False, throttle)
        if HAVE_PYPDF:
            assert pdf["status"] == "fetched" and pdf["path"], pdf
            with open(pdf["path"], encoding="utf-8") as f:
                pdf_cached = f.read()
            assert "101.6 billion yen" in pdf_cached, "the PDF text layer did not reach the cache"
        else:
            assert pdf["status"] == "unsupported" and pdf["path"] is None, pdf

        # a thin body is not cached
        thin = fp.fetch_one(f"{base}/thin", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert thin["status"] == "thin" and thin["path"] is None, thin

        index_path = fp.update_index(run_dir, [r, pdf, thin])
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        expected_urls = {f"{base}/page"} | ({f"{base}/pdf"} if HAVE_PYPDF else set())
        assert set(index) == expected_urls, f"the index does not match what was cached: {index}"

        print(f"[1] quote match found ({detail}); wrapping non-destructive; "
              f"PDF {'cached via pypdf' if HAVE_PYPDF else 'unsupported (pypdf not importable)'}; "
              "thin body not cached; second fetch cached")
    finally:
        srv.shutdown()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_wrap_width():
    s = "a" * 1000
    wrapped = fp.wrap_text(s, 200)
    assert max(len(l) for l in wrapped.splitlines()) <= 200, "a line exceeded the wrap width"
    assert re.sub(r"\s+", "", wrapped) == s
    print("[2] a body with no break characters keeps the width and loses no character")


def assert_local_round_trip(path, expected_text, run_dir, label):
    """One local file: ingest, a cache-line quote matches the source text, then cached."""
    r = fp.ingest_one(path, run_dir)
    assert r["status"] == "ingested" and r["path"], r
    assert r["url"] == fp.canonical_file_url(path), r["url"]
    with open(r["path"], encoding="utf-8") as f:
        cached = f.read()
    body_lines = cached.split("\n\n", 1)[1]
    line = next(l for l in body_lines.splitlines() if "101.6 billion yen" in l)
    quote = line.strip()[:60]
    status, detail = cv.check_quote_match(quote, cv.normalize_text(expected_text))
    assert status == "found", f"{label}: a quote from the cache did not match: {status} {detail}"

    again = fp.ingest_one(path, run_dir)
    assert again["status"] == "cached", f"{label}: {again}"
    print(f"    {label}: ingested, quote matched ({detail}), second ingest cached")


def test_local_ingest():
    tmpdir = tempfile.mkdtemp(prefix="localmat-")
    run_dir = os.path.join(tmpdir, "run")
    try:
        filler = "Filler text discussing background and methodology in some depth. " * 6
        txt_content = filler + SENTENCE + " " + filler
        txt_path = os.path.join(tmpdir, "market.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        assert_local_round_trip(txt_path, txt_content, run_dir, ".txt")

        paragraphs = (["Filler paragraph before the figure gives background and methodology."] * 4
                      + [SENTENCE]
                      + ["Filler paragraph after the figure continues with further analysis."] * 4)
        docx_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>" + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
            + "</w:body></w:document>")
        docx_path = os.path.join(tmpdir, "material.docx")
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", docx_xml)
        assert_local_round_trip(docx_path, "\n".join(paragraphs), run_dir, ".docx")

        if HAVE_PYPDF:
            pdf_path = os.path.join(tmpdir, "material.pdf")
            with open(pdf_path, "wb") as f:
                f.write(build_minimal_pdf(SENTENCE * 3))
            assert_local_round_trip(pdf_path, SENTENCE * 3, run_dir, ".pdf")
        else:
            print("    .pdf: skipped (pypdf not importable in this environment)")

        print(f"[3] local ingest round-trips for .txt, .docx"
              f"{' and .pdf' if HAVE_PYPDF else ''} (cache key = canonical file:// URL)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_local_ingest_errors_and_force():
    tmpdir = tempfile.mkdtemp(prefix="localmat-err-")
    run_dir = os.path.join(tmpdir, "run")
    try:
        # a corrupt .docx raises inside extraction; ingest_one catches it and reports it
        broken_path = os.path.join(tmpdir, "broken.docx")
        with open(broken_path, "wb") as f:
            f.write(b"this is a plain file wearing a .docx extension")
        broken = fp.ingest_one(broken_path, run_dir)
        assert broken["status"] == "unreadable" and broken["path"] is None, broken
        assert broken["detail"], "the exception text should be carried in detail"
        print(f"    corrupt .docx: unreadable ({broken['detail']})")

        # a second, healthy target still ingests after the corrupt one, in the same batch
        ok_path = os.path.join(tmpdir, "healthy.txt")
        healthy_content = "Filler background material for the run. " * 20 + SENTENCE
        with open(ok_path, "w", encoding="utf-8") as f:
            f.write(healthy_content)
        ok = fp.ingest_one(ok_path, run_dir)
        assert ok["status"] == "ingested", ok
        index_path = fp.update_index(run_dir, [broken, ok])
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        assert list(index) == [ok["url"]], f"the failed target should be left out of the index: {index}"

        # --force re-extracts a file that changed since it was first ingested
        changing_path = os.path.join(tmpdir, "changing.txt")
        original = "Background filler for the changing case. " * 20 + SENTENCE
        with open(changing_path, "w", encoding="utf-8") as f:
            f.write(original)
        first = fp.ingest_one(changing_path, run_dir)
        assert first["status"] == "ingested", first

        newer_sentence = SENTENCE.replace("101.6 billion yen", "212.4 billion yen")
        updated = "Background filler for the changing case. " * 20 + newer_sentence
        with open(changing_path, "w", encoding="utf-8") as f:
            f.write(updated)

        stale = fp.ingest_one(changing_path, run_dir)
        assert stale["status"] == "cached", stale
        with open(stale["path"], encoding="utf-8") as f:
            assert "101.6 billion yen" in f.read(), "the cache should still hold the old figure here"

        refreshed = fp.ingest_one(changing_path, run_dir, force=True)
        assert refreshed["status"] == "ingested", refreshed
        with open(refreshed["path"], encoding="utf-8") as f:
            refreshed_body = f.read()
        assert "212.4 billion yen" in refreshed_body, "force should pick up the file's new content"
        assert "101.6 billion yen" not in refreshed_body, "the old figure should be gone after force"
        print("    --force: a changed file re-ingests and the cache carries the new figure")

        print("[4] a corrupt .docx is reported as unreadable, leaves its batch, and force re-extracts")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_fetch_and_quote_round_trip()
    test_wrap_width()
    test_local_ingest()
    test_local_ingest_errors_and_force()
    print("all passed")
