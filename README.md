# research-team

A Claude Code plugin for research on any subject. It returns a short report in which every
factual sentence cites evidence, every cited quote has been matched by a script against the cached
source page, and the sentences the answer rests on have been checked against their sources by a
verifier that never saw the report.

Version 2.0 is built around one rule: **spend tokens on searching and on verifying the claims the
answer rests on; spend none on re-reading.** It replaces the five-stage pipeline of 1.x, which
spent 60-80 million input tokens and 33-94 minutes per run; 42-44% of that input went to a lead
agent re-reading a context of 230k-320k tokens on every turn.

## How a run works

1. **Scope.** The orchestrator writes a one-page brief: the decision the answer serves, the
   question type, the presuppositions to verify, 2-6 sub-questions and the competing hypotheses.
2. **Collect.** One `research-collector` per sub-question (Sonnet), all in parallel, each with a
   fixed tool budget (12 in STANDARD, 20 in DEEP). It stops early once two searches in a row add
   nothing, spends at least one search on opposing evidence, and writes JSONL: an English claim,
   a verbatim quote copied from the cached page, the full URL, a grade. Academic sub-questions
   go through `paper_search.py` (OpenAlex, arXiv, PubMed, Semantic Scholar).
3. **Check.** `check.py` merges the items and re-checks every quote against the cached page,
   every URL, DOI and arXiv ID, and writes one digest per sub-question.
4. **Write.** The orchestrator writes an outline from the digests, then the English report once.
   Every factual sentence ends with its evidence ids, `[E3]`.
5. **Verify.** `select_claims.py` takes the cited sentences up to the tier's cap: the Answer
   first, then every sentence with a number, then the rest in report order.
   `research-verifier` agents (Opus), five sentences each, re-read the cited passages, search once
   for opposing evidence, and mark each sentence supported, partial, unsupported or contradicted.
   They see the sentence and its sources only.
6. **Patch and check.** The orchestrator rewrites only the flagged sentences; `report_check.py`
   fails the report on a dangling id, an uncited number or a flagged sentence left in place.
7. **Translate.** For a request in another language, the checked English report is translated,
   and `report_check.py --translation` confirms that every id, number and heading survived.

**Tiers.** QUICK answers one fact in the conversation with sources and writes no files. STANDARD
uses 2-4 sub-questions and verifies up to 10 sentences. DEEP uses 3-6 sub-questions, adds
academic collection where studies matter, and verifies up to 25.

## Why it is built this way

The design follows a survey of eight well-regarded research projects (STORM, GPT Researcher,
open_deep_research, dzhng/deep-research, hyperresearch and three Claude Code skills) and the
published evidence on research agents. The sources are listed with their arXiv IDs in
[methodology_sources.md](plugins/research-team/skills/research-team/references/methodology_sources.md).

- Token use explains most of the variance in research-agent performance, so tokens go to search
  and verification. A verifier buys the same accuracy gain for about a fifth of the tool calls
  that more searching needs (arXiv:2510.06135).
- Deep-research systems leave 20-60% of citations unsupported (arXiv:2509.04499), so quotes are
  checked by a script and key sentences by a verifier.
- Parallel agents help collection; one writer writing once avoids disjoint, repetitive reports.
- An outline built from the evidence before writing raises organisation and coverage in STORM's
  evaluation (arXiv:2402.14207).

## Install

```
/plugin marketplace add tomkd555/research-skill
/plugin install research-team@research-skill
```

Then ask for research in the ordinary way, in any language. In a session on Claude Fable, the
main session runs the procedure itself. On any other model, the skill launches
`research-team-lead` on Opus.

## What you get

A run writes into `research/{YYYYMMDD}-{topic-slug}/`:

| File | Content |
|---|---|
| `brief.md` | the decision, question type, sub-questions and hypotheses |
| `report.md` | the English report; every factual sentence cites `[E#]` |
| `report.{lang}.md` | the translation, for a request in another language |
| `sources.md` | each cited source with its check result, the gaps, the search log |
| `evidence.jsonl`, `verdicts.json` | the checked evidence and the verifiers' verdicts |
| `pages/` | the cached text of every source, so any quote can be re-checked |

## Measured results

{filled from eval/README.md after the evaluation runs}

## Requirements

- Claude Code with plugin support.
- Python 3 on `PATH`; the scripts use the standard library only. Tested on 3.11.
- WebSearch and WebFetch enabled. Claude Code caps WebSearch at 200 calls per session by
  default, shared by every agent; raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` to run two or
  more DEEP studies in one session.
- Optional: `OPENALEX_MAILTO` set to a contact address routes academic searches to OpenAlex's
  faster pool.

## Upgrading from 1.x

2.0 changes the run directory layout. Run directories written by 1.x keep their files but cannot
be re-checked with the 2.0 scripts. The rival analyst and the audit agent are gone; their work
moved to the verifier and `report_check.py`.

## Layout

```
.claude-plugin/marketplace.json
plugins/research-team/
  agents/                        research-team-lead, research-collector, research-verifier
  skills/research-team/          SKILL.md, references/procedure.md, scripts/, assets/
  skills/literature-review/      paper_search.py and its own skill
tests/                           repository only
eval/                            the evaluation protocol and the token measurement
```

## Tests

```
for t in tests/test_*.py; do python "$t"; done
```

They use the standard library and a local HTTP server; none of them reach the network.

## License

MIT. See [LICENSE](LICENSE).
