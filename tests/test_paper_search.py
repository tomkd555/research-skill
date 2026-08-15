#!/usr/bin/env python3
"""Offline self-check for paper_search.py: run `python test_paper_search.py`."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "research-team", "skills", "literature-review", "scripts"))
import paper_search as ps


def test_inverted_index():
    assert ps.from_inverted_index({"large": [1], "a": [0], "model": [2]}) == "a large model"
    assert ps.from_inverted_index(None) == ""


def test_doi_and_grade():
    assert ps.norm_doi("https://doi.org/10.1145/ABC") == "10.1145/abc"
    arxiv = ps.record(title="t", doi="https://doi.org/10.48550/arXiv.2312.10997",
                      is_preprint=True)
    assert arxiv["arxiv_id"] == "2312.10997"
    assert ps.grade(arxiv) == "B"
    assert ps.canonical_url(arxiv) == "https://arxiv.org/abs/2312.10997"
    published = ps.record(title="t", doi="10.1145/abc")
    assert ps.grade(published) == "A"
    assert ps.canonical_url(published) == "https://doi.org/10.1145/abc"
    assert ps.grade(ps.record(title="t")) == "C"


def test_merge_across_sources():
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

    # A published version and a preprint of the same title merge, and stop counting as a preprint.
    pair = ps.merge_all([
        ps.record(title="Attention Is All You Need Again", is_preprint=True, sources=["arxiv"]),
        ps.record(title="Attention Is All You Need Again", doi="10.5555/x", is_preprint=False,
                  sources=["openalex"]),
    ])
    assert len(pair) == 1 and pair[0]["is_preprint"] is False
    assert ps.grade(pair[0]) == "A"

    # Different papers stay apart.
    assert len(ps.merge_all([ps.record(title="Some Entirely Different Paper Title"),
                             ps.record(title="Another Wholly Unrelated Paper Title")])) == 2


def test_rank():
    ranked = ps.rank([ps.record(title="a", citations=3), ps.record(title="b", citations=90)],
                     min_citations=1)
    assert [r["title"] for r in ranked] == ["b", "a"]
    assert ps.rank([ps.record(title="a", citations=3)], min_citations=10) == []


def test_check_catches_a_fabricated_quote():
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
        assert ps.cmd_check(args) == 1  # E2 fabricated, E3 unknown paper; E1 and E4 pass


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  " + name)
    print("all passed")
