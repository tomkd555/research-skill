---
name: research-team
description: >-
  General-purpose research team (an orchestrator over a group of agents). For any subject
  (technology, market, academic, product, current affairs, a case with the user's own
  documents), it runs five stages — planning (question analysis: the decision, the question type,
  the presuppositions; key-question decomposition, competing hypotheses, disconfirmation plan),
  parallel collection (web and user-supplied materials, collection floors, source grades, search
  log), one wave of independent verification (citation existence, verbatim-quote matching,
  disconfirmation search, corroboration) with a rival analyst answering from the evidence alone,
  synthesis (an Analysis section — hypothesis matrix, mechanism, source incentives, premortem —
  written before the conclusion; an evidence ledger with every claim linked to an ID; the
  seven-level confidence vocabulary), and one audit (deterministic check scripts plus an auditor
  agent) — and produces a corroborated research report. Use it for requests such as "research
  this", "look into it", "why is this happening", "dig deeper", "verify this", "compare these and
  help me choose", "summarise it with evidence", "market research", "help me pick a technology",
  in any language.
  Do not use it for requests that a codebase search alone answers, for reviewing
  implementation plans and code, or for a pure literature review with no web-information side
  (the literature-review skill, which ships beside this one, covers that at a fraction of the
  cost).
allowed-tools:
- Bash
- Read
- Write
- Glob
- Grep
- WebSearch
- WebFetch
- AskUserQuestion
- Task
- Agent
---

# General-purpose research team (research-team)

This skill orchestrates research on any subject, producing findings in a structure an LLM can
interpret and evaluate correctly. It distributes collection, verification, and auditing across
subagents, and owns four rule files that are the source of record for the rules themselves.

**Output language.** The section headings, the table headers, and the confidence labels are
English and only English — in every deliverable, and in every message to the user that carries
one, because such a message transcribes the report rather than restating it. A label is written
with its band as `roughly even chance (45-65%)`, never translated and never reworded. The prose
around them is written in the language of the request — the body of `research_brief.md` and
`report.md`, the evidence `claim` text, and every message to the user. `verbatim_quote` stays in the language of the source. Settle the
language at Step 0, record it in the ledger's top-level `deliverable_language`, and pass it to
`merge_fragments.py` as `--deliverable-language`; nothing else takes a language flag, because
`scripts/labels.py` holds one English set of names and the check scripts all read it. A collection
agent picks the language of each query for itself while collecting; that judgement is neither
planned nor recorded.

## How to start

| Situation | What to do |
|---|---|
| A research request arrives in the main session | Launch the `research-team-lead` agent with the Agent tool and delegate the whole pipeline. This keeps the main session's context free. **This is the default.** |
| LIGHT (below) | Answer in the main session with WebSearch / WebFetch. Write no files |
| You must run STANDARD or DEEP in the main session yourself | Read [references/pipeline.md](references/pipeline.md) first, then follow it |

## Mode selection

Decide the mode first. If the decision is unclear, fold it into the Step 0
AskUserQuestion rather than spending a turn on it. Where asking is impossible, default to STANDARD
and record the default in research_brief.

| Mode | Condition | Setup |
|---|---|---|
| LIGHT | Confirming a single fact, definition, or current value. The cost of being wrong is low | The main session searches directly with WebSearch / WebFetch. Sources (full absolute URL, publication date) are mandatory. If there is only one source, say so explicitly |
| STANDARD | Comparison, selection, or situation assessment that feeds one decision | Run Steps 1–6 with reduced floors. Agent verification (Step 3) covers the claims that carry the conclusion, the conflicts and the citation failures |
| DEEP | Serious stakes (money, external publication, management decisions), multiple issues, a contested subject, or the user explicitly asks for depth ("be thorough", "go deep") | The full pipeline plus the audit gate. Floors apply per decision relevance: decision KQs get the full floors, background KQs get the STANDARD floors |

A study that starts as STANDARD escalates to DEEP once source conflicts, serious stakes, or a
proliferation of issues emerge. It never de-escalates.

## The rules and where they live

This document does not duplicate the content of the files below.

| Principle | Source of record | What it defines |
|---|---|---|
| The procedure and the delegation | [references/pipeline.md](references/pipeline.md) | Steps 0–6: intake, question analysis and planning, collection, the ledger turn and verification, synthesis, evaluation, delivery; the launch instruction, model and scale rule for every agent; error handling |
| Collection standards | [references/collection_standards.md](references/collection_standards.md) | Collection floors, the four search facets, the disconfirmation duty, source grades, independence, freshness, page-fetch rules — the human-facing source of record; the collector and scholar definitions carry the operative text, and `tests/test_standards_sync.py` keeps the numbers equal |
| Interpretation contract | [references/interpretation_contract.md](references/interpretation_contract.md) | Hand-off between agents, separation of fact and insight layers, the bias procedures, the seven-level confidence vocabulary, retry rules, the final-message contract |
| Evaluation protocol | [references/evaluation_protocol.md](references/evaluation_protocol.md) | The design principles, the rubric R1–R16 (carried operatively by the auditor definition), confidence calibration, the minimum re-run scope |

The academic grounding for these rules is collected in
[references/methodology_sources.md](references/methodology_sources.md) (every citation has a
verified DOI or arXiv ID). It is bibliography only; no execution path reads it.

## Deliverables and directory

The output directory is `research/{YYYYMMDD}-{topic-slug}/` unless the user specifies one.
In LIGHT mode, write no files; answer in the conversation with sources attached.

| File | Content | Checked by |
|---|---|---|
| `research_brief.md` | The research plan (question analysis, KQs, competing hypotheses, disconfirmation plan, source plan, stopping rules) | `scripts/research_plan_linter.py` |
| `materials/` (or the paths the user named) | The local materials the user supplied, ingested in place through `scripts/fetch_page.py` into `pages/` | — |
| `evidence_fragments/kq{N}_{role}.json` | The evidence fragment each collection agent writes | The collection agent self-checks with `scripts/validate_fragment.py`; `scripts/merge_fragments.py` checks again on intake |
| `pages/{hash}.txt` / `pages/index.json` | The cached text of every fetched source page, written by `scripts/fetch_page.py`. Agents copy quotes out of it, and it answers a re-read without a second request | — |
| `evidence_log.json` | The evidence ledger (all evidence units, disconfirmation records, search log, gaps) | `scripts/evidence_auditor.py` |
| `id_map.json` / `unmerged_report.json` | Temporary-to-final ID mapping, and fragments or evidence that could not be merged | — |
| `citation_input.json` | A copy of the ledger, taken so the citation check does not race writes to it | — |
| `citation_check.json` | Deterministic citation-check results for every evidence unit (URL reachability, DOI and arXiv resolution, quote match against the live page or the cached local file) | — |
| `verification/targets_{BATCH_ID}.json` | The claim payload per batch of up to five claims (a projection of the claims plus their citation-check records) | Generated by `scripts/select_verification_targets.py` |
| `rival.json` | The rival analyst's independent answer, its case, and the evidence it names as missing | Read by the lead at Step 4 and by `scripts/report_auditor.py --rival` |
| `verification/verdicts_{BATCH_ID}.json` | The verifier agents' verdicts | `scripts/apply_verdicts.py` applies them to the ledger |
| `kq_slices/KQ{n}.md` | Per-KQ evidence extracts (the reading unit for the rival and for split synthesis) | — |
| `report.md` | The final report (every claim links to a ledger ID) | `scripts/report_auditor.py` |
| `audit_digest.json` / `audit_sample.json` | The ledger digest and sampling targets handed to the auditor agent | Generated by `scripts/build_audit_input.py` |
| `audit_result.json` | Audit results (script output plus the auditor agent's verdict) | — |

## The agents

These live in `<plugin root>/agents/` under the research-team plugin, and in `~/.claude/agents/`
under a manual install. Each definition is the source of record for how that agent works and
carries every rule it needs, so no agent reads a reference file at run time;
`references/pipeline.md` holds what the launcher decides (the launch instruction, the model, the
scale rule, error handling).

| Agent | Responsibility | Prohibited |
|---|---|---|
| research-team-lead | Running the whole pipeline (the delegation entry point; opus) | Doing the work alone without launching specialists. Reporting a key figure that has not been verified |
| research-collector | Web and local-material evidence collection and search logging for one KQ | Writing insights or recommendations. Passing over a floor shortfall in silence |
| research-scholar | Academic literature collection for one KQ (paper_search.py, DOI resolution, evidence hierarchy) | Accepting a paper paper_search.py did not return. Calling the academic APIs with WebFetch. Selecting without checking citation counts and venue |
| research-verifier | Independent verification per claim (citation existence, agreement, disconfirmation, corroboration) | Starting from an endorsement of the collector's judgement |
| research-rival | An independent answer to the decision from the evidence slices alone (opus) | Reading the brief, the hypotheses, the draft or the report |
| research-auditor | Final audit of the report and ledger (rubric plus sampling checks) | Editing the deliverables (it returns findings only) |

Every agent returns structured results (JSON or a fixed table). Launch agents in parallel within a
single message, launching every agent that stage needs at once (the launch cap and its rationale
are in [references/pipeline.md](references/pipeline.md), "Shared conventions"). The lead waits on
agents three times in a run: the collection, the verification, and the audit.

research-scholar owns academic literature collection; the pipeline does not depend on third-party
plugins such as deep-research. It does depend on the `literature-review` skill, which ships beside
this one and provides `scripts/paper_search.py`. A request that is purely a literature review — no
web statistics, no IR filings, no reporting — belongs to that skill instead, which runs the same
paper search in the main session without the five-stage pipeline.
