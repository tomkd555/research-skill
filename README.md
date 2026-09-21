# research-team

A Claude Code plugin that runs research as a pipeline instead of a single prompt. It splits a
question into key questions, sends a team of subagents to collect evidence, and has a second set
of agents attack that evidence from the sceptic's side. No report ships until deterministic
scripts and an auditor agent have both passed it.

Every claim in the final report carries the ID of an evidence unit. Every evidence unit carries a
verbatim quote, a full absolute URL, and a source grade. A Python script re-fetches each URL and
checks the quote against the page character by character, so a citation that was paraphrased,
invented, or attached to the wrong source fails before a human ever reads it.

**The report's structure is English; its prose follows the language you asked in.** The section
headings, the table headers and the confidence labels are always English, so one set of checks
reads every report, whatever language the request used. The body of the report, the research brief and the
claim text are written in the language of the request, which the evidence ledger records in its
top-level `deliverable_language` field. Verbatim quotes stay in the language of the source. A
collection agent picks the language of each query for itself, searching wherever the best sources
for its key question happen to be written.

## What it does

**Five stages.**

1. **Question analysis and planning** — write down the decision the answer serves, the question
   type (descriptive, diagnostic, evaluative, prescriptive, predictive), the presuppositions the
   request rests on (each marked verify or accept), the useless answer, and the pivotal
   observation; derive 2-7 key questions from the decision; state two or more competing
   hypotheses and what would be observed if each were false, before searching. A linter checks the
   plan and estimates the session's WebSearch budget.
2. **Parallel collection** — one agent per key question, launched in a single message.
   `research-collector` handles the general web (statistics, IR filings, reporting) and the local
   materials the user supplied (PDF, DOCX, text, HTML), ingested into the same page cache;
   `research-scholar` handles academic literature through OpenAlex, arXiv, PubMed and Semantic
   Scholar. Each agent must clear a floor of queries, independent sources, and disconfirmation
   queries before it may return.
3. **One wave of independent verification** — a deterministic citation check covers every
   evidence unit (URL, DOI, arXiv ID, verbatim quote against the page or the cached local file);
   `research-verifier` then takes up to five claims at a time — the conflicts, the citation
   failures, the uncorroborated key figures and the claims that carry the conclusion — in a
   context that never saw the collection, and tries to break them. In the same message,
   `research-rival` answers the decision from the evidence slices alone, without the brief or the
   draft, and the lead writes its first draft while they run.
4. **Synthesis** — the Analysis section comes first: a hypothesis matrix, the mechanism, the
   outside view, the source incentives, second-order effects and a premortem, as the question type
   requires, plus the reconciliation with the rival's reading (a disagreement caps the confidence).
   The writer works from per-key-question evidence extracts, keeps fact and interpretation in
   separate layers, and confines every estimate to a seven-level confidence vocabulary mapped onto
   probability bands.
5. **One audit** — deterministic scripts check the ledger and the report, then `research-auditor`
   grades both against a 16-item binary rubric and samples atomic facts. The lead applies the
   findings once and delivers.

**Three modes.** LIGHT answers a single factual question in the main session and writes no files.
STANDARD runs the pipeline with reduced floors for one decision. DEEP runs the full pipeline with
the full floors on the decision-carrying key questions. Both wait on agents three times: the
collection, the verification, and the audit. A study escalates from STANDARD to DEEP when sources conflict or the stakes turn
out to be serious; it never de-escalates.

**Collection floors**, per key question:

| | DEEP (decision) | DEEP (background) and STANDARD |
|---|---|---|
| Search queries | 12+ | 6+ |
| Independent sources | 5+ | 3+ |
| Disconfirmation queries | 2+ | 1+ |

DEEP holds `research-collector` and `research-scholar` to these floors separately. STANDARD counts
the total across both roles for one key question, and asks each role for at least three queries
and one disconfirmation query. LIGHT sets no query floor.

**Source grades.** A is governments, international organisations and peer-reviewed papers; B is
industry bodies, corporate IR and research firms; C is trade media, reporting and blogs. The
pipeline rejects a key figure that rests only on grade-C sources.

Four reference files under `plugins/research-team/skills/research-team/references/` state the
design rules (the agent definitions carry the operative text, so no agent reads a reference file at run time), and `methodology_sources.md` holds the academic grounding for them — every citation
with a verified DOI or arXiv ID.

## Install

```
/plugin marketplace add tomkd555/research-skill
/plugin install research-team@research-skill
```

The marketplace is named `research-skill` since 1.1.0 (earlier releases declared `tomkd555`,
which collided with the scan-research marketplace of the same name). An install made under the
old name shows `research-team@tomkd555`; remove it with `/plugin uninstall research-team@tomkd555`
and install again with the two lines above.

Then ask for research in the ordinary way, in any language: "research X and give me sources",
"look into X", "compare these and help me choose", "summarise it with evidence". The skill picks
the mode and launches `research-team-lead`, which runs the pipeline in its own context.

## What you get

A run writes into `research/{YYYYMMDD}-{topic-slug}/`:

| File | Content |
|---|---|
| `research_brief.md` | The plan: key questions, competing hypotheses, disconfirmation plan, stopping rules |
| `evidence_log.json` | The ledger: every evidence unit, the disconfirmation records, the search log, the gaps |
| `pages/` | The cached text of every fetched page, so a quote can be re-checked without a second request |
| `report.md` | The report, every claim linked to a ledger ID |
| `audit_result.json` | The script findings and the auditor agent's verdict |

## Requirements

- Claude Code with plugin support.
- Python 3 on `PATH`. The scripts use the standard library only — no packages to install. Tested
  on 3.11.
- WebSearch and WebFetch enabled. Claude Code caps WebSearch at 200 calls per session by default
  and then returns a budget message instead of results, so the planning linter estimates the run's
  query total and fails a plan that would exceed the cap. Raise
  `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` or cut key questions.
- Optional: set `OPENALEX_MAILTO` to a contact address. OpenAlex routes callers who identify
  themselves to a faster pool. The scripts send the address only when you set the variable, and the paper search works
  either way.

## Layout

```
.claude-plugin/marketplace.json
plugins/research-team/           everything an install copies
  .claude-plugin/plugin.json
  agents/                        6 agent definitions (lead, collector, scholar, verifier, rival, auditor)
  skills/research-team/          SKILL.md, references/, scripts/, assets/
  skills/literature-review/      paper_search.py and its own skill, bundled
tests/                           repository only, never installed
```

`skills/research-team/scripts/labels.py` holds one English set of section names, confidence
labels and prose patterns. The generator that writes the scaffold, and every check script that
reads a deliverable, take their vocabulary from it, so none of them needs a language flag.

`literature-review` ships here because `research-scholar` calls its `paper_search.py` for every
academic search. It is a usable skill on its own: a literature review with no web-information
side costs a fraction of the full pipeline.

## Tests

```
for t in tests/test_*.py; do python "$t"; done
```

The tests live outside `plugins/`, so installing the plugin copies none of them. Ten files cover
the check scripts and one covers the paper search. They use the standard library and a local HTTP
server; none of them reach the network.

## License

MIT. See [LICENSE](LICENSE).
