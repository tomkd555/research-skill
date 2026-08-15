# The pipeline (Steps 0–6)

This is the procedure for STANDARD and DEEP. LIGHT does not come here: search directly and answer
in the conversation with sources attached. The mode table, the deliverable list, and the agent
table are in [SKILL.md](../SKILL.md).

`{SKILL_DIR}` is this skill's install location — `<plugin root>/skills/research-team` when the
research-team plugin is installed, `~/.claude/skills/research-team` when the skill is copied in by
hand. `{RUN_DIR}` is the output directory. Substitute absolute paths at run time.

`{AGENTS_DIR}` is where the agent definitions sit: `<plugin root>/agents/` under the plugin,
`~/.claude/agents/` under a manual install.

A deliverable's structure is English and only English: its section headings, its table headers
and its confidence labels. `scripts/labels.py` holds them and is the source of record; write
them exactly as that file has them. The prose under those headings — the claims, the
conclusions, the report body — is written in the language of the request.

## Step 0 Intake

If the request leaves its purpose, scope, or criteria unclear, combine the mode question
and the scope questions into a single AskUserQuestion and keep the exchange to one turn (four
questions at most): (1) mode, with the recommendation first, only if the mode is unclear; (2) what
this research will decide; (3) scope (region, period, subject); (4) the aspects that matter most.
If the user says to decide for them, proceed with sensible defaults and record those defaults in
research_brief. Waiting on a human is the longest wait in the pipeline, so never split the
questions across two turns. `research-team-lead` is a subagent and cannot ask: it fills every
omission with a default and states the assumption.

If the user states an initial hypothesis or a personal view, register it as one competing
hypothesis (H1). Do not privilege it: search for supporting and disconfirming evidence with equal
effort (sycophancy prevention; interpretation_contract.md §4).

**Settle the deliverable language here.** It is the language the user wrote the request in, unless
they asked for another. Call it `{OUT_LANG}` from here on: it goes into research_brief, into every
launch instruction, into `merge_fragments.py`'s `--deliverable-language`, and it reaches the ledger
as `deliverable_language`. It governs the prose alone; the headings, the table headers and the
confidence labels stay English whatever it is. Nor does it decide the language a query runs in: a
collection agent searches wherever the best sources for its key question sit, so a question about
French regulation is searched in French even when the report comes out in English. There is one
brief template and one report template, both in `{SKILL_DIR}/assets/` and both English —
`research_brief_template.md` and `report_template.md`. Write the prose in `{OUT_LANG}` under their
English headings.

## Step 1 Planning

Write research_brief.md following `assets/research_brief_template.md`, with its headings as they
stand and the prose in `{OUT_LANG}`. The required elements are:

- Purpose (what this research will decide) and intended readers
- Key questions (KQ1–KQn, two to seven, each ending in a question mark). In DEEP, append the
  decision relevance to the end of each line — `[decision]` or `[background]` (at most four
  decision KQs; collection_standards.md §1)
- Competing hypotheses (two or more mutually opposed ones in DEEP; optional in STANDARD)
- Disconfirmation plan (for each hypothesis, list what would be observed if it were false, before
  searching)
- Source plan (which primary sources to prefer, and the role and model assignment per KQ — for
  example `KQ1=collector, KQ2=scholar/sonnet, KQ3=collector+scholar/opus`). The model per scholar
  KQ follows the table in [agent_roles.md](agent_roles.md) §2
- Stopping rules (meeting the collection floors plus diminishing new information, the three
  conditions for a conclusion-sufficiency early stop, or a time or turn limit)
- Out-of-scope items and the as-of date

Check it with `python {SKILL_DIR}/scripts/research_plan_linter.py {RUN_DIR}/research_brief.md
--mode {MODE}` and clear every FAIL before continuing.

**The session-wide search budget (`P-BUDGET` / `P-COST`).** Claude Code caps WebSearch calls at 200
per session by default and, past that, returns a budget-exceeded string without searching. It is
not an error, so floors can go unmet without anyone noticing. The cap is cumulative for the session
and shared by the parent and every subagent; only resetting the conversation reinitialises it. The
linter estimates the total with this formula: for each KQ, sum its query floor — 12 in DEEP, 6 in
STANDARD and for a DEEP background KQ — over each assigned role, multiplying the scholar share by
0.4 (academic APIs do not consume the cap); then add the verification stage's disconfirmation
queries as "the batch cap × 3 claims × 2 queries" — 60 in DEEP and 36 in STANDARD. Adding a KQ adds
collection queries and leaves the verification stage where it was. If `P-BUDGET` or `P-COST` fails,
cut the plan back (fewer KQs, a role dropped from a KQ, or a decision KQ moved to background) or
raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`, and record which you did in the stopping rules.

In DEEP, show the plan to the user and get agreement within one turn. Skip that agreement, record
the plan as it stands, and continue if any of the following holds: (a) you were told to run
autonomously; (b) the environment is non-interactive; (c) you are `research-team-lead` (a subagent
cannot ask the user). If you skip it, record "plan agreement skipped (reason)" in English in
research_brief and include the plan's essentials (KQs, competing hypotheses, out-of-scope) in the
final message at Step 6.

## Step 2 Parallel collection

Launch the collection agents for every KQ in parallel, in a single message. Assign
research-collector to KQs whose main sources are primary web information (statistics, IR filings,
reporting, case studies, specifications) and research-scholar to KQs whose main sources are
academic literature (effectiveness studies, method comparisons, theory, medicine, statistical
findings). Launch both on the same KQ when it needs both, and merge at intake. research-scholar
owns the academic side throughout; never subcontract the role to another agent.

The procedure, prohibitions, and output convention live in the agent definitions
(`{AGENTS_DIR}/research-collector.md`, `research-scholar.md`). Do not restate them in the
launch instruction and do not write a separate shared brief — pass only the per-launch variables
listed in [agent_roles.md](agent_roles.md) §1. Where custom agent types are unavailable, hand the
agent definition file itself to a general-purpose agent as its instructions.

Every scholar launch must carry `{PAPER_TOOL}`, the absolute path of the literature-review skill's
`scripts/paper_search.py`. That skill ships beside this one, so the path is
`{SKILL_DIR}/../literature-review/scripts/paper_search.py`. A scholar launched
without that path falls back to WebFetch and burns its context on raw API JSON. Set each scholar's
model with the Agent tool's `model` parameter, per the table in
[agent_roles.md](agent_roles.md) §2 — sonnet by default, opus for a key question that turns on
statistics, contested findings, costly errors, or full-text reading.

Before returning, each collection agent runs `validate_fragment.py` on its own fragment and fills
the gaps until it passes. The agent resolves any shortfall computable from the fragment alone (the
query count, the disconfirmation query count) at this point.

Each collection agent writes the full evidence-fragment JSON to
`evidence_fragments/kq{N}_{role}.json` and returns only the file path and a compressed summary
(300–500 tokens). The caller never transcribes fragments out of a response body. Merge
deterministically with `python {SKILL_DIR}/scripts/merge_fragments.py --run-dir {RUN_DIR} --brief
{RUN_DIR}/research_brief.md --mode {MODE} --as-of {AS_OF} --topic "{TOPIC}"
--deliverable-language {OUT_LANG} --json`; that script assigns IDs, attaches `kq_id` and `role` to
`search_log` rows, merges `disconfirmation` and `gaps`, and records the deliverable language. If
`unmerged_report.json` records fragments or evidence that could not be taken in, follow the retry
rules in [interpretation_contract.md](interpretation_contract.md) §6.

The only work left to the caller's judgement is **merging independence clusters (`origin_cluster`)
across fragments**. Starting from the provisional clusters the collection agents assigned within
their own fragment, give the same ID to provisional clusters in different fragments that share a
publisher or a reprint relationship. Merge only; never split what a collection agent judged to be
the same source. Fill in any evidence that `merge_fragments.py` reports as unset.

Immediately after merging, run `python {SKILL_DIR}/scripts/evidence_auditor.py
{RUN_DIR}/evidence_log.json --mode {MODE} --json` and clear every FAIL before Step 3. If a floor
shortfall (`E-FLOOR-*`) comes back as FAIL, launch additional collection for that KQ alone at this
point; do not carry it to Step 5. A shortfall downgraded to WARN by an early-stop record does not
trigger more collection — transcribe the `E-EARLYSTOP` content into the report's limitations
section at Step 4.

Collection agents fetch pages through `triage_sources.py` and `fetch_page.py`, so
`{RUN_DIR}/pages/` fills up with the cached page text. Leave it in place: Step 4 and any
resubmission read quotes out of it without a second request. Pass `{RUN_DIR}` in every collection
launch (agent_roles.md §1) or the agents have nowhere to put the cache.

**The draft probe (DEEP only).** Before Step 3, run `python {SKILL_DIR}/scripts/render_scaffold.py
{RUN_DIR}/evidence_log.json --out {RUN_DIR}/draft_probe.md --slices {RUN_DIR}/kq_slices/`, read
the slices, and write a provisional answer of about five lines per KQ into `draft_probe.md`. Then
list which of the claims those provisional answers lean on rest on one source, on no source, or on a
figure nobody corroborated, and send one round of additional collection for that list alone. A
draft names which claims carry the conclusion, and the plan cannot
(source: TTD-DR, `https://arxiv.org/abs/2507.16075`, which drives retrieval from a draft rather
than from a plan). `draft_probe.md` is working material: it is never delivered, and Step 4 writes
the report from the ledger, not from it. This round is the same single allowance Step 3 holds —
spending it here costs one turn, while spending it after synthesis costs a report rewrite.

## Step 3 Independent verification

Once Step 2's merge and the structural fixes from `evidence_auditor.py` are done, copy the ledger
(`cp {RUN_DIR}/evidence_log.json {RUN_DIR}/citation_input.json`) and start
`python {SKILL_DIR}/scripts/citation_verifier.py {RUN_DIR}/citation_input.json --output
{RUN_DIR}/citation_check.json --json` in the background with Bash's `run_in_background` (run it
synchronously where background execution is unavailable).

Verification runs against the copy so the script does not race the caller's writes to the ledger.
Do not narrow the full run (no `--only`). If evidence is added later — by a gap resubmission, for
instance — run `--only` on the additions and merge the result into `citation_check.json`;
`R-CITECOMP` at Step 5 checks that the results are complete.

Verification runs in two waves. Only the second wave, which picks targets from citation-check
severities, waits for the full run; the first wave, decidable from the ledger alone, starts without
waiting.

1. For wave 1, run `python {SKILL_DIR}/scripts/select_verification_targets.py
   {RUN_DIR}/evidence_log.json --run-dir {RUN_DIR} --json`. The script picks up the signals
   decidable from the ledger alone (every key figure, single-source claims, claims that conflict
   across sources, key figures resting only on grade-C sources, self-reported key figures, and
   claims whose `claim_type` is estimate) and writes batches of three together with a per-batch
   claim payload (`verification/targets_{BATCH_ID}.json`). Single-source and estimate claims are
   targeted only when they belong to a decision KQ. The batch count is capped **for the whole
   study, not per wave**: 10 batches in DEEP, 6 in STANDARD, 2 in LIGHT — wave 2 gets what wave 1
   left, which the script works out from the batch files already written. The excess is cut in an
   order that keeps key figures and conflicts, and appears under `dropped` in the output — record
   the count and the reason in the ledger's `gaps`. The caller adds to the targets
   whatever meets the one criterion no script can decide: "claims that drive the conclusion or the
   recommendation" (the script never removes targets; only the caller adds). Then run
   `citation_verifier.py {RUN_DIR}/citation_input.json --only {wave-1 IDs} --output
   {RUN_DIR}/citation_check_targets.json` synchronously and re-run
   `select_verification_targets.py` with `--citation {RUN_DIR}/citation_check_targets.json`. The
   selection does not change; the payloads gain the match results. Launch the wave-1 verifier
   agents here.
2. For wave 2, after the full run finishes, execute `select_verification_targets.py …
   --wave 2 --citation {RUN_DIR}/citation_check.json`. The targets are the evidence whose
   citation-check severity is CRITICAL or WARN and that wave 1 did not already cover. Launch per
   batch in the same way.
3. Pass the union of wave 1, wave 2, and the caller's additions to `apply_verdicts.py --expected`.
   Pass the full `citation_check.json` to `report_auditor.py --citation` at Step 5.

Launch the verifier agents (research-verifier) in parallel, one per batch, following the script's
recommended `model`. A verifier runs in a **separate context** from the collection agents and
inherits none of their judgements (this prevents self-preference and carried-over confirmation).
Pass only the payload path and the verdicts output path; never copy the claim text into the
instruction. The verification procedure and the verdict JSON are in the agent definition
(`{AGENTS_DIR}/research-verifier.md`).

Each verifier writes its full verdicts to `{RUN_DIR}/verification/verdicts_{BATCH_ID}.json` and
returns only the path and a one-line summary. Apply them to the ledger deterministically with
`python {SKILL_DIR}/scripts/apply_verdicts.py {RUN_DIR}/evidence_log.json --verdicts-dir
{RUN_DIR}/verification --expected {target IDs} --json`; the caller never transcribes a verdict out
of a message body. If the output's `errors` (IDs absent from the ledger, invalid statuses) or
`missing` (targets with no verdict returned) are non-empty, resolve them before continuing. If
`changes` records a rewrite of the ledger's corroboration, read what changed. Drop refuted evidence
from the basis of the conclusion and route disputed evidence to both-sides presentation; the caller
makes that call.

After verification, check for knowledge gaps. Only when an important gap remains unresolved and the
mode is DEEP may you send one — and only one — round of additional collection back to Step 2, and
only if the draft probe did not already spend it. In STANDARD and below, state the gap explicitly
and continue without a resubmission. Collecting again for a claim the verifiers refuted is a
repair of that claim, not the additional round.

## Step 4 Synthesis

First run `python {SKILL_DIR}/scripts/render_scaffold.py {RUN_DIR}/evidence_log.json --out
{RUN_DIR}/report.md --slices {RUN_DIR}/kq_slices/` and take the generated scaffold as the initial
state of report.md. The header metrics and verification breakdown, the per-KQ evidence tables and
confidence ceilings, the disconfirmation table, the evidence and verification-status columns of the
KQ coverage table, the search-log table, the source list, and the gaps table are all deterministic
renderings of the ledger; do not rewrite them by hand (the rendering is more accurate, and it keeps
R10's full absolute URLs and R11's publication dates satisfied). The disconfirmation table sits
between a `<!-- generated:disconfirmation -->` pair and is excluded from the R4 judgement, so always
write your own interpretation outside those markers.

The script refuses to overwrite an existing `--out`. On a resubmission, render to
`{RUN_DIR}/report_scaffold.md` instead and replace only the generated ranges inside report.md;
`--force` exists but discards the prose already written.

Then the caller (the orchestrator) writes the analysis sections — the answer to the decision, the
summary, the per-KQ conclusions, disconfirmation and conflicting evidence, insight and
implications, and limitations and evidence gaps — in a single context, following
`assets/report_template.md`, whose headings stand as they are while the prose goes in
`{OUT_LANG}`. Writing sections in parallel lowers quality; never do it.
Draft in two passes: first a recall-first draft that reflects every KQ and every
important piece of evidence. Immediately after saving that draft, run the Step 5 item 1 checks
(both scripts in one Bash call), bring FAIL to zero, and only then move to the precision pass that
cuts redundancy. Run both scripts again after that pass. **Full-text revision stops after these two
passes; from the third pass on, fix only the locations that still FAIL** — a third full pass
rewrites prose the checks already cleared, reloads the whole report into context, and tends to
reintroduce phrasing the ledger no longer backs. Fix a failing
location as often as it takes; the limit applies to full-text revision alone.

The rules that govern synthesis are in interpretation_contract.md §3 (split synthesis, restating
key facts, drawing from `kq_slices/` rather than memory) and §5 (evidence IDs on every factual
sentence, the seven-level confidence vocabulary plus a probability band, absolute dates, units and
denominators, disconfirmation in its own section). Two points specific to this step:

- Use the `kq_slices/KQ{n}.md` files that `render_scaffold.py` generates as the reading unit; each
  is an extract of the ledger for that KQ. For sections that cut across KQs, also read
  `kq_slices/cross_cutting.md`. Do not re-read `evidence_log.json` on top of the slices
- The precision pass revises only the prose of the analysis sections. Never revise the
  deterministically generated tables and lists; cutting them violates R10 and R11

## Step 5 Evaluation and the pass gate

1. Deterministic checks: run `python {SKILL_DIR}/scripts/evidence_auditor.py
   {RUN_DIR}/evidence_log.json --mode {MODE} --json && python
   {SKILL_DIR}/scripts/report_auditor.py {RUN_DIR}/report.md --evidence
   {RUN_DIR}/evidence_log.json --citation {RUN_DIR}/citation_check.json --json`, and save both
   outputs together with the CRITICAL and WARN records from `citation_check.json` into
   `{RUN_DIR}/audit_machine.json`. **If even one FAIL remains at this point, do not launch the
   auditor agent — go back to Step 4 and clear it.** These checks are deterministic, so fixing what
   they report is not self-evaluation
2. Run `python {SKILL_DIR}/scripts/build_audit_input.py {RUN_DIR}/evidence_log.json --report
   {RUN_DIR}/report.md --run-dir {RUN_DIR} --mode {MODE} --json` to generate the ledger digest
   (`audit_digest.json`) and the sampling targets (`audit_sample.json`). Launch the auditor agent
   (research-auditor) in a context that took no part in writing the report, and pass it the report,
   these two files, audit_machine.json, and the path of
   `{SKILL_DIR}/references/evaluation_protocol.md`. Do not pass the full ledger — the rubric needs
   only what those two files contain, and no item requires the search log. When the audit finishes,
   the caller merges the deterministic output and the auditor's verdict into
   `{RUN_DIR}/audit_result.json`
3. Verdict: zero CRITICAL findings means the report passes. On a failure, resubmit **per KQ** for
   the findings raised; never rebuild the whole report. Which stage to return to follows the
   minimum re-run scope table in [evaluation_protocol.md](evaluation_protocol.md) §6. At most two
   resubmissions; beyond that, deliver the best version with the unresolved findings and
   limitations stated in it

## Step 6 Delivery

The final message follows the final-message contract in
[interpretation_contract.md](interpretation_contract.md) §7: summary → key findings with `[E#]` on
each line → disconfirming evidence and limitations → audit verdict → deliverable paths, in that
order. Never put into the final message a claim or a number that is absent from report.md.
Transcribe the full report only if the user asks for it.

## When LIGHT becomes STANDARD

A LIGHT study that escalates enters at Step 1 and builds the deliverables from there; the evidence
ledger is created at that point, not before. LIGHT itself writes no files.

## Error handling

[agent_roles.md](agent_roles.md) §5 governs search failures, conflicts between sources, failed
citation-existence checks, paywalls, exceeding the resubmission limit, and relaunching a subagent
that failed to produce a structured response. Retries for fragment JSON that fails the schema
or a deterministic check follow [interpretation_contract.md](interpretation_contract.md) §6.
