#!/usr/bin/env python3
"""Checks for triage_sources.py.

1. Registrable-domain resolution (multi-label suffixes such as co.jp, www. removal, subdomains)
2. The second and later URL of one domain leaves the fetch list and is not counted as independent
3. Ranking follows the expected grade
4. Notes report a grade-C-only fetch list and a shortage of independent clusters
"""
import importlib.util
import os
import sys

SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "plugins", "research-team", "skills", "research-team",
                           "scripts")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = load(os.path.join(SKILL_SCRIPTS, "triage_sources.py"), "ts_new")


def test_registrable_domain():
    cases = {
        "https://www.e-stat.go.jp/stat-search/x": "e-stat.go.jp",
        "https://ir.example.co.jp/library/": "example.co.jp",
        "https://example.co.jp/a": "example.co.jp",
        "https://blog.example.com/a": "example.com",
        "https://example.com": "example.com",
        "https://sub.dept.univ.ac.uk/paper": "univ.ac.uk",
        "not a url": "",
    }
    for url, expected in cases.items():
        got = ts.registrable_domain(url)
        assert got == expected, f"{url}: {got} != {expected}"
    print("[1] registrable domain (multi-label suffix, subdomain, www.)")


CLUSTER_URLS = [
    "https://note.example.com/post1",                 # C
    "https://ir.sony.co.jp/investors/library/a.pdf",  # B (IR path)
    "https://www.e-stat.go.jp/a",                     # A
    "https://www.e-stat.go.jp/b",                     # A but same cluster -> skip
    "https://note.example.com/post2",                 # C same cluster -> skip
    "https://www.oecd.org/report",                    # A
]


def test_triage_fetch_order_by_grade():
    r = ts.triage(CLUSTER_URLS, "KQ1")
    assert [x["grade_hint"] for x in r["ranked"]][:3] == ["A", "A", "A"], r["ranked"]
    assert r["fetch_order"] == [
        "https://www.e-stat.go.jp/a",
        "https://www.oecd.org/report",
        "https://ir.sony.co.jp/investors/library/a.pdf",
        "https://note.example.com/post1",
    ], r["fetch_order"]
    print("[2] the order runs A -> B -> C")


def test_triage_same_cluster_urls_skipped():
    r = ts.triage(CLUSTER_URLS, "KQ1")
    assert r["clusters"] == 4, r["clusters"]
    skipped = [x["url"] for x in r["ranked"] if x["duplicate"]]
    assert set(skipped) == {"https://www.e-stat.go.jp/b", "https://note.example.com/post2"}, skipped
    assert r["notes"] == [], r["notes"]
    print("[3] the second URL of a cluster is dropped")


def test_triage_grade_c_only_adds_grade_c_note():
    r = ts.triage(["https://blog.a.com/1", "https://blog.b.com/1"], "KQ2")
    assert any("grade C" in n for n in r["notes"]), r["notes"]
    print("[4] grade-C-only is reported")


def test_triage_two_clusters_adds_cluster_note():
    r = ts.triage(["https://blog.a.com/1", "https://blog.b.com/1"], "KQ2")
    assert any("independent cluster" in n for n in r["notes"]), r["notes"]
    print("[5] cluster shortage is reported")


def test_grade_hint_preprint_servers_grade_b():
    for url in ("https://arxiv.org/abs/2401.00001", "https://www.biorxiv.org/content/x",
                "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1"):
        assert ts.grade_hint(url)[0] == "B", url


def test_main_help_uses_sq_prefix():
    import subprocess
    out = subprocess.run([sys.executable, os.path.join(SKILL_SCRIPTS, "triage_sources.py"), "-h"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    assert "KQ" not in out and "SQ1" in out, out


def test_triage_two_arxiv_papers_both_fetched():
    r = ts.triage(["https://arxiv.org/abs/2401.00001v2", "https://arxiv.org/pdf/2402.00002",
                   "https://arxiv.org/abs/2401.00001"], "SQ1")
    assert r["fetch_order"] == ["https://arxiv.org/abs/2401.00001v2", "https://arxiv.org/pdf/2402.00002"], r


def test_origin_per_paper_and_account():
    cases = {
        "https://arxiv.org/abs/2401.00001v3": "arxiv:2401.00001",
        "https://doi.org/10.1000/ABC.1": "doi:10.1000/abc.1",
        "https://github.com/acme/tool/blob/main/README.md": "github.com/acme",
        "https://acme.github.io/docs/": "acme.github.io",
        "https://medium.com/@writer/post-1": "medium.com/@writer",
        "https://www.e-stat.go.jp/stat-search/x": "e-stat.go.jp",
    }
    for url, want in cases.items():
        assert ts.origin(url) == want, (url, ts.origin(url), want)


if __name__ == "__main__":
    test_registrable_domain()
    test_triage_fetch_order_by_grade()
    test_triage_same_cluster_urls_skipped()
    test_triage_grade_c_only_adds_grade_c_note()
    test_triage_two_clusters_adds_cluster_note()
    test_grade_hint_preprint_servers_grade_b()
    test_main_help_uses_sq_prefix()
    test_triage_two_arxiv_papers_both_fetched()
    test_origin_per_paper_and_account()
    print("all passed")
