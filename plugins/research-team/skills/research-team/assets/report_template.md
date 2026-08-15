# {topic} — research report

<!-- research-team Step 4 deliverable. Check it with python {SKILL_DIR}/scripts/report_auditor.py report.md --evidence evidence_log.json --citation citation_check.json -->

<!-- Match the report's length to the substance the evidence carries. No filler sections, no
     boilerplate, no closing summary that repeats a section the reader has just read. Answer to
     the decision, Summary and KQ coverage restate the same conclusion on purpose, as a cross-check
     against what was missed — hold each to the length stated for it rather than expanding all
     three. -->

- as_of: {YYYY-MM-DD} / mode: {STANDARD | DEEP}
- Independent sources: {N} / evidence units: {N} / confirmed claims: {N}
- Verification breakdown: confirmed {N} / plausible {N} / disputed {N} / refuted {N} / unchecked {N}
- Overall confidence: {one of the seven labels} ({band})

## Answer to the decision

<!-- The answer to the decision goes first, so that a sweep of detail
     cannot dilute the subject. render_scaffold.py generates this section's skeleton and
     report_auditor.py checks it as a required section. -->

- Answer: {one sentence answering the decision named in the brief's Purpose}[E#]
- Recommendation: {one sentence on what to do}
- Confidence: {label} ({band})
- What would overturn this: {the fact or indicator that would change the conclusion}

## Summary

<!-- Conclusion first, three to five sentences. Mark every fact with [E#]. Estimates take
     a label from the confidence vocabulary. -->

{conclusion}[E1][E2]. {the grounds, summarised}[E3]. {the main counter-evidence or limit, in one clause}.

## Conclusions per key question

### KQ1: {…?}

<!-- render_scaffold.py generates the ceiling line and the evidence table from
     evidence_log.json. Do not rewrite them. The evidence column is bare (E1) rather than
     [E1] so that it does not count as a body citation. -->

- Confidence ceiling (computed): {label} ({band}) — {grounds}. The writer picks the final label.

| Evidence | Claim | Grade | Corroboration | Verification |
|---|---|---|---|---|
| E1 | {the claim in one line} | A | corroborated | confirmed |

**Conclusion**: {one or two sentences}[E#] (confidence: {label})

- {a supporting fact}[E#]
- {a supporting fact}[E#]
- Conflicting: {if any}[E#]

### KQ2: {…?}

(same shape)

## Disconfirmation and conflicting evidence

<!-- Its own section: everything that runs against the conclusion collects here.
     render_scaffold.py transcribes the ledger's disconfirmation into the table between the
     generated markers, and the audit does not judge that table. The writer's own reading
     must appear outside the markers. -->

<!-- generated:disconfirmation -->
| Hypothesis | Observable if false | Queries run | Result | Effect on the hypothesis |
|---|---|---|---|---|
| {…} | {…} | {…} | {…} | {…} |
<!-- /generated:disconfirmation -->

- {the disconfirming fact or the opposing view}[E#] — {what it does to the conclusion}
- Reading of the disconfirmation search: {how the table above moves the confidence}

## Insight and implications

<!-- Write an insight as evidence → warrant → conclusion. Leave out any insight you cannot
     trace back that way. -->

1. **{the insight}** (evidence: [E#][E#])
   - Warrant: {why that evidence supports this conclusion}
   - Confidence: {label} ({band})
   - Evidence that lowers it: {if any}

## Limitations and evidence gaps

| Claim left uncorroborated | Queries tried | Further research suggested |
|---|---|---|
| {…} | {…} | {…} |

<!-- render_scaffold.py generates the early-stop table from the ledger's floor_status.
     An early stop means "not looked at", not "not there", so state it as a limit. -->

<!-- generated:early_stop -->
| KQ | Role | Independent sources | Consecutive zero-new | Confidence | Note |
|---|---|---|---|---|---|
| {…} | {…} | {…} | {…} | {…} | {…} |
<!-- /generated:early_stop -->

- {other limits: the period covered, sources that could not be reached}

## KQ coverage

| KQ | Conclusion | Confidence | Key evidence | Verification |
|---|---|---|---|---|
| KQ1 | {one line} | {label} | E1, E3 | confirmed |
| KQ2 | {one line} | {label} | E5 | single_source |

## Search log

| Query | Tool | Adopted | Kind | KQ |
|---|---|---|---|---|
| {…} | WebSearch | 2 | normal | KQ1 |
| {…} | WebSearch | 0 | counter | KQ2 |

## Sources

<!-- Every evidence unit's source. Full absolute URL, with the grade and the publication date. -->

- [E1] {publisher}. {title}. {published}. grade {A}. {https://…}
- [E2] …
