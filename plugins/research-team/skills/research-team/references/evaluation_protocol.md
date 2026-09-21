# Evaluation protocol (the source of record for evaluating research results correctly)

This applies to research-team's evaluation stage (Step 5). It defines the design principles for
the auditor agent (research-auditor) and for the corroboration done at the verification stage
(Step 3). The auditor's own definition (`agents/research-auditor.md`) carries the rubric and the
sampling procedure operatively, so no agent reads this file at run time; the lead reads §6 when it
applies the audit's findings.

The report under audit carries English structure — section headings, table headers and
confidence labels, all held in `scripts/labels.py`, which is the source of record for them. Its
prose is written in the language of the request, which the ledger records as
`deliverable_language`. Audit the prose in that language and the structure against `labels.py`.

## 1. Design principles for evaluation

1. **No personas**: making the model play a role ("you are a harsh expert") is reported not to
   improve accuracy on objective tasks (source [1]). Get multiple perspectives by
   decomposing into concrete check items per aspect and running them in parallel
2. **Reject false positives through corroboration**: for each finding or claim, pose a
   verification question, answer it independently on a path separate from the original
   generation, and discard findings that are refuted (Chain-of-Verification; source [2]). Withholding the original answer while answering the verification question makes the check accurate
3. **Separate the writing context from the evaluation context**: never have the report
   evaluated in the context that wrote it. LLM evaluators recognise their own output and score
   it higher (self-preference; source [3]). The auditor agent is launched in a new
   context and receives only the deliverable files
4. **No impressionistic scoring**: the evaluator's mood and the verbosity of the output pull a "rate this out of 10" score around. Decompose evaluation into binary check
   items (met / not met) and require the location for each (the design philosophy of rubric
   decomposition; sources [4][5])

## 2. Known biases in LLM evaluators, and the countermeasures

| Bias | What it is | Countermeasure |
|---|---|---|
| Position bias (source [4]) | In comparative evaluation, favouring the candidate presented first | Where a comparison is needed, evaluate twice with the order swapped and accept the result only if both agree. On disagreement, treat it as a draw and state the difference |
| Verbosity bias (source [4]) | Scoring longer, more detailed output higher regardless of content | Do not include length as an evaluation item. Make the check items existence judgements, such as "does it carry an evidence ID" |
| Self-preference (source [3]) | Scoring one's own output higher | Separate the writing and evaluation contexts (§1-3). Where possible, assign evaluation to an agent on a different model or configuration |
| Leniency and central tendency | Rounding every item to "broadly fine" | Force binary judgements. Require a location (line, ID) for every "met" judgement. A "met" with no location is treated as "not met" |

## 3. The audit rubric (binary check items)

The auditor agent judges each item below one at a time and returns the judgement, the location,
and the reason as a table. A failed mandatory item is CRITICAL; a failed recommended item is
WARN. Items decidable by machine are checked first by `scripts/report_auditor.py`,
`scripts/evidence_auditor.py`, and `scripts/citation_verifier.py`, and the auditor agent
concentrates on the semantic items no script can decide. `citation_verifier.py` mechanises
citation existence (URL reachability, DOI/arXiv ID resolution) and verbatim-quote matching, and
writes the results to `citation_check.json`.

### Mandatory items (the CRITICAL gate)

| # | Item | How it is judged |
|---|---|---|
| R1 | Every key question has a conclusion, or is marked unresolved with a reason | Cross-check the KQ coverage table against the body |
| R2 | Sentences stating a fact carry an evidence ID [E#] | Script detection plus a visual sample |
| R3 | Figures that drive a conclusion carry one of corroborated / single_source / conflicting, and conflicting figures are presented with both sides | For every `is_key_figure` in the ledger, confirm that a corroborated flag has two or more independent clusters (`origin_cluster`) — the two-independent-cluster principle for key figures. For single_source, confirm the reason (a record of the search for other sources) is in `note` |
| R4 | A disconfirmation and conflicting-information section exists and is non-empty, or the reason it is empty (the record of the disconfirmation search) is shown | Cross-check against the ledger's `disconfirmation`. The range between `<!-- generated:disconfirmation -->` and `<!-- /generated:disconfirmation -->` is a table `render_scaffold.py` generated from the ledger and is excluded from the judgement. Judge on what the writer wrote |
| R5 | Estimates and forecasts use the seven-level confidence vocabulary plus a probability band | Script detection plus visual check |
| R6 | The study's limitations and evidence gaps are stated | Section existence plus a cross-check against the ledger's `gaps` |
| R7 | Errors (unsupported plus contradicted) in atomic-fact sampling (§4) are under 30% of the sample | The §4 procedure |
| R13 | The deterministic citation check has zero CRITICAL findings (sources [8][9]) | Check every evidence ID in `citation_check.json`. If any item is left with an unresolved DOI/arXiv ID (`doi_status` / `arxiv_status` of not_found) or a `quote_match` of not_found, and the auditor agent has not judged it, the item fails |
| R14 | Claims resting on thin evidence (single_source, or plausible and below) are never written as flat assertions | Cross-check the body against `corroboration` and `verification`. A claim based on single_source, or on a verification of plausible or below, that is written as a flat assertion (a bare "X is Y", with no hedge) without a seven-level confidence label fails. A violation is grounds for resubmission |
| R16 | Where the rival analyst's answer differs from the report's, both readings appear in the body with the observation that would settle them, and the overall confidence is capped at "likely" or below | Compare `rival.json` against the `### Rival reading` block and the header's overall confidence. The item passes by default when no `rival.json` exists (a descriptive study runs no rival). `scripts/report_auditor.py --rival` checks the shape (`R-RIVAL`, `R-RIVAL-CAP`); the auditor judges the substance |

### Recommended items (WARN)

| # | Item |
|---|---|
| R8 | Insights and recommendations have the structure "supporting E-group → warrant → conclusion", and every insight is traceable back to an evidence ID |
| R9 | Conflicts between sources are marked conflicting, with an account of why they diverge |
| R10 | The search log and the source list (full absolute URLs) are included in the report |
| R11 | The as-of date and each source's publication date are stated, and the freshness rules (3 years / 12 months) are met or a reason is attached |
| R12 | The user's initial hypothesis is not privileged (there is a record of a disconfirmation search on H1) |
| R15 | The report's limitations section notes the scope within which the verification methods apply (for example: self-verification is unstable without external checking; sampling-based confidence methods work only on extrinsic confabulation and cannot detect intrinsic confabulation or systematic error; source [10]) |

Handling the three-valued attribution judgement (research-verifier's `attribution_check`, whose
definition is in that agent's own file): Accept supports as is. Treat misattributed as refuted and remove it from the report. partial — where the source only partly supports the claim — is either
presented with both sides in the body or reduced to a limiting expression such as "so far as the
source goes" or "within the range the source covers"; writing it as a flat assertion in the way
supports allows is prohibited (this interacts with R14).

## 4. Atomic-fact sampling check

The factual accuracy of a long report is measured per atomic fact — a single claim that cannot
be divided further — not by an overall impression (sources [5][6]).

1. Extract factual claims from the report body: 10 in DEEP, 5 in STANDARD (the extraction need
   not be strictly random; even sampling in evidence-ID order is fine)
2. Decompose each claim into atomic facts (split a sentence that carries more than one claim)
3. Check each atomic fact against the verbatim quote and source URL of the evidence unit it
   links to. The judgement is three-valued: supported / unsupported (not written in the source)
   / contradicted (at odds with the source)
4. If unsupported plus contradicted reaches 30% of the sample (3 or more of 10 in DEEP, 2 or
   more of 5 in STANDARD), R7 fails and that KQ is resubmitted
5. When checking, re-read the source independently. Do not read the report's wording first and
   then judge that it "looks right" (independence of corroboration; source [2])

## 5. Confidence calibration

- Assign the seven-level confidence vocabulary from the quantity, quality, and agreement of the
  evidence: agreement between two or more independent grade-A sources allows considering the
  "almost certain" band; a single grade-B source caps the claim at "likely"; a conflict puts it
  at "roughly even chance" or below, with both sides presented
- In a report containing forecasts, write them so they can be scored later (a verifiable
  indicator and a date). Forecast quality improves only through tracking outcomes (source [7])
- State disconfirming evidence alongside the main conclusions. Never assign high confidence to a
  conclusion whose disconfirmation has not been searched for. `scripts/render_scaffold.py`
  applies this to the per-KQ ceiling it computes: a key question with no evidence unit at
  `verification: confirmed` is capped at "likely" however strong its sources look, because
  the grade of a source says nothing about whether the quote, the attribution, and the
  disconfirmation search have been verified

## 6. The pass gate and resubmission

| Severity | Definition | Handling |
|---|---|---|
| CRITICAL | A failed mandatory item (R1–R7, R13, R14, R16), or reliance on refuted evidence | Cannot pass. Resubmit that KQ |
| WARN | A failed recommended item, an important claim resting on a single source, a freshness violation | Recorded, may pass. Transcribed into the report's limitations section |
| INFO | Unused evidence, room for improvement in style or structure | Recorded only |

- Pass condition: zero CRITICAL findings
- Resubmit **per KQ** for the findings raised, and keep the deliverables of unaffected KQs
  intact (rebuilding everything risks degradation and reintroduced errors)
- The lead applies the audit's findings once, re-runs the deterministic checks, and delivers; it
  re-launches the auditor only for a CRITICAL on R7 or on the substantive part of R3 or R4, and at
  most once. Beyond that, deliver the best version with the unresolved findings and limitations
  stated in it. Agreement between findings from more than one aspect informs a note
  on confidence; it never automatically escalates severity

### Minimum re-run scope for a resubmission

The stage at which the defect arose decides how far to re-run. Re-collecting in response
to a defect in the writing adds not one new piece of information, so it does nothing for the
completeness of the audit.

| Finding | Minimum re-run scope |
|---|---|
| R1, R2, R5, R6, R8–R12, R14, R15, R16, and the part of R4 that is a writing omission | **Step 4 only**. The ledger is unchanged (for R16 the rival's JSON is already on disk) |
| R13, a missing verdict, and the part of R3 where verification is incomplete | **Step 3** (re-verify only the affected evidence) → Step 4 |
| The part of R3 that is insufficient corroboration, the part of R4 that is an insufficient disconfirmation search, R7, and a FAIL on `E-FLOOR-*` | **Step 2** (additional collection for that KQ only) → Step 3 → Step 4 |

Resubmission to Step 2 is limited to cases where the evidence in question is cited as the basis
of a conclusion or a recommendation in the report. Insufficient corroboration for evidence that
no conclusion cites is passed through by stating it in the limitations section, without
additional collection — re-collecting where it does not move the conclusion only adds cost
without changing the verdict. An `E-FLOOR-*` finding downgraded to WARN by an early-stop record
(collection_standards.md §1) is not a resubmission target; transcribe what was cut short into
the limitations section.

In a Step 4 re-run, keep the KQ sections with no findings intact. Apply the two-pass drafting
(recall → precision) only to what was rewritten; do not revise a section that has already been
through both passes. Re-render the generated regions with `render_scaffold.py --merge`, so the
summary, the KQ coverage table and the source list stay consistent with the rewritten sections.

## Sources

The bibliography for the reference marks `[1]` through `[10]` in this document is cited in
[methodology_sources.md](methodology_sources.md) under the "Ref" column as `evaluation[1]`
through `evaluation[10]`.
