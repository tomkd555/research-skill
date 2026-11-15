# research-team

research-team is a Claude Code plugin for research on any subject. Parallel collectors gather
quoted evidence, and a script then matches each quote against its cached source page. One writer
drafts the report from that evidence. Verifiers, each in a fresh context, then check its key
sentences against their sources. The report is written and checked in English and finally
translated into the language of the request.

The plugin also ships `literature-review`, a skill that searches the academic literature in
OpenAlex, arXiv, PubMed and Semantic Scholar.

## Requirements

The plugin needs Python 3 and Claude Code's WebSearch and WebFetch tools. Its scripts use only
Python's standard library, apart from `pypdf`, which reads PDF sources.

## Install

```
/plugin marketplace add tomkd555/research-skill
/plugin install research-team@research-skill
```

## Usage

Ask Claude to research a subject. You can write the request in any language. The research-team
skill picks one of three tiers for the request:

| Tier | Kind of request | Output |
|---|---|---|
| QUICK | a question about one fact, definition or current value | an answer in the conversation, with source URLs and dates |
| STANDARD | a comparison or choice that feeds one decision | a report under `research/{YYYYMMDD}-{slug}/` |
| DEEP | a request that involves money, an external publication, a management decision or a contested subject | the same report, built from more sub-questions and more follow-up searches |

### Files a run writes

A STANDARD or DEEP run writes:

| File or folder | Content |
|---|---|
| `report.md`, `report.{lang}.md` | the report and its translation; every factual sentence cites its evidence by id, such as `[E3]` |
| `sources.md` | each cited source with its check result, the gaps in the evidence, the leads the collectors surfaced, and the search log |
| `brief.md` | the plan: the decision, the sub-questions and the hypotheses |
| `evidence.jsonl` | the collected evidence |
| `screen.json` | the screener's result for each report sentence |
| `verdicts.json` | the verifiers' verdicts |
| `pages/` | the cached source pages |

## Agents

| Agent | Role |
|---|---|
| research-team-lead | runs the research procedure, writes the report and launches the other agents |
| research-collector | collects evidence for one sub-question within a fixed tool budget; one more collector covers topics related to the request |
| research-screener | compares every report sentence with the quotes it cites |
| research-verifier | checks the sentences the screener flagged, and the key sentences, against their sources without seeing the report |

## License

MIT
