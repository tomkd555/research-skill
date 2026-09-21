# Interpretation contract (the source of record for interpreting research results correctly)

LLM interpretation errors come in known shapes: overlooking information placed in the middle of a
long context (source [1]), sycophancy toward the user's view (source [2]), accepting unverified
presuppositions (source [3]), judgements that shift with presentation order (source [4]),
fabricated bibliographic details (source [5]), and confusing stale training knowledge with
search results (source [6]). This document sets out the countermeasures as rules in four
layers: the structure of evidence, the hand-off between agents, synthesis, and expression.

A deliverable's structure is English: its section headings, its table headers and its confidence
labels, all held in `scripts/labels.py`, which is the source of record for them. The prose under
those headings — the claims, the conclusions, the report body — is written in the language of the
request, which the ledger records as `deliverable_language`.

## 1. The structure of an evidence unit

Every fact is recorded as an evidence unit (the machine-readable definition is
`assets/evidence_log.schema.json`; the field-by-field table a collector works from is in its own
definition, `agents/research-collector.md`). The fields that carry the interpretation accuracy:

| Field | Rule |
|---|---|
| id | E1, E2, … Every claim in the report links to one of these |
| kq_ids | The IDs of the key questions it answers (more than one is allowed) |
| claim | **One falsifiable proposition**, in the third person. No causation, implication, or recommendation — those belong to the insight layer |
| claim_type | fact (observed), estimate (projection or forecast), opinion (the publisher's view) |
| verbatim_quote | A **verbatim quote** from the source, in its original language, up to about 40 words. No summary or paraphrase |
| source | publisher / title / url (a full absolute URL, never abbreviated) / published / grade / origin_cluster |
| accessed | Access date (YYYY-MM-DD) |
| is_key_figure | true when the figure drives a conclusion |
| corroboration | corroborated / single_source / conflicting (collection_standards.md §6) |
| verification | The verification-stage result: confirmed / plausible / disputed / refuted / unchecked |
| source.doi | Optional. The source's DOI (e.g. "10.18653/v1/2023.emnlp-main.398"). When present, citation_verifier.py checks that it resolves |
| source.arxiv_id | Optional. The source's arXiv ID (e.g. "2402.14207"). When present, citation_verifier.py checks that it resolves |
| archive | Optional. A Wayback Machine snapshot `{wayback_url, timestamp}`, recorded as an alternative route when the URL is unreachable |
| superseded_by | Optional. A replacement marker used when conflicting newer evidence is confirmed (e.g. "E37"). **Never delete the original evidence unit** — write the new evidence's ID into this field to show the replacement |
| self_reported | Optional (default false). true when the figure or effect size comes from the method's proposer, a vendor, or an interested party |
| lineage | Optional. `{collected_by, kq_id, fragment_file}`. Records which agent run produced this evidence, and from which key question |

Those last six fields are all optional. The ledger's version lives in its top-level `schema`
field (`research-evidence-1.3` and the like); the minor version increments within 1.x and stays
backward compatible with existing ledgers. `superseded_by` exists to preserve the
ledger's history: when conflicting new evidence appears, the original evidence unit is neither
deleted nor overwritten. For evidence with `self_reported: true` that is also `is_key_figure`,
add an attempt at independent corroboration to the corroboration duty in
collection_standards.md §6.

Three things about this structure carry the interpretation accuracy.

1. **Propositional form**: writing "the X market was worth Y in 2025, per Z's survey" rather
   than a vague observation such as "X is growing" makes the statement true or false, which lets
   the later verification, corroboration, and disconfirmation run mechanically
2. **Verbatim quotes**: they make it checkable whether a generated claim is actually written in
   the source (whether it is attributable). LLMs generate bibliographies that do not exist and
   content that is absent from sources that do (source [5]); the countermeasure is not "cite a
   source" but "quote the passage verbatim and match it" (the attributability approach of
   source [7])
3. **Separating claim_type**: synthesising facts, estimates, and opinions as one kind lets a
   publisher's promotion or forecast propagate as fact. Record them by type, and keep them
   distinct in the report

## 2. Rules for the hand-off between agents

- **Structured responses are mandatory**: a subagent's response is fixed to JSON — the evidence
  array fragment plus the search-log fragment. Free prose is prohibited, because prose invites
  reinterpretation at merge time, which means degradation and contamination
- **Self-contained instructions**: subagents have no conversational context. The instruction
  states the assigned KQ, the as-of date, the mode, and the full paths of every file to read
- **Separating the fact layer from the insight layer**: collection agents return facts only.
  Insights, implications, and recommendations are written at the synthesis stage (Step 4) by the
  caller alone, and every one of them must be traceable back to an evidence ID. An insight that
  cannot be traced back does not go in the report
- **Carrying numbers**: a number travels as one set — value, unit, denominator, period,
  definition. Carry only "up 50%", and once the denominator and the period are gone, no one can verify the number

## 3. Rules for synthesis (countering long contexts)

A model uses information placed in the middle of a long context less than information at the start
or the end (source [1]). In DEEP research, where the ledger grows large, observe the following.

- **Split synthesis**: read the evidence per KQ, synthesise in small pieces, produce per-KQ
  conclusions, and only then synthesise across them. Never load all the evidence into the
  context and write in one pass
- **Restating key facts**: restate evidence that drives a conclusion in the KQ coverage
  table, separately from the body. The table doubles as a detector for what was missed
- **Draw from the ledger**: when writing the report, always re-read the per-key-question slices
  in `kq_slices/` to source a fact (they are extracts `render_scaffold.py` generated from the
  ledger, and reading one is equivalent to reading the ledger). Evidence belonging to no key
  question is in `kq_slices/cross_cutting.md`. Do not write from memory — the residue of the
  context so far. Do not overwrite search results with training-time knowledge (source [6];
  change after the as-of date is "not investigated", not "absent")

## 4. Operating procedures against known biases

| Known shape | Procedure |
|---|---|
| Sycophancy (source [2]) | Register the user's initial hypothesis as competing hypothesis H1 and do not privilege it. Search for supporting and disconfirming evidence with equal effort. Never count the user's approval as evidence |
| Accepting unverified presuppositions (source [3]) | Presuppositions embedded in the request (such as "now that X has become the mainstream choice, ...") are listed in research_brief's Question analysis block, each marked `verify → KQn` or `accept — reason`, before any search runs. A `verify` presupposition is a key question or a verification target; none is treated as fact before verification |
| Order effects (source [4]) | When comparing several options or hypotheses, read the hypothesis matrix once by row and once by column before naming the survivor, and check that the conclusion does not move with the order |
| A confidently wrong frame | The rival analyst (`research-rival`) answers the decision from the evidence slices alone, without the brief or the draft; the report reconciles with it in the Analysis section and caps its confidence where they differ (pipeline.md Step 4) |
| Anchoring (source [8]) | Do not make the first figure you find the reference point. For key figures, line up the values from independent sources before deciding a representative value and a range. For a forecast, the outside view's base rate is the reference point |

## 5. Rules of expression (how to write the report)

- Attach an evidence ID `[E#]` to every sentence stating a fact. Never write an assertion
  without one
- Express estimates and forecasts with the seven-level confidence vocabulary plus a probability
  band (point estimates are prohibited; the vocabulary is below). Do not use vague hedges such
  as "it may be", "it seems", "probably"
- Use absolute dates ("June 2026") rather than relative ones ("last year", "recently", "now"),
  and state the as-of date at the top of the report
- Give every number its unit, denominator, period, and definition. For a value given as a rate,
  confirm the denominator; for one given as a count, confirm its ratio to the population
- Put conflicting information and disconfirmation in their own section, reachable from the
  conclusions in the body. Never hide unfavourable evidence in a footnote or by omission

### Confidence vocabulary (seven levels)

Estimates and forecasts use these seven labels, and no other label or probability band is mixed
into the same document. The labels stay in English whatever language the prose is in — in the
report and in any message to the user that carries one — and a label is written with its band as
`roughly even chance (45-65%)`, never translated and never reworded. Pairing a
label with a probability band follows the intelligence-analysis standard for mapping estimative
language onto probability ranges (sources [9][10]); the wording is that standard's own
(US ODNI ICD 203).

| Label | Band |
|---|---|
| almost certain | 90-100% |
| very likely | 80-90% |
| likely | 65-80% |
| roughly even chance | 45-65% |
| unlikely | 20-45% |
| very unlikely | 10-20% |
| almost no chance | 0-10% |

`scripts/labels.py` holds the same table and is what the check scripts read.

## 6. Retry rules for schema-validation failures

This section covers what to do when an evidence fragment JSON fails the schema or a
deterministic check (`scripts/evidence_auditor.py` and the like). It addresses the case where a
response arrived but failed those checks. The rule for
relaunching a subagent that failed to produce a structured response at all (a response that is
not valid JSON, say) is a different rule, whose source of record is `pipeline.md`'s error-handling
section. The two
kinds of failure differ, so the retry counts differ too.

1. Re-request from the same agent, attaching a verbatim list of the failing fields and the
   reasons (at most twice; informed by the re-request design in source [12])
2. If both attempts fail, the parent (the main session or the lead) fixes what can be fixed
   mechanically
3. Where it cannot be fixed, register the evidence as degraded: lower its confidence_band by
   one level and record the reason in `note`

Conforming to the schema guarantees the structure of the output and nothing about the
reliability of its content (source [11]). The degraded mark exists to keep visible, rather than delete, evidence whose structure is intact but whose certainty has dropped.

## 7. The final-message contract at delivery

The final message at Step 6 (delivery) keeps this order.

1. Summary (with a confidence label, in the English wording of §5 and with its band)
2. Key findings (each line carrying an evidence ID `[E#]`)
3. The rival reading in one line: the rival's answer, whether the report agrees or differs, and
   what would settle it
4. Disconfirming evidence and limitations
5. Audit verdict (the deterministic checks' FAIL/WARN counts plus the agent audit's verdict)
6. Absolute paths of the deliverables

Never add to the final message a claim or a number that is absent from report.md.
What reaches the conversation is a transcription of report.md, not new writing. Keep the message
short by being selective about which findings you transcribe, not by compressing the writing into
fragments, abbreviations, or arrow chains.

## Sources

The bibliography for the reference marks `[1]` through `[12]` in this document is cited in
[methodology_sources.md](methodology_sources.md) under the "Ref" column as `interpretation[1]`
through `interpretation[12]`.
