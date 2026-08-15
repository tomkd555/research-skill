# Research plan (research_brief): {topic}

<!-- research-team Step 1 deliverable. Check it with python {SKILL_DIR}/scripts/research_plan_linter.py research_brief.md --mode {MODE} -->

- Mode: {LIGHT | STANDARD | DEEP}
- as_of: {YYYY-MM-DD}
- Written: {YYYY-MM-DD}

## Purpose

<!-- What this research decides, in one to three sentences. Not "we want to know", but
     "this is the input to which judgement". -->

{who decides what, using the result of this research}

- Intended readers: {who reads it}
- Defaults recorded: {what the user left to you, and the default you took}

## Key questions

<!-- Two to seven, phrased as questions, each at a grain that can be researched and verified
     on its own. In DEEP, append the decision relevance [decision] or [background]:
     at most four [decision] questions drive the conclusion or the
     recommendation; [background] questions establish premises and take the STANDARD floors
     (collection_standards.md §1). -->

- KQ1: {…?} [decision]
- KQ2: {…?} [decision]
- KQ3: {…?} [background]

## Competing hypotheses

<!-- Two or more mutually opposed ones in DEEP. Register the user's own hypothesis
     as H1; it gets no privilege over the others. -->

- H1: {the user's initial hypothesis, or the leading explanation}
- H2: {an explanation that contradicts H1}

## Disconfirmation plan

<!-- For each hypothesis, list what would be observed if it were false — before searching
     (collection_standards.md §3). -->

| Hypothesis | Observable if false | Disconfirming query |
|---|---|---|
| H1 | {…} | {…} |
| H2 | {…} | {…} |

## Source plan

<!-- Name the kinds of primary source to prefer; they map onto the grades in
     collection_standards.md §4. -->

- Primary sources preferred: {government statistics / peer-reviewed papers / corporate IR / official documentation …}
- Publishers expected: {the statistics agencies, regulators, journals or industry bodies you expect to cite}
- Role assignment: {which collection role handles each KQ, as in KQ1=collector,
  KQ2=scholar/sonnet, KQ3=collector+scholar/opus. Name the model for each scholar
  (the escalation conditions are in agent_roles.md §2).}

## Stopping rules

- The collection floors are met (per mode and decision relevance; collection_standards.md §1) and two consecutive queries add nothing new
- Early stop: three or more independent sources, no new evidence unit in the last two queries, and the KQ's conclusion at "likely" or above — all three together stop the collection even short of the DEEP floors (record it in floor_status.early_stop)
- Ceiling: {a cap on total search queries, turns, or time}
- Cutbacks recorded: {what you did when the planning budget check went over — fewer KQs, a decision KQ moved to background. Write "not applicable" if none.}

## Out of scope

<!-- What you decided against researching, so that later readers do not read "not looked at"
     as "not there". -->

- {…}
