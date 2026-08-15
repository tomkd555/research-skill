#!/usr/bin/env python3
"""paper_search.py - academic literature search over OpenAlex / arXiv / PubMed / Semantic Scholar.

The point of this script is cost. Hitting the academic APIs from an agent means raw API JSON
lands in the model's context and gets re-parsed there. Here the fetching, de-duplication,
ranking and grading happen in Python, and the model sees a compact table; abstracts are pulled
only for the papers it picks.

Standard library only. Uses the network.

    python paper_search.py search "query one" "query two" --db papers.json
    python paper_search.py show --db papers.json P1 P3
    python paper_search.py check --db papers.json --evidence evidence.json

Exit codes: 0 = ok / 1 = check failed / 2 = usage or I/O error.
"""

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# OpenAlex routes callers who identify themselves to a faster pool. It is optional, so the
# address is only sent when the user supplies one.
MAILTO = os.environ.get("OPENALEX_MAILTO", "")
UA = "literature-review/1.0 (+https://github.com/tomkd555/research-skill)"
if MAILTO:
    UA += " (mailto:%s)" % MAILTO
TIMEOUT = 30
SOURCES = ("openalex", "arxiv", "pubmed", "semanticscholar")
DEFAULT_SOURCES = ("openalex", "arxiv")


# ---------------------------------------------------------------- http

def _get(url, retries=3):
    """GET with backoff on the throttling and transient status codes."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            raise
    return b""


def _get_json(url, retries=3):
    return json.loads(_get(url, retries) or b"{}")


# ---------------------------------------------------------------- normalisation

_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)


def norm_doi(doi):
    if not doi:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower())


def norm_title(title):
    folded = unicodedata.normalize("NFKD", title or "").lower()
    return re.sub(r"[^a-z0-9]+", "", folded)


def norm_text(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip().lower()


def from_inverted_index(index):
    """OpenAlex ships abstracts as {word: [positions]}; put the words back in order."""
    if not index:
        return ""
    positions = [(pos, word) for word, spots in index.items() for pos in spots]
    positions.sort()
    return " ".join(word for _, word in positions)


def record(**kw):
    rec = {
        "title": "", "authors": [], "year": None, "venue": "", "doi": "", "arxiv_id": "",
        "pmid": "", "citations": 0, "is_preprint": False, "abstract": "", "oa_url": "",
        "sources": [],
    }
    rec.update(kw)
    rec["doi"] = norm_doi(rec["doi"])
    match = _ARXIV_DOI.match(rec["doi"])
    if match and not rec["arxiv_id"]:
        rec["arxiv_id"] = match.group(1)
    return rec


def grade(rec):
    """A = peer-reviewed with a DOI, B = preprint, C = neither established."""
    if rec["is_preprint"]:
        return "B"
    if rec["doi"]:
        return "A"
    return "C"


def canonical_url(rec):
    if rec["doi"] and not _ARXIV_DOI.match(rec["doi"]):
        return "https://doi.org/" + rec["doi"]
    if rec["arxiv_id"]:
        return "https://arxiv.org/abs/" + rec["arxiv_id"]
    if rec["doi"]:
        return "https://doi.org/" + rec["doi"]
    if rec["pmid"]:
        return "https://pubmed.ncbi.nlm.nih.gov/" + rec["pmid"] + "/"
    return rec["oa_url"]


# ---------------------------------------------------------------- sources

def fetch_openalex(query, limit, year_from):
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(query)
           + "&per-page=%d" % limit)
    if MAILTO:
        url += "&mailto=" + urllib.parse.quote(MAILTO)
    if year_from:
        url += "&filter=publication_year:>%d" % (year_from - 1)
    out = []
    for work in _get_json(url).get("results", []):
        loc = (work.get("primary_location") or {}).get("source") or {}
        out.append(record(
            title=work.get("display_name") or "",
            authors=[a["author"]["display_name"] for a in work.get("authorships", [])[:5]
                     if a.get("author")],
            year=work.get("publication_year"),
            venue=loc.get("display_name") or "",
            doi=work.get("doi") or "",
            citations=work.get("cited_by_count") or 0,
            is_preprint=work.get("type") == "preprint" or loc.get("type") == "repository",
            abstract=from_inverted_index(work.get("abstract_inverted_index")),
            oa_url=(work.get("open_access") or {}).get("oa_url") or "",
            sources=["openalex"],
        ))
    return out


def fetch_arxiv(query, limit, year_from):
    url = ("http://export.arxiv.org/api/query?search_query=all:"
           + urllib.parse.quote(query) + "&max_results=%d" % limit)
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(_get(url))
    out = []
    for entry in root.findall("a:entry", ns):
        arxiv_url = entry.findtext("a:id", default="", namespaces=ns)
        arxiv_id = re.sub(r"^.*/abs/", "", arxiv_url)
        published = entry.findtext("a:published", default="", namespaces=ns)
        year = int(published[:4]) if published[:4].isdigit() else None
        if year_from and year and year < year_from:
            continue
        journal_ref = entry.findtext("ar:journal_ref", default="", namespaces=ns) or ""
        out.append(record(
            title=" ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split()),
            authors=[a.findtext("a:name", default="", namespaces=ns)
                     for a in entry.findall("a:author", ns)[:5]],
            year=year,
            venue=journal_ref or "arXiv",
            doi=entry.findtext("ar:doi", default="", namespaces=ns) or "",
            arxiv_id=arxiv_id,
            is_preprint=not journal_ref,
            abstract=" ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split()),
            oa_url="https://arxiv.org/pdf/" + re.sub(r"v\d+$", "", arxiv_id),
            sources=["arxiv"],
        ))
    return out


def fetch_pubmed(query, limit, year_from):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    term = urllib.parse.quote(query)
    if year_from:
        term += urllib.parse.quote(' AND ("%d"[PDAT] : "3000"[PDAT])' % year_from)
    ids = _get_json(base + "esearch.fcgi?db=pubmed&retmode=json&retmax=%d&term=%s"
                    % (limit, term)).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    joined = ",".join(ids)
    summaries = _get_json(base + "esummary.fcgi?db=pubmed&retmode=json&id=" + joined
                          ).get("result", {})
    abstracts = _pubmed_abstracts(base, joined)
    out = []
    for pmid in ids:
        item = summaries.get(pmid)
        if not item:
            continue
        articleids = {a.get("idtype"): a.get("value") for a in item.get("articleids", [])}
        pubdate = item.get("pubdate") or ""
        out.append(record(
            title=item.get("title") or "",
            authors=[a.get("name") for a in item.get("authors", [])[:5] if a.get("name")],
            year=int(pubdate[:4]) if pubdate[:4].isdigit() else None,
            venue=item.get("fulljournalname") or item.get("source") or "",
            doi=articleids.get("doi") or "",
            pmid=pmid,
            is_preprint="Preprint" in (item.get("pubtype") or []),
            abstract=abstracts.get(pmid, ""),
            sources=["pubmed"],
        ))
    return out


def _pubmed_abstracts(base, joined_ids):
    """esummary carries no abstract, so efetch them in one call."""
    try:
        xml = _get(base + "efetch.fcgi?db=pubmed&retmode=xml&rettype=abstract&id=" + joined_ids)
    except Exception:
        return {}
    out = {}
    for article in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        parts = [(t.text or "").strip() for t in article.iter("AbstractText")]
        if pmid:
            out[pmid] = " ".join(p for p in parts if p)
    return out


def fetch_semanticscholar(query, limit, year_from):
    """Optional. Without an API key this throttles hard; a failure degrades to no results."""
    fields = "title,year,venue,authors,citationCount,externalIds,abstract,openAccessPdf,publicationTypes"
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?query="
           + urllib.parse.quote(query) + "&limit=%d&fields=%s" % (limit, fields))
    if year_from:
        url += "&year=%d-" % year_from
    try:
        data = _get_json(url, retries=4)
    except Exception as exc:
        print("warn: semanticscholar unavailable (%s)" % exc, file=sys.stderr)
        return []
    out = []
    for paper in data.get("data") or []:
        ext = paper.get("externalIds") or {}
        types = paper.get("publicationTypes") or []
        out.append(record(
            title=paper.get("title") or "",
            authors=[a.get("name") for a in (paper.get("authors") or [])[:5] if a.get("name")],
            year=paper.get("year"),
            venue=paper.get("venue") or "",
            doi=ext.get("DOI") or "",
            arxiv_id=ext.get("ArXiv") or "",
            citations=paper.get("citationCount") or 0,
            is_preprint=not paper.get("venue") and bool(ext.get("ArXiv")),
            abstract=paper.get("abstract") or "",
            oa_url=(paper.get("openAccessPdf") or {}).get("url") or "",
            sources=["semanticscholar"],
        ))
    return out


FETCHERS = {
    "openalex": fetch_openalex,
    "arxiv": fetch_arxiv,
    "pubmed": fetch_pubmed,
    "semanticscholar": fetch_semanticscholar,
}


# ---------------------------------------------------------------- merge

def dedup_keys(rec):
    keys = []
    if rec["doi"]:
        keys.append("doi:" + rec["doi"])
    if rec["arxiv_id"]:
        keys.append("arxiv:" + re.sub(r"v\d+$", "", rec["arxiv_id"].lower()))
    title = norm_title(rec["title"])
    if len(title) > 15:
        keys.append("title:" + title)
    return keys


def merge_into(target, other):
    if len(other["abstract"]) > len(target["abstract"]):
        target["abstract"] = other["abstract"]
    target["citations"] = max(target["citations"], other["citations"])
    for field in ("title", "venue", "doi", "arxiv_id", "pmid", "oa_url"):
        if not target[field] and other[field]:
            target[field] = other[field]
    if not target["year"]:
        target["year"] = other["year"]
    if not target["authors"]:
        target["authors"] = other["authors"]
    # A record that any source calls published outranks a preprint listing of the same work.
    target["is_preprint"] = target["is_preprint"] and other["is_preprint"]
    for src in other["sources"]:
        if src not in target["sources"]:
            target["sources"].append(src)
    return target


def merge_all(records, existing=None):
    """Fold duplicates found across queries and sources into one record each."""
    index, merged = {}, []
    for rec in (existing or []) + records:
        keys = dedup_keys(rec)
        hit = next((index[k] for k in keys if k in index), None)
        if hit is None:
            merged.append(rec)
            hit = rec
        else:
            merge_into(hit, rec)
        for key in dedup_keys(hit):
            index[key] = hit
    return merged


def rank(records, min_citations=0):
    kept = [r for r in records if r["citations"] >= min_citations]
    kept.sort(key=lambda r: (-r["citations"], -(r["year"] or 0), r["title"]))
    return kept


# ---------------------------------------------------------------- commands

def cmd_search(args):
    sources = [s for s in (args.source.split(",") if args.source else DEFAULT_SOURCES)]
    for src in sources:
        if src not in FETCHERS:
            sys.exit("unknown source: %s (choose from %s)" % (src, ",".join(SOURCES)))

    jobs = [(src, q) for src in sources for q in args.query]
    collected, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(FETCHERS[src], q, args.limit, args.year_from): (src, q)
                   for src, q in jobs}
        for future in concurrent.futures.as_completed(futures):
            src, query = futures[future]
            try:
                collected.extend(future.result())
            except Exception as exc:
                failures.append("%s / %r: %s" % (src, query, exc))

    existing, prior_queries = [], []
    if args.merge:
        try:
            with open(args.db, encoding="utf-8") as fh:
                old = json.load(fh)
            existing = old.get("papers", [])
            prior_queries = old.get("queries", [])
            for rec in existing:
                rec.pop("id", None)
                rec.pop("grade", None)
                rec.pop("url", None)
        except FileNotFoundError:
            pass

    papers = rank(merge_all(collected, existing), args.min_citations)
    for num, rec in enumerate(papers, 1):
        rec["id"] = "P%d" % num
        rec["grade"] = grade(rec)
        rec["url"] = canonical_url(rec)

    db = {
        "queries": prior_queries + [{"query": q, "sources": sources} for q in args.query],
        "count": len(papers),
        "papers": papers,
    }
    with open(args.db, "w", encoding="utf-8") as fh:
        json.dump(db, fh, ensure_ascii=False, indent=2)

    for line in failures:
        print("warn: " + line, file=sys.stderr)
    print(format_table(papers))
    print("\n%d papers -> %s  (abstracts: %s of %d)"
          % (len(papers), args.db, sum(1 for p in papers if p["abstract"]), len(papers)))


def format_table(papers):
    header = "%-5s %-5s %-6s %-2s %-20s %s" % ("ID", "YEAR", "CITES", "G", "VENUE", "TITLE")
    rows = [header, "-" * 110]
    for rec in papers:
        rows.append("%-5s %-5s %-6s %-2s %-20s %s%s" % (
            rec["id"], rec["year"] or "-", rec["citations"], rec["grade"],
            _clip(rec["venue"] or "-", 20), _clip(rec["title"], 58),
            "" if rec["abstract"] else "  [no-abstract]",
        ))
    return "\n".join(rows)


def _clip(text, width):
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[:width - 1] + "…"


def cmd_show(args):
    papers = {p["id"]: p for p in _load_db(args.db)["papers"]}
    missing = [i for i in args.ids if i not in papers]
    if missing:
        sys.exit("not in %s: %s" % (args.db, ", ".join(missing)))
    for pid in args.ids:
        rec = papers[pid]
        print("### %s  [%s]" % (rec["id"], rec["grade"]))
        print("title:    %s" % rec["title"])
        print("authors:  %s" % ", ".join(rec["authors"]))
        print("venue:    %s (%s)  citations: %d  preprint: %s"
              % (rec["venue"] or "-", rec["year"] or "-", rec["citations"], rec["is_preprint"]))
        print("url:      %s" % rec["url"])
        if rec["oa_url"]:
            print("fulltext: %s" % rec["oa_url"])
        print("abstract: %s" % (rec["abstract"] or "(not provided by the source APIs)"))
        print()


def cmd_check(args):
    """Every claim must point at a paper in the db, and every quote must be in that paper."""
    papers = {p["id"]: p for p in _load_db(args.db)["papers"]}
    with open(args.evidence, encoding="utf-8") as fh:
        evidence = json.load(fh)
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence", [])

    problems, unverifiable = [], 0
    for item in evidence:
        eid = item.get("id", "?")
        pid = item.get("paper")
        rec = papers.get(pid)
        if rec is None:
            problems.append("%s: paper %r is not in %s" % (eid, pid, args.db))
            continue
        quote = item.get("quote") or ""
        if not quote:
            problems.append("%s: no quote" % eid)
            continue
        if item.get("quote_source") == "fulltext":
            unverifiable += 1
            continue
        if norm_text(quote) not in norm_text(rec["abstract"]):
            problems.append("%s: quote is not in %s's abstract" % (eid, pid))

    for line in problems:
        print("FAIL " + line)
    print("checked %d evidence units: %d FAIL, %d fulltext quotes (verify by hand)"
          % (len(evidence), len(problems), unverifiable))
    return 1 if problems else 0


def _load_db(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit("no such db: %s" % path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="search the academic APIs and write a paper db")
    p_search.add_argument("query", nargs="+", help="one or more queries, run in parallel")
    p_search.add_argument("--db", default="papers.json")
    p_search.add_argument("--source", help="comma separated: " + ",".join(SOURCES)
                          + " (default: " + ",".join(DEFAULT_SOURCES) + ")")
    p_search.add_argument("--limit", type=int, default=20, help="results per query per source")
    p_search.add_argument("--year-from", type=int, default=0)
    p_search.add_argument("--min-citations", type=int, default=0)
    p_search.add_argument("--merge", action="store_true",
                          help="fold into an existing db (snowballing); ids are reassigned")
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="print full records incl. abstracts")
    p_show.add_argument("ids", nargs="+")
    p_show.add_argument("--db", default="papers.json")
    p_show.set_defaults(func=cmd_show)

    p_check = sub.add_parser("check", help="verify evidence quotes against the paper db")
    p_check.add_argument("--db", default="papers.json")
    p_check.add_argument("--evidence", required=True)
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
