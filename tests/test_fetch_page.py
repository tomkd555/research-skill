#!/usr/bin/env python3
"""Checks for fetch_page.py.

1. A quote taken from the cache passes citation_verifier's match against the live body
2. Wrapping does not change the text (identical once whitespace is removed)
3. A web PDF is cached through its text layer (pypdf) like an HTML page; a thin body is not
4. A second fetch returns the cache (the no-duplicate-fetch rule held by the path itself)
5. A local .txt/.docx/.pdf file ingests, quote-matches, and caches on a second ingest
"""
import contextlib
import email.message
import importlib.util
import io
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


@contextlib.contextmanager
def fetch_env():
    srv, base = start_server()
    run_dir = tempfile.mkdtemp(prefix="fetchpage-")
    try:
        yield base, run_dir, cv.HostThrottle((0.0, 0.0))
    finally:
        srv.shutdown()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_fetch_one_html_wrapping_text_unchanged():
    with fetch_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched", r
        with open(r["path"], encoding="utf-8") as f:
            cached = f.read()

        body_lines = cached.split("\n\n", 1)[1]
        expected = cv.normalize_text(cv.html_to_text(PAGE_HTML, "utf-8"))
        assert re.sub(r"\s+", "", body_lines) == re.sub(r"\s+", "", expected), "wrapping altered the body"
        assert "color:red" not in cached, "style contents leaked into the body"
        print("[1] wrapping non-destructive; style contents stay out of the body")


def test_fetch_one_cache_quote_matches_live_body():
    with fetch_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        with open(r["path"], encoding="utf-8") as f:
            cached = f.read()
        body_lines = cached.split("\n\n", 1)[1]
        expected = cv.normalize_text(cv.html_to_text(PAGE_HTML, "utf-8"))

        # a quote taken from one cache line passes the match against the live body
        line = next(l for l in body_lines.splitlines() if "101.6 billion yen" in l)
        quote = line.strip()[:60]
        status, detail = cv.check_quote_match(quote, expected)
        assert status == "found", f"a quote from the cache did not match: {status} {detail}"
        print(f"[2] quote match found ({detail})")


def test_fetch_one_second_fetch_returns_cached():
    with fetch_env() as (base, run_dir, throttle):
        fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        again = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert again["status"] == "cached", again
        print("[3] second fetch cached")


def test_fetch_one_web_pdf_cached_via_text_layer():
    with fetch_env() as (base, run_dir, throttle):
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
        print(f"[4] PDF {'cached via pypdf' if HAVE_PYPDF else 'unsupported (pypdf not importable)'}")


def test_fetch_one_thin_body_not_cached():
    with fetch_env() as (base, run_dir, throttle):
        thin = fp.fetch_one(f"{base}/thin", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert thin["status"] == "thin" and thin["path"] is None, thin
        print("[5] thin body not cached")


def test_update_index_lists_cached_urls_only():
    with fetch_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        pdf = fp.fetch_one(f"{base}/pdf", run_dir, 10, fp.MIN_CHARS, False, throttle)
        thin = fp.fetch_one(f"{base}/thin", run_dir, 10, fp.MIN_CHARS, False, throttle)
        index_path = fp.update_index(run_dir, [r, pdf, thin])
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        expected_urls = {f"{base}/page"} | ({f"{base}/pdf"} if HAVE_PYPDF else set())
        assert set(index) == expected_urls, f"the index does not match what was cached: {index}"
        print("[6] the index holds the cached pages and leaves the thin one out")


def test_wrap_text_unbroken_body_wraps_at_width():
    s = "a" * 1000
    wrapped = fp.wrap_text(s, 200)
    assert max(len(l) for l in wrapped.splitlines()) <= 200, "a line exceeded the wrap width"
    assert re.sub(r"\s+", "", wrapped) == s
    print("[7] a body with no break characters keeps the width and loses no character")


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


def test_ingest_one_txt_docx_pdf_round_trip():
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

        print(f"[8] local ingest round-trips for .txt, .docx"
              f"{' and .pdf' if HAVE_PYPDF else ''} (cache key = canonical file:// URL)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_ingest_one_corrupt_docx_unreadable():
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

        print("[9] a corrupt .docx is reported as unreadable and leaves its batch")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_ingest_one_force_refreshes_changed_file():
    tmpdir = tempfile.mkdtemp(prefix="localmat-force-")
    run_dir = os.path.join(tmpdir, "run")
    try:
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

        print("[10] force re-extracts a changed file")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


DOCX_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRIP_SECONDS = 6.0


def build_docx_bytes(text):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml",
                    f'<w:document xmlns:w="{DOCX_W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
                    "</w:body></w:document>")
    return buf.getvalue()


class ExtraHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        import gzip
        import time
        extra = {}
        if self.path == "/gzip":
            body, ctype = gzip.compress(PAGE_HTML), "text/html; charset=utf-8"
            extra["Content-Encoding"] = "gzip"
        elif self.path == "/plain":
            body = ("If a<b and b>c then the rule <applies> here. " * 12).encode("utf-8")
            ctype = "text/plain; charset=utf-8"
        elif self.path == "/docx":
            body = build_docx_bytes(SENTENCE * 3)
            ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif self.path == "/png":
            body, ctype = b"\x89PNG\r\n\x1a\n" + b"\x00" * 600, "image/png"
        elif self.path == "/inline":
            body = ("<html><body><p>" + "国内の<strong>生成</strong>AI市場は拡大している。 " * 20
                    + "See <a href=x>Images of Text</a>. " * 20 + "</p></body></html>").encode("utf-8")
            ctype = "text/html; charset=utf-8"
        elif self.path == "/drip":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                end = time.monotonic() + DRIP_SECONDS
                while time.monotonic() < end:
                    self.wfile.write(b"<p>slow drip of text</p>")
                    self.wfile.flush()
                    time.sleep(0.3)
            except OSError:
                pass
            return
        else:
            body, ctype = b"missing", "text/plain"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@contextlib.contextmanager
def extra_env():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ExtraHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    run_dir = tempfile.mkdtemp(prefix="fetchpage-x-")
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", run_dir, cv.HostThrottle((0.0, 0.0))
    finally:
        srv.shutdown()
        shutil.rmtree(run_dir, ignore_errors=True)


def cache_body(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n\n", 1)[1]


def test_wrap_text_decimal_number_not_split():
    s = "a" * 195 + " 1,200.5 " + "b" * 100
    lines = fp.wrap_text(s, 200).splitlines()
    assert any("1,200.5" in l for l in lines), lines


def test_wrap_text_fixed_cut_inside_number_moves_to_run_end():
    s = "あ" * 198 + "26.5%増" + "い" * 50
    lines = fp.wrap_text(s, 200).splitlines()
    assert any("26.5%" in l for l in lines), lines


def test_wrap_text_japanese_period_breaks_after_it():
    s = "あ" * 150 + "。" + "い" * 100
    first = fp.wrap_text(s, 200).splitlines()[0]
    assert first.endswith("。"), first[-5:]


def test_fetch_one_inline_tags_join_without_space():
    with extra_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/inline", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched", r
        body = re.sub(r"\s+", "", cache_body(r["path"]))
        assert "国内の生成AI市場は" in body and "ImagesofText." in body, body[:80]
        assert "Images of Text ." not in cache_body(r["path"])


def test_fetch_one_pdf_over_cap_unsupported():
    cvm = sys.modules["citation_verifier"]
    saved = getattr(cvm, "PDF_MAX_BYTES", None)
    cvm.PDF_MAX_BYTES = 500
    try:
        with fetch_env() as (base, run_dir, throttle):
            r = fp.fetch_one(f"{base}/pdf", run_dir, 10, fp.MIN_CHARS, False, throttle)
            assert r["status"] == "unsupported" and r["detail"] == "PDF larger than 50 MB", r
    finally:
        if saved is not None:
            cvm.PDF_MAX_BYTES = saved


def test_write_cache_existing_file_intact_until_replace():
    run_dir = tempfile.mkdtemp(prefix="fetchpage-w-")
    try:
        path = os.path.join(run_dir, "pages", "x.txt")
        fp._write_cache(path, "http://example.com/x", "old body")
        seen = []
        real = fp.wrap_text

        def spy(t, *a):
            with open(path, encoding="utf-8") as f:
                seen.append(f.read())
            return real(t, *a)

        fp.wrap_text = spy
        try:
            fp._write_cache(path, "http://example.com/x", "new body")
        finally:
            fp.wrap_text = real
        assert "old body" in seen[0], "the cache file was truncated before the new text was ready"
        assert os.listdir(os.path.dirname(path)) == ["x.txt"], "a temporary file was left behind"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_update_index_rebuilds_from_cache_headers():
    run_dir = tempfile.mkdtemp(prefix="fetchpage-i-")
    try:
        for u in ("http://example.com/a", "http://example.com/b"):
            fp._write_cache(os.path.join(run_dir, "pages", cv.cache_name(u)), u, "text " * 100)
        with open(os.path.join(run_dir, "pages", "index.json"), "w") as f:
            f.write("{broken")
        index_path = fp.update_index(run_dir, [])
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        assert set(index) == {"http://example.com/a", "http://example.com/b"}, index
        assert index["http://example.com/a"] == {"path": cv.cache_name("http://example.com/a"), "chars": 500}
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_fetch_one_slow_drip_response_times_out():
    import time
    with extra_env() as (base, run_dir, throttle):
        t0 = time.monotonic()
        r = fp.fetch_one(f"{base}/drip", run_dir, 1, fp.MIN_CHARS, False, throttle)
        elapsed = time.monotonic() - t0
        assert r["status"] == "unreachable" and elapsed < DRIP_SECONDS - 1.5, (r, elapsed)


def test_fetch_one_gzip_body_decompressed():
    with extra_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/gzip", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched" and "101.6 billion yen" in cache_body(r["path"]), r


def test_fetch_one_text_plain_keeps_angle_brackets():
    with extra_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/plain", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched" and "a<b and b>c then the rule <applies>" in cache_body(r["path"]), r


def test_fetch_one_docx_body_extracted():
    with extra_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/docx", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "fetched" and "101.6 billion yen" in cache_body(r["path"]), r


def test_fetch_one_image_type_unsupported():
    with extra_env() as (base, run_dir, throttle):
        r = fp.fetch_one(f"{base}/png", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert r["status"] == "unsupported" and "image/png" in r["detail"], r


def test_fetch_one_cached_chars_match_fresh_fetch():
    with fetch_env() as (base, run_dir, throttle):
        fresh = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        again = fp.fetch_one(f"{base}/page", run_dir, 10, fp.MIN_CHARS, False, throttle)
        assert again["status"] == "cached" and again["chars"] == fresh["chars"], (fresh, again)


def test_ingest_one_cached_chars_match_fresh_ingest():
    run_dir = tempfile.mkdtemp(prefix="fetchpage-c-")
    try:
        src = os.path.join(run_dir, "note.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(SENTENCE * 3)
        fresh = fp.ingest_one(src, run_dir)
        again = fp.ingest_one(src, run_dir)
        assert again["status"] == "cached" and again["chars"] == fresh["chars"], (fresh, again)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_body_text_no_content_type_html_tags_removed():
    text, err = fp.body_text(b"<html><body><p>Revenue <b>rose</b> 5%</p></body></html>",
                             email.message.Message())
    assert err is None and "<" not in text and "Revenue rose 5%" in text, (text, err)


def test_body_text_corrupt_docx_unsupported():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><unclosed>")
    text, err = fp.body_text(buf.getvalue(), None)
    assert text is None and "DOCX" in err, (text, err)


def test_body_text_crc_corrupt_docx_unreadable():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("word/document.xml", "<w:document>" + "x" * 200 + "</w:document>")
    raw = bytearray(buf.getvalue())
    raw[raw.index(b"xxxx")] ^= 0x01  # one flipped byte inside the stored entry fails its CRC
    text, err = fp.body_text(bytes(raw), None)
    assert text is None and "unreadable DOCX" in err, (text, err)


def test_body_text_pk_plain_text_decoded():
    headers = email.message.Message()
    headers["Content-Type"] = "text/plain; charset=utf-8"
    text, err = fp.body_text(b"PKCS #11 defines a platform-independent API.", headers)
    assert err is None and text.startswith("PKCS #11"), (text, err)


if __name__ == "__main__":
    test_wrap_text_decimal_number_not_split()
    test_wrap_text_fixed_cut_inside_number_moves_to_run_end()
    test_wrap_text_japanese_period_breaks_after_it()
    test_fetch_one_inline_tags_join_without_space()
    test_fetch_one_pdf_over_cap_unsupported()
    test_write_cache_existing_file_intact_until_replace()
    test_update_index_rebuilds_from_cache_headers()
    test_fetch_one_slow_drip_response_times_out()
    test_fetch_one_gzip_body_decompressed()
    test_fetch_one_text_plain_keeps_angle_brackets()
    test_fetch_one_docx_body_extracted()
    test_fetch_one_image_type_unsupported()
    test_fetch_one_cached_chars_match_fresh_fetch()
    test_ingest_one_cached_chars_match_fresh_ingest()
    test_fetch_one_html_wrapping_text_unchanged()
    test_fetch_one_cache_quote_matches_live_body()
    test_fetch_one_second_fetch_returns_cached()
    test_fetch_one_web_pdf_cached_via_text_layer()
    test_fetch_one_thin_body_not_cached()
    test_update_index_lists_cached_urls_only()
    test_wrap_text_unbroken_body_wraps_at_width()
    test_ingest_one_txt_docx_pdf_round_trip()
    test_ingest_one_corrupt_docx_unreadable()
    test_ingest_one_force_refreshes_changed_file()
    test_body_text_no_content_type_html_tags_removed()
    test_body_text_corrupt_docx_unsupported()
    test_body_text_crc_corrupt_docx_unreadable()
    test_body_text_pk_plain_text_decoded()
    print("all passed")
