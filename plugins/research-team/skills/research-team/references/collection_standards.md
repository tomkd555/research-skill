# Collection standards (the source of record for accurate research results)

These quality standards apply to research-team's collection stage (Step 2) and
verification stage (Step 3). Collection agents (research-collector) read this document in full
before starting. The floor numbers are this skill's internal design values and are not
attributed to any external standard. Public analytic standards such as the US ODNI's ICD 203
set no numeric norms; they require sourcing per judgement and transparency about the state of
corroboration. These standards are internal rules informed by that design philosophy
(source [8]).

A deliverable's structure is English: its section headings, its table headers and its confidence
labels. `scripts/labels.py` holds them, together with the relevance tags and the `floor_status`
field names quoted below, and is the source of record for all of them. The prose under those
headings is written in the language of the request, which the ledger records as
`deliverable_language`.

## 1. Collection floors (the minimum work per key question)

| Item | DEEP (decision KQ) | DEEP (background KQ) and STANDARD | LIGHT |
|---|---|---|---|
| Search queries | 12 or more | 6 or more | No floor |
| Independent sources | 5 or more | 3 or more | 1 or more (state it if single) |
| Disconfirmation queries | 2 or more | 1 or more | Optional |
| Independent two-source corroboration of key figures | Required | Required | Recommended |

- **Decision relevance (decision KQ / background KQ)**: in DEEP, split the key questions into
  decision KQs, which directly drive the conclusion or the recommendation, and background KQs,
  which establish premises and context. Declare the split in research_brief at Step 1 and have
  every later stage merely read it — re-deciding importance at each stage turns variation in
  judgement into variation in workload. At most four decision KQs; background KQs get the same
  floors as STANDARD. The notation is `[decision]` or `[background]` appended to the end of each
  key question line in research_brief, and `scripts/research_plan_linter.py` checks that it is
  present. A key question with no classification is treated as a decision KQ, so that leaving
  it blank never lowers a floor. STANDARD and LIGHT do not use the split; every key question
  gets the same floors
- **The unit the floors apply to**: DEEP applies the table per role, so when one key question
  has both collector and scholar assigned, each of them meets every number on its own. STANDARD
  applies it per key question, and the two roles' totals may satisfy it together — but every
  launched role individually meets 3 or more queries and 1 or more disconfirmation query
  (`MIN_ROLE_ALLOCATION`). Applying only the total would let a fragment pass the deterministic
  check with scholar at zero queries whenever collector cleared the floor alone, and the report
  would pass with no academic evidence at all
- Record every query in the search log, including queries that yielded nothing. What you looked
  for and failed to find is itself evidence
- The floors are a minimum, not a target. Once two consecutive queries add no new information,
  you may stop, provided the floors are met (theoretical-saturation stopping rule; source [9])
- **Conclusion-sufficiency early stop**: in DEEP the floors are a target, and the STANDARD
  floors (6 queries, 3 independent sources, 1 disconfirmation query) are the absolute minimum.
  You may stop collecting short of the DEEP floors once all three of the
  following hold: (1) there are 3 or more independent sources; (2) the last two queries added
  no new evidence unit; (3) the conclusion for the assigned key question has reached "likely" or
  above on the seven-level confidence vocabulary. When you stop, record
  `{independent_sources, consecutive_zero_new, conclusion_confidence, note}` under
  `floor_status.early_stop`. Where that record exists and the STANDARD floors are met,
  `scripts/evidence_auditor.py` and `scripts/validate_fragment.py` report the shortfall as a
  warning rather than a failure. A shortfall with no record remains a failure.
  Transcribe what was cut short into the report's limitations section — stopping means "not
  investigated", not "does not exist"
- **Session-wide search budget**: Claude Code caps WebSearch calls at 200 per session by default.
  The parent and every subagent share the cap, and past it a search returns a
  budget-exceeded string instead of failing. The planning-stage estimate that keeps a study inside
  the cap belongs to the planner, not to a collection agent: it is in pipeline.md, Step 1. What
  matters here is that the academic APIs (Semantic Scholar / OpenAlex / Crossref / arXiv / PubMed)
  are called through `paper_search.py` and do not consume the cap

## 2. Query design

Cover synonyms, related terms, broader concepts, and narrower concepts, and always include the
four search facets below. A search skewed to one facet produces skewed results no matter how
much it collects. The shapes are written in English here; run each facet in whatever language
the best sources for your key question are written in, since a domestic rule, a local market and
a national statistics office are documented in their own language and nowhere else.

| Facet | Purpose | Query shape |
|---|---|---|
| Definition and overview | The standard understanding and vocabulary of the subject | "what is {topic}" / "{topic} overview" |
| Data and statistics | Figures, scale, trends | "{topic} statistics" / "{topic} market size site:oecd.org" |
| Disconfirmation and criticism | Conflicting information (the §3 duty) | "{topic} criticism limitations" / "{topic} failure cases" |
| Practice and cases | How it plays out in application, and the pitfalls | "{topic} case study lessons" / "{topic} adoption comparison" |

- Record which of the four facets each query covers in the search log's `facet` field
  (`definition` / `data` / `counter` / `practice`). `scripts/validate_fragment.py` warns when a
  fragment records some facets and misses others, so the skew shows before the fragment is
  returned rather than at synthesis
- Once you find a strong source, follow its references and citations to pick up adjacent
  sources (snowball sampling; source [6])
- Vary period qualifiers (years, "latest") and operators (site: / filetype:pdf / quoted
  phrases)
- **Filter with the search tool's own domain arguments, not only with `site:`.** WebSearch takes
  `allowed_domains` and `blocked_domains`. Spend at least one query per key question as a
  primary-source sweep with `allowed_domains` (for example `["go.jp", "e-stat.go.jp",
  "oecd.org"]` for statistics, the regulator's domain for a rule, the company's domain for a
  filing), and put the content farms that keep coming back into `blocked_domains` for the rest
  of the run. The call count is unchanged; what changes is the grade mix of what comes back.
  `site:` reaches one domain per query, so it costs a query per domain — the arguments take a
  list in one call
- **Search broadly, then narrow**: start with short broad queries and move to specific terms as
  you see results. Do not cling to a specific query that returns little — go back to a broad
  query and narrow again
- For academic questions where completeness matters, record the search terms, the databases,
  and the selection criteria, and make them transparent in the style of PRISMA reporting (the count
  found, the count excluded, and the reason; source [4])
- On broad themes — subjects with no settled definition, or with two or more opposing positions —
  split the query sets by viewpoint (persona) when collecting. This prevents a single-viewpoint
  bias and increases the diversity of what you gather (STORM's multi-perspective simulation
  improves coverage; source [11])
- Derive the tool-call budget from the collection floors in §1. Per key question and role, the
  guide is 20–28 calls for a DEEP decision KQ (12 searches plus 8–16 page fetches), 10–16 for a
  DEEP background KQ and for STANDARD (6 searches plus 4–10 fetches), and 3–10 for LIGHT. The
  fetch share counts pages, not calls: one `fetch_page.py` call takes a whole batch of URLs.
  **Set the budget above the floor. Never cut a floor to fit a budget** — §1 sets the minimum
  work and the budget is only a brake on overrun. If you hit the budget with a floor unmet, do
  not stop there: continue to §1's saturation rule (two consecutive queries adding nothing) or
  to the three early-stop conditions. If the floor is still unmet, state the shortfall and the reason in
  floor_status and record it in the evidence gap table. Page fetching follows §9

## 3. The disconfirmation duty

Confirmation bias — collecting only evidence that supports the hypothesis — is the largest
systematic error in research (sources [1][2]). The countermeasure is to invert the search
instruction.

1. For each hypothesis, list what would be observed if it were false, before searching
2. Search directly for whether those observations exist ("{hypothesis} failure", "{measure}
   problems", plus the disconfirming facts you listed)
3. Record any disconfirming fact you find, with its content and its effect on the hypothesis,
   in the ledger's disconfirmation

- Aim disconfirmation at the strongest form of the opposing view. Defeating its weakest form
  does not count as disconfirmation (consider-the-opposite; source [3])
- At least 2 queries per KQ (1 in STANDARD) are disconfirmation searches, logged with kind
  `counter`
- The research output always includes whether evidence against the hypothesis exists and what
  it says, the alternative hypotheses, and the indicators that would change the judgement

## 4. Source grades

| Grade | Definition | Examples |
|---|---|---|
| A | Governments, international organisations, peer-reviewed papers | e-Stat, OECD, World Bank, peer-reviewed papers with a DOI |
| B | Industry bodies, corporate IR, major research firms, independent think tanks, consulting firm publications | Industry statistics, securities reports, research-firm press releases, published firm reports |
| C | Trade media, news reporting, personal blogs, forums | Trade journals, newspaper articles, technical blogs |

- Never let a key figure rest only on grade-C sources. Grade C serves as supplementary
  or corroborating material only
- Peer-reviewed papers are grade A; preprints are grade B, with "preprint, not peer-reviewed"
  stated in the source's `descriptor`
- Where a secondary review (a firm report, say) cites primary data, cite the primary source
- Add a one-line narrative descriptor to any source that drives the conclusion: the publisher's
  access to the data, the motive for publishing, the likely bias, and freshness
- Within academic sources, note certainty with the evidence hierarchy: meta-analysis /
  systematic review > randomised controlled trial > observational study > case study > expert
  opinion (the design philosophy of GRADE; source [5]. Standards differ by field, so do not
  apply it mechanically)
- Check for predatory journals (journals that charge fees and do not really peer-review) before
  accepting a paper. Acceptance within days, an opaque editorial board, absence from the major
  databases (Scopus / Web of Science / PubMed) — where two or more such warning signs appear, treat
  the paper as rejected or as corroboration only, and check DOAJ or Think. Check. Submit. when
  in doubt
- Prefer primary information (the publisher's own announcement, the primary data) over
  SEO-optimised aggregators and content farms (sites that hold no primary data and merely
  reprint or summarise others). This is the same idea as replacing a secondary review with its
  primary source: grade by the primacy of the origin, not by how the page looks
- **Setting self_reported**: figures and effect sizes published by the method's proposer, a
  vendor, or an interested party are `self_reported: true`. When such a figure is also
  `is_key_figure`, add an attempt at independent corroboration to the §6 corroboration duty; if
  you find none, state in the report body that the figure is self-reported

## 5. Judging source independence

"Five sources" means five independent origins, not five URLs.

- Pages from the same publisher count as one source
- Reprints, wire-service distribution, and multiple reports originating from one press release
  belong to the same independence cluster (`origin_cluster`) once traced back. Always follow the chain of
  citation before counting sources
- Judge a source's reliability by what other sites say about the origin, not by how the page
  itself looks (lateral reading: before reading the site in question, find out how other sites
  assess that origin; source [7])
- Assess the origin's reliability and the information's credibility on separate axes (the
  military intelligence grading system uses two axes, reliability A–F × credibility 1–6;
  source [10]. This skill simplifies that into the `grade` and `corroboration` fields)

## 6. Corroboration and the corroboration-state flag

Key figures used in the report (the figures that ground a conclusion or a recommendation) are
checked against two or more independent sources, and every key figure carries one of these
flags.

| Flag | Meaning |
|---|---|
| corroborated | Confirmed at a comparable value by two or more independent sources |
| single_source | No corroborating source was found; one source only. Usable, but flag it explicitly |
| conflicting | The values diverge across sources. Record both values and an account of why they differ |

Never hide a conflict. Making a conflict and its structure visible — differing definitions,
differing points in time, differing populations — is worth more than presenting a single value.

## 7. Freshness rules

- Prefer market data and statistics from the last three years. When using data older than
  three years, note that nothing newer exists and why you are using it
- For fast-moving subjects (AI, regulation, pricing), prefer the last 12 months, and always
  attach the retrieval time to anything older
- Record a publication date (`published`) and an access date (`accessed`) on every evidence
  unit. Never treat information dated after the as-of date as a fact "as of the study"

## 8. Required output (included in a collection agent's response)

1. **Evidence units**: the `evidence` array fragment from `assets/evidence_log.schema.json`
   (structure per interpretation_contract.md §1)
2. **Search log**: query, tool, number of sources adopted, kind (normal / counter), facet
   (definition / data / counter / practice; §2)
3. **Evidence gap table**: claims that could not be corroborated, the queries tried, and the
   additional research recommended
4. **Alternative hypotheses and indicators**: another explanation that could overturn this KQ's
   conclusion, and the signals that would change its likelihood
5. **Disconfirmation record**: the results of the §3 procedure as an array of
   `{hypothesis, expected_if_false, queries, found, impact}`. When no disconfirming fact was
   found, record the queries you ran and that they confirmed none. The agent that ran
   the disconfirmation search writes this record; the orchestrator never reconstructs it from a
   summary

## 9. Page-fetch rules

Fetch pages through `scripts/fetch_page.py`, and read the cache it writes. WebFetch is the
fallback, not the default, because it does not return the page as it is: it converts the page to
Markdown, has a small model answer the `prompt`, and returns that answer. Record that answer as a
verbatim quote and it fails the citation match (`scripts/citation_verifier.py` looks for the
quote in the live page and requires 0.9 of its characters to appear, in order, inside one window
of the page text). The cache holds the page text after the same extraction and normalisation the
verifier applies, so a quote copied out of it matches by construction.

1. **Sort the candidates first**: pass the URLs the search returned to
   `python {SKILL_DIR}/scripts/triage_sources.py --prefix {KQ_ID} {urls} --json`. It groups them
   by registrable domain, assigns the provisional `origin_cluster`, ranks them by the source
   grade expected from the domain, and drops the second and later URL of one cluster from the
   fetch list. Take `fetch_order` as the reading order and read its `notes`. The grade it reports
   is an expectation from the URL; the `grade` on an evidence unit is still your call under §4
   after reading the page
2. **Fetch**: `python {SKILL_DIR}/scripts/fetch_page.py --run-dir {RUN_DIR} {fetch_order URLs}
   --json`. Pass every URL in one call — they are fetched in parallel under a per-host interval.
   A URL already in the cache comes back as `cached` without a second request, which is how the
   no-duplicate-fetch rule is kept
3. **Read the cache with Grep**, not by reading the file whole. Search the cached text for the
   figures and terms of your key question, then copy the quote out of the line the hit sits on.
   The line breaks in the cache are its own wrapping, so quote from inside one line
4. **Fall back to WebFetch** for anything the fetch reports as `unsupported` (PDF), `thin`
   (JavaScript-rendered or paywalled) or `unreachable`. There, use this prompt template and treat
   what comes back as needing a stricter reading:
   "Extract at most 5 passages bearing on the assigned key question, each 40 words or fewer,
   worded exactly as the page words them. Write no summary, paraphrase, preamble or comment.
   Give every figure its unit, denominator and period, and every article its publication date
   and publisher."
5. **Filter before fetching**: on top of the ranking, decide from the search-result snippet
   whether the page is worth a fetch at all. The three criteria are the primacy of the origin
   (§4), whether a publication date exists, and the expected grade. Do not fetch a page that the
   snippet already shows can only be grade C
6. **No duplicate fetches**: never re-fetch a URL you have already fetched. Fetch another page
   from the same publisher only when it holds a new fact for your key question

## Sources

The bibliography for the reference marks `[1]` through `[11]` in this document is cited in
[methodology_sources.md](methodology_sources.md) under the "Ref" column as `collection[1]`
through `collection[11]`.
