---
name: research-team
description: >-
  Research on any subject (technology, market, academic, product, current affairs, the user's own
  documents) that returns a short report in which every factual sentence cites evidence whose
  verbatim quote a script has matched against the cached source page, and whose key sentences a
  fresh-context verifier has checked against those sources. Parallel collectors with fixed tool
  budgets, one writer, one verification wave; written and checked in English, then translated
  into the request's language. Use it for "research this", "look into it", "why is this
  happening", "compare these and help me choose", "summarise it with evidence", "market
  research", in any language. A codebase question, a plan or code review, or a pure literature
  review (the literature-review skill beside this one) goes elsewhere.
allowed-tools:
- Bash
- Read
- Write
- Edit
- Glob
- Grep
- WebSearch
- WebFetch
- AskUserQuestion
- Agent
---

# research-team

Spend tokens on searching and on verifying the claims the answer rests on; spend none on
re-reading. The procedure is [references/procedure.md](references/procedure.md).

## Tier

| Tier | When | What runs |
|---|---|---|
| QUICK | one fact, definition or current value; being wrong costs little | the main session searches (at most 8 tool calls), checking each specific with a search even when it feels sure, and answers from the sources in the request's language with each source's full URL and date; no files |
| STANDARD | a comparison, choice or assessment that feeds one decision | procedure.md with 2-4 sub-questions |
| DEEP | money, external publication or a management decision rides on it; a contested subject; or the user asks for depth | procedure.md with 3-6 sub-questions and academic collection where studies matter |

Default to STANDARD when unsure. If the purpose, scope or tier is unclear, ask once, in one
AskUserQuestion of at most four questions: the tier (recommended option first), what the answer
will decide, the scope (region, period, subject), the aspects that matter most.

## How to start

| Session | Action |
|---|---|
| Running on Claude Fable | run procedure.md in this session |
| Any other model | launch `research-team-lead` with the Agent tool, `model: opus`, passing the request, the tier, the answers to the intake question and the local materials; tell the user the topic and tier in one line; relay its final message as it stands |

If the lead returns `{"error": "the Agent tool is unavailable"}`, run procedure.md in this session.

## Agents

| Agent | Model | Role |
|---|---|---|
| research-team-lead | opus | runs procedure.md when the session is on another model than Fable |
| research-collector | sonnet, effort medium | one sub-question, one source type, a fixed tool budget; writes JSONL |
| research-verifier | opus | up to five report sentences against their cited sources, without the report |

Pass `model` on every launch; never `fable`.

## Deliverables in `research/{YYYYMMDD}-{slug}/`

| File | Content |
|---|---|
| `brief.md` | decision, question type, sub-questions, hypotheses |
| `report.md` | the English report; every factual sentence cites `[E#]` |
| `report.{lang}.md` | the translation, when the request was not in English |
| `sources.md` | each cited source with its check result, the gaps, the search log |
| `evidence.jsonl`, `verdicts.json`, `pages/` | the evidence, the verification and the cached pages behind them |

The literature-review skill ships beside this one; the collector's academic route calls its
`paper_search.py`.
