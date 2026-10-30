#!/usr/bin/env python3
"""Offline self-check for paper_search.py: run `python test_paper_search.py`."""

import contextlib
import io
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "research-team", "skills", "literature-review", "scripts"))
import paper_search as ps


def test_from_inverted_index_orders_words_by_position():
    assert ps.from_inverted_index({"large": [1], "a": [0], "model": [2]}) == "a large model"


def test_from_inverted_index_none_returns_empty():
    assert ps.from_inverted_index(None) == ""


def test_norm_doi_url_form_returns_lowercase_doi():
    assert ps.norm_doi("https://doi.org/10.1145/ABC") == "10.1145/abc"


def test_record_arxiv_doi_sets_arxiv_id():
    arxiv = ps.record(title="t", doi="https://doi.org/10.48550/arXiv.2312.10997",
                      is_preprint=True)
    assert arxiv["arxiv_id"] == "2312.10997"


def test_grade_by_preprint_and_doi():
    arxiv = ps.record(title="t", doi="https://doi.org/10.48550/arXiv.2312.10997",
                      is_preprint=True)
    assert ps.grade(arxiv) == "B"
    published = ps.record(title="t", doi="10.1145/abc")
    assert ps.grade(published) == "A"
    assert ps.grade(ps.record(title="t")) == "C"


def test_canonical_url_by_doi_kind():
    arxiv = ps.record(title="t", doi="https://doi.org/10.48550/arXiv.2312.10997",
                      is_preprint=True)
    assert ps.canonical_url(arxiv) == "https://arxiv.org/abs/2312.10997"
    published = ps.record(title="t", doi="10.1145/abc")
    assert ps.canonical_url(published) == "https://doi.org/10.1145/abc"


def test_merge_all_arxiv_and_openalex_copies_collapse():
    """The same paper from arXiv and OpenAlex must collapse to one record."""
    from_arxiv = ps.record(title="Retrieval Augmented Generation Survey", arxiv_id="2312.10997v3",
                           is_preprint=True, abstract="short", sources=["arxiv"], year=2023)
    from_openalex = ps.record(title="Retrieval Augmented Generation Survey",
                              doi="https://doi.org/10.48550/arxiv.2312.10997", citations=696,
                              is_preprint=True, abstract="a much longer abstract here",
                              venue="arXiv", sources=["openalex"], year=2023)
    merged = ps.merge_all([from_arxiv, from_openalex])
    assert len(merged) == 1, merged
    assert merged[0]["citations"] == 696
    assert merged[0]["abstract"] == "a much longer abstract here"
    assert sorted(merged[0]["sources"]) == ["arxiv", "openalex"]


def test_merge_all_preprint_and_published_not_preprint():
    """A published version and a preprint of the same title merge, and stop counting as a preprint."""
    pair = ps.merge_all([
        ps.record(title="Attention Is All You Need Again", is_preprint=True, sources=["arxiv"]),
        ps.record(title="Attention Is All You Need Again", doi="10.5555/x", is_preprint=False,
                  sources=["openalex"]),
    ])
    assert len(pair) == 1 and pair[0]["is_preprint"] is False
    assert ps.grade(pair[0]) == "A"


def test_merge_all_distinct_titles_return_two():
    assert len(ps.merge_all([ps.record(title="Some Entirely Different Paper Title"),
                             ps.record(title="Another Wholly Unrelated Paper Title")])) == 2


def test_rank_orders_by_citations_descending():
    ranked = ps.rank([ps.record(title="a", citations=3), ps.record(title="b", citations=90)],
                     min_citations=1)
    assert [r["title"] for r in ranked] == ["b", "a"]


def test_rank_below_min_citations_returns_empty():
    assert ps.rank([ps.record(title="a", citations=3)], min_citations=10) == []


def test_cmd_check_fabricated_quote_returns_one():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "papers.json")
        ev = os.path.join(tmp, "evidence.json")
        with open(db, "w", encoding="utf-8") as fh:
            json.dump({"papers": [{"id": "P1", "abstract": "We show that RAG reduces  "
                                                           "hallucination by 30%."}]}, fh)
        with open(ev, "w", encoding="utf-8") as fh:
            json.dump([
                {"id": "E1", "paper": "P1", "quote": "RAG reduces hallucination by 30%"},
                {"id": "E2", "paper": "P1", "quote": "RAG eliminates hallucination entirely"},
                {"id": "E3", "paper": "P9", "quote": "anything"},
                {"id": "E4", "paper": "P1", "quote": "from page 7", "quote_source": "fulltext"},
            ], fh)
        args = ps.argparse.Namespace(db=db, evidence=ev)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ps.cmd_check(args)
        assert rc == 1  # E2 fabricated, E3 unknown paper; E1 and E4 pass
        assert "FAIL E2: quote is not in P1's abstract" in out.getvalue(), out.getvalue()


def _run_main(argv):
    """Run ps.main and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ps.main(argv)
    except SystemExit as exc:
        rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def _with_fetchers(fetchers, argv):
    saved = dict(ps.FETCHERS)
    ps.FETCHERS.update(fetchers)
    try:
        return _run_main(argv)
    finally:
        ps.FETCHERS.clear()
        ps.FETCHERS.update(saved)


def _boom(query, limit, year_from):
    raise OSError("network down")


def test_cmd_search_all_sources_fail_exits_two_db_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "papers.json")
        with open(db, "w", encoding="utf-8") as fh:
            fh.write('{"papers": [{"id": "P1"}]}')
        rc, out, err = _with_fetchers({"arxiv": _boom}, ["search", "q", "--db", db, "--source", "arxiv"])
        assert rc == 2, (rc, out, err)
        assert "network down" in err, err
        with open(db, encoding="utf-8") as fh:
            assert fh.read() == '{"papers": [{"id": "P1"}]}'


def test_cmd_search_one_source_fails_stdout_names_failed_source():
    ok = lambda query, limit, year_from: [ps.record(title="A Sufficiently Long Title", sources=["openalex"])]
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "papers.json")
        rc, out, err = _with_fetchers({"openalex": ok, "arxiv": _boom},
                                      ["search", "q", "--db", db, "--source", "openalex,arxiv"])
        assert rc == 0, (rc, out, err)
        assert "failed sources: arxiv" in out, out


def test_main_unknown_source_exits_two_message_on_stderr():
    rc, out, err = _run_main(["search", "q", "--source", "nope"])
    assert rc == 2 and "unknown source: nope" in err, (rc, err)


def test_main_show_missing_db_exits_two():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, err = _run_main(["show", "--db", os.path.join(tmp, "none.json"), "P1"])
    assert rc == 2 and "no such db" in err, (rc, err)


def test_main_check_malformed_evidence_exits_two():
    with tempfile.TemporaryDirectory() as tmp:
        db, ev = os.path.join(tmp, "papers.json"), os.path.join(tmp, "evidence.json")
        with open(db, "w", encoding="utf-8") as fh:
            fh.write('{"papers": []}')
        with open(ev, "w", encoding="utf-8") as fh:
            fh.write('{"id": "E1"}' + chr(10) + '{"id": "E2"}' + chr(10))
        rc, out, err = _run_main(["check", "--db", db, "--evidence", ev])
    assert rc == 2, (rc, err)


def test_cmd_search_completion_order_merges_in_submission_order():
    def slow(query, limit, year_from):
        time.sleep(0.3)
        return [ps.record(title="One Paper With A Long Title", venue="first", sources=["openalex"])]

    def fast(query, limit, year_from):
        return [ps.record(title="One Paper With A Long Title", venue="second", sources=["arxiv"])]

    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "papers.json")
        rc, out, err = _with_fetchers({"openalex": slow, "arxiv": fast},
                                      ["search", "q", "--db", db, "--source", "openalex,arxiv"])
        with open(db, encoding="utf-8") as fh:
            papers = json.load(fh)["papers"]
    assert rc == 0 and len(papers) == 1 and papers[0]["venue"] == "first", (rc, papers)


def test_merge_all_any_arrival_order_returns_one_record():
    import itertools
    journal = dict(title="Journal Version Of The Work", doi="10.1000/j.2024.1", sources=["openalex"])
    oa_pre = dict(title="Preprint Copy Under Another Title", doi="10.48550/arxiv.2401.00001",
                  is_preprint=True, sources=["openalex"])
    arxiv = dict(title="Arxiv Listing Of The Same Work", arxiv_id="2401.00001v2",
                 doi="10.1000/j.2024.1", sources=["arxiv"])
    for order in itertools.permutations((journal, oa_pre, arxiv)):
        merged = ps.merge_all([ps.record(**dict(r)) for r in order])
        assert len(merged) == 1, [m["title"] for m in order]
        assert merged[0]["doi"] == "10.1000/j.2024.1" and ps.grade(merged[0]) == "A"


def test_merge_all_joined_record_stale_key_merges_into_survivor():
    """A key indexed for a record that a later join removed still leads to the surviving record."""
    a = dict(title="First listing of work A", doi="10.48550/arxiv.2401.00001", sources=["openalex"])
    a2 = dict(title="First listing of work A", arxiv_id="2401.00001", doi="10.1000/j.1", sources=["arxiv"])
    b = dict(title="Another listing named B", doi="10.2000/b.1", sources=["openalex"])
    r = dict(title="Record joining B and A", doi="10.2000/b.1", arxiv_id="2401.00001", sources=["arxiv"])
    s = dict(title="Late copy with the abstract", doi="10.48550/arxiv.2401.00001",
             abstract="The abstract that only the late copy carries.", sources=["openalex"])
    merged = ps.merge_all([ps.record(**dict(x)) for x in (a, a2, b, r, s)])
    assert len(merged) == 1 and merged[0]["abstract"] == s["abstract"], merged


def test_pubmed_abstracts_malformed_xml_returns_empty():
    saved = ps._get
    ps._get = lambda url, retries=3: b"<html><body>error</html>"
    try:
        assert ps._pubmed_abstracts("https://x/", "1,2") == {}
    finally:
        ps._get = saved


_FEED = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def _fake_clock():
    clock, sleeps = [100.0], []
    ps.time.monotonic = lambda: clock[0]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    ps.time.sleep = sleep
    return sleeps


def test_fetch_arxiv_request_uses_https():
    urls, saved = [], (ps._get, ps.time.monotonic, ps.time.sleep)
    ps._get = lambda url, retries=3: urls.append(url) or _FEED
    _fake_clock()
    try:
        ps.fetch_arxiv("q", 5, 0)
    finally:
        ps._get, ps.time.monotonic, ps.time.sleep = saved
    assert urls and urls[0].startswith("https://export.arxiv.org/"), urls


def test_fetch_arxiv_consecutive_requests_wait_three_seconds():
    saved = (ps._get, ps.time.monotonic, ps.time.sleep)
    ps._get = lambda url, retries=3: _FEED
    sleeps = _fake_clock()
    try:
        ps.fetch_arxiv("q1", 5, 0)
        ps.fetch_arxiv("q2", 5, 0)
    finally:
        ps._get, ps.time.monotonic, ps.time.sleep = saved
    assert sleeps and sleeps[-1] >= 3 - 1e-6, sleeps


def test_get_retry_after_header_sets_sleep_capped_at_thirty():
    import email.message
    import urllib.error

    def run(header):
        calls, saved = [0], (ps.urllib.request.urlopen, ps.time.monotonic, ps.time.sleep)
        sleeps = _fake_clock()

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"ok"

        def urlopen(req, timeout=None):
            calls[0] += 1
            if calls[0] == 1:
                hdrs = email.message.Message()
                hdrs["Retry-After"] = header
                raise urllib.error.HTTPError("u", 429, "Too Many", hdrs, None)
            return Resp()
        ps.urllib.request.urlopen = urlopen
        try:
            assert ps._get("https://example.org/") == b"ok"
        finally:
            ps.urllib.request.urlopen, ps.time.monotonic, ps.time.sleep = saved
        return sleeps

    assert run("20") == [20]
    assert run("120") == [30]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  " + name)
    print("all passed")
