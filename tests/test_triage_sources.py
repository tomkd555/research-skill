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


def test_dedup_and_order():
    urls = [
        "https://note.example.com/post1",                 # C
        "https://ir.sony.co.jp/investors/library/a.pdf",  # B (IR path)
        "https://www.e-stat.go.jp/a",                     # A
        "https://www.e-stat.go.jp/b",                     # A but same cluster -> skip
        "https://note.example.com/post2",                 # C same cluster -> skip
        "https://www.oecd.org/report",                    # A
    ]
    r = ts.triage(urls, "KQ1")
    assert [x["grade_hint"] for x in r["ranked"]][:3] == ["A", "A", "A"], r["ranked"]
    assert r["fetch_order"] == [
        "https://www.e-stat.go.jp/a",
        "https://www.oecd.org/report",
        "https://ir.sony.co.jp/investors/library/a.pdf",
        "https://note.example.com/post1",
    ], r["fetch_order"]
    assert r["clusters"] == 4, r["clusters"]
    skipped = [x["url"] for x in r["ranked"] if x["duplicate"]]
    assert set(skipped) == {"https://www.e-stat.go.jp/b", "https://note.example.com/post2"}, skipped
    assert r["notes"] == [], r["notes"]
    print("[2] the second URL of a cluster is dropped and the order runs A -> B -> C")


def test_notes():
    r = ts.triage(["https://blog.a.com/1", "https://blog.b.com/1"], "KQ2")
    assert any("grade C" in n for n in r["notes"]), r["notes"]
    assert any("independent cluster" in n for n in r["notes"]), r["notes"]
    print("[3] grade-C-only and cluster shortage are reported")


if __name__ == "__main__":
    test_registrable_domain()
    test_dedup_and_order()
    test_notes()
    print("all passed")
