---
name: research-team
description: >-
  Research on any subject (technology, market, academic, product, current affairs, the user's own
  documents) that returns a short report in which every factual sentence cites evidence whose
  verbatim quote a script has matched against the cached source page, and whose key sentences a
  fresh-context verifier has checked against those sources. Parallel collectors with fixed tool
  budgets search past what an overview says and cover what surrounds the request; one writer,
  one verification wave; written and checked in English, then translated into the request's
  language. Use it for "research this", "look into it", "why is this
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
re-reading. Three things make a report worth reading, and the procedure enforces each: it goes
past what any overview of the subject says, it covers what surrounds the request as well as
the request, and it says of a study only what the study's design carries. The procedure is
[references/procedure.md](references/procedure.md).

## Tier

| Tier | When | What runs |
|---|---|---|
| QUICK | one fact, definition or current value; being wrong costs little | the main session searches (at most 8 tool calls), checking each specific with a search even when it feels sure, and answers from the sources in the request's language with each source's full URL and date, adding one line when the searches showed something beside the answer that changes how to read it (a newer value, a competing definition, an alternative that fits better); no files |
| STANDARD | a comparison, choice or assessment that feeds one decision | procedure.md with 2-4 sub-questions, a breadth collector and up to 2 follow-ups |
| DEEP | money, external publication or a management decision rides on it; a contested subject; or the user asks for depth | procedure.md with 3-6 sub-questions, a breadth collector and up to 4 follow-ups |

Both tiers add an academic collector where a sub-question turns on studies.

Default to STANDARD when unsure. If the purpose, scope or tier is unclear, ask once, in one
AskUserQuestion of at most four questions: the tier (recommended option first), what the answer
will decide, the scope (region, period, subject), the aspects that matter most.

## How to start

| Session | Action |
|---|---|
| Running on Claude Fable | run procedure.md in this session |
| Any other model | launch `research-team-lead` with the Agent tool, `model: opus`, passing the request, the tier, the answers to the intake question, the local materials and the skill directory (the absolute path of the directory that holds this SKILL.md); tell the user the topic and tier in one line; relay its final message as it stands |

If the lead returns `{"error": "the Agent tool is unavailable"}`, run procedure.md in this session.

## Agents

| Agent | Model | Role |
|---|---|---|
| research-team-lead | opus | runs procedure.md when the session is on another model than Fable |
| research-collector | sonnet for `web`, opus for `academic`; effort medium | one sub-question, one source type, a fixed tool budget; mode focus digs past the usual account, mode breadth covers what surrounds the request; writes evidence, searches and leads as JSONL |
| research-screener | sonnet, effort medium | every report sentence against its cited quotes, one batch of 40; labels drift (a study read for more than its design carries included), uncited facts and readings under a source marker |
| research-verifier | opus | up to five report sentences against their cited sources, without the report; reads the study behind a sentence that cites one |

Pass `model` on every launch; never `fable`.

## Deliverables in `research/{YYYYMMDD}-{slug}/`

| File | Content |
|---|---|
| `brief.md` | decision, question type, field terms, territory, sub-questions, hypotheses |
| `report.md` | the English report: Answer, Findings, Beyond the question, Disagreements and limits; every factual sentence cites `[E#]` |
| `report.{lang}.md` | the translation, when the request was not in English |
| `sources.md` | each cited source with its check result, the gaps, the leads the collectors surfaced, the search log |
| `evidence.jsonl`, `screen.json`, `verdicts.json`, `pages/` | the evidence, the screen, the verification and the cached pages behind them |

The literature-review skill ships beside this one; the collector's academic route calls its
`paper_search.py`, which searches, lists the recent papers and follows the citation graph.
