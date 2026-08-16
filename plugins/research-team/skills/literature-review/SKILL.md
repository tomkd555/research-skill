---
name: literature-review
description: >-
  Academic literature review. Searches OpenAlex / arXiv / PubMed / Semantic Scholar through one
  deterministic script, ranks papers by venue and citation count, and builds an evidence table
  whose quotes are provably taken from the source abstracts. Two modes: survey (10-20 papers
  from abstracts, one context) and deep (full text of a handful of papers). Use it for requests
  such as "find the papers on this", "survey the literature", "go through the prior work",
  "what is known in this field", "read this paper closely", in any language.
  For market research, technology selection, or anything whose main
  sources are the general web (statistics, IR filings, reporting), use research-team instead.
allowed-tools:
- Bash
- Read
- Write
- Glob
- Grep
- WebSearch
- WebFetch
- AskUserQuestion
- Skill
- Agent
---

# Literature review (literature-review)

Academic search is cheap to do well because the metadata is structured. A DOI either resolves or
it does not; the venue, the year and the citation count come from the API; the abstract comes
back as text. None of that needs an agent's judgement, so no agent does any of it here.
`scripts/paper_search.py` performs every API call, de-duplicates across sources, ranks, and
grades. What reaches the model's context is a table of roughly one line per paper — a search of
37 papers writes 70 KB to disk and shows about 1 KB.

`{TOOL}` below is this skill's `scripts/paper_search.py`; substitute its absolute path at run time.
Run everything from the working directory where the deliverable belongs.

OpenAlex puts callers who identify themselves on a faster queue. Set `OPENALEX_MAILTO` to a
contact address to join it; without the variable the script still works, on the shared queue.

**Output language.** The structure is English and only English: the section headings and the
confidence labels, in the report and in every message to the user that carries one. The prose
follows the language of the request — the evidence `claim` text, the
report body, and every message to the user. `quote` stays in the language of the paper. Search in
whatever language the literature on the topic is written in — for most fields English — however
the report itself reads.

## Modes

| Mode | When | Cost |
|---|---|---|
| survey | "what is known in this field". 10-20 papers judged from their abstracts | One context, no subagents |
| deep | Specific papers whose method, numbers or limitations you need from the full text | survey plus one reader subagent per 3 papers |

Default to survey. Escalate to deep only when the abstract cannot answer the question — a
requested effect size, an experimental setup, a stated limitation.

**Choose the model by what the reading demands, not by the size of the job.** The tool does the
ranking, the DOI resolution and the grading, so extracting a claim and its quote from an
abstract is sonnet work. Raise a reader subagent to opus (the Agent tool's `model` parameter)
when any of these holds:

| Raise to opus when | Why |
|---|---|
| The answer turns on effect sizes, statistical method, or experimental design | Misreading a confidence interval or a confounder produces a confident wrong number |
| The literature is contested and both the majority and the minority position must be stated | Deciding what counts as a strong minority position is a judgement call |
| Being wrong is costly — medicine, safety, legal or regulatory compliance, money | The cost of the error, not the difficulty of the search |
| The reading is full text, not abstract | Pulling a method's real limitations out of a paper is the hardest part of this work |

Deciding the modes and the models, selecting the papers, and writing the report stay in the main
session whatever the subagents run on.

Run the whole procedure without stopping. The mode, the model tier and the paper selection are
yours to decide from the tables above — pick them and start searching rather than putting the
choice to the user, and do not narrate the options you rejected. Pause only where the work
genuinely needs the user: the topic is too ambiguous for any defensible query, or the request
turns out to belong to another skill. That is what `AskUserQuestion` is for and the only thing it
is for; if you do ask, end the turn on the question rather than on a promise to continue.

## Procedure

### 1. Queries

Write three to six queries covering four facets, in the language the literature on the topic is
written in:

- **overview** — `survey`, `systematic review`, `meta-analysis` on the topic
- **substance** — the mechanism, the method, or the measured quantity
- **disconfirmation** — `limitations`, `failed replication`, `negative results`, `criticism`.
  **Mandatory.** State before searching what you would observe if the expected answer were
  wrong, then search for it directly
- **application** — deployment reports, case studies, clinical practice

### 2. Search

```
python {TOOL} search "query 1" "query 2" "query 3" --db papers.json --limit 20 --year-from 2018
```

All queries and sources run in parallel in one process. Defaults to OpenAlex + arXiv.
Add `--source openalex,arxiv,pubmed` for medicine and life sciences, and
`,semanticscholar` when you want a second citation count (it throttles hard without an API key
and degrades to no results rather than failing).

Read the printed table. Columns are ID, year, citation count, grade, venue, title.

- **Grade** — A = peer-reviewed with a DOI, B = preprint, C = neither established. A grade-B
  paper is usable; say that it is a preprint, not peer-reviewed, wherever you cite it, in the
  language the report is written in.
- **Citation counts come from OpenAlex.** A paper found only through arXiv or PubMed shows 0;
  that is a missing count, not an uncited paper. Never rank on it alone.
- Do not select on recency alone. Weigh the venue and the citation count against the year.
  Establish the overview from surveys and meta-analyses first, then search the terms those
  surveys use to reach the primary work behind them (`--merge` folds a follow-up search into the
  same db and renumbers the IDs).

### 3. Read

```
python {TOOL} show --db papers.json P1 P4 P7
```

Pull abstracts only for the papers you selected — 10 to 20 in survey mode. In deep mode, fetch
the `fulltext` URL for the chosen papers with WebFetch; beyond three papers, launch one
general-purpose subagent per three papers, on the model the table above calls for.

Tell each subagent what the review is for and what its answer feeds into, not only its
assignment — a reader that knows the purpose connects the paper to it instead of guessing at
intent. Give it the paper IDs, the `fulltext` URLs, the question, and the evidence-unit format
below. Ask for everything it finds bearing on the question, including results that contradict
it, and filter in the main session: a subagent told to report only what matters reports less.

### 4. Evidence table

Write `evidence.json`:

```json
[
  {"id": "E1", "paper": "P3", "claim": "one sentence stating a falsifiable proposition, in the language of the request",
   "quote": "verbatim, up to about 40 words", "quote_source": "abstract"}
]
```

`quote_source` is `abstract` or `fulltext`. A quote from an abstract is checked mechanically; a
quote from full text is not, so quote it exactly and mark it. Never build a quote from a search
snippet or from your own summary.

```
python {TOOL} check --db papers.json --evidence evidence.json
```

The check must report zero FAILs before you write the report. This check replaces a verification
agent: a claim can only cite a paper the API actually returned, and an abstract quote can only be
text that paper actually contains. Report the run faithfully — say that you ran it, and if you
dropped or requoted an evidence unit to clear a FAIL, say which one and why. A FAIL that
disappears without explanation reads to the user as a check that passed.

### 5. Report

Attach `[E#]` to every sentence stating a fact. State confidence with one of four English labels
— certain / likely / possible / uncertain — whatever language the prose is in, and never as a
bare point estimate. Give the evidence hierarchy where it matters
(meta-analysis and systematic review > RCT > observational study > case study > expert
opinion). Put disconfirming and
conflicting findings in their own section, and say when a question is contested rather than
picking the majority side silently. Close with what the literature does not answer. Match the
report's length to what the evidence carries: cover every claim in the evidence table and the gaps
around it, and add no filler sections and no restatement of the search method.

Answer in the conversation, with the paper table attached, when the request was a question. Write
a document when the request asked for one, or when the review ran deep mode or cleared ten papers:
a single self-contained HTML file in the working directory, built with the session's report-design
skill, or plain semantic HTML carrying the same sections when the session has none. Give the user
the path either way.

Lead the closing message with the finding — the first sentence says what the literature says, not
what you did. The search log, the counts and the method come after. Keep that message short by
leaving things out, not by compressing it into fragments, abbreviations or arrow chains.

## Non-negotiable

- Every cited paper has a resolved DOI or arXiv ID. The script guarantees this; do not add papers
  to `evidence.json` by hand.
- The disconfirmation query runs and you record its result, including when it found nothing.
- Mark preprints as not peer-reviewed at every citation.
- Papers the search did not return do not enter the report, however well you remember them.

## Not covered

Citation-graph snowballing — finding the papers that cite a given paper — is not implemented;
search the terms the paper uses instead. Extending `paper_search.py` is not part of a review run:
note the gap where it bit and move on.
