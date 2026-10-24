# Procedure (STANDARD and DEEP)

`{SKILL}` is this skill's directory, `{RUN}` the run directory, `{AGENTS}` the plugin's agents
directory. Substitute absolute paths. Everything in `{RUN}` is written in English except verbatim
quotes and `report.{lang}.md`.

Your context is the run's scarcest resource: every turn re-reads it. Read script summaries,
digests and agent return lines; leave raw pages, `evidence.jsonl` and verdict files to the
scripts. Run each step's scripts in one Bash call.

While agents run, do the work that does not depend on them. When nothing is left, end the turn
with one line on what is running; their notifications resume the run. When the user follows the
run in this session, say in one line what each step does before it starts and what came back
when a wait ends. Pause for the user only at the intake question and the DEEP plan agreement.

| | STANDARD | DEEP |
|---|---|---|
| Sub-questions | 2-4 | 3-6 |
| Collectors | one per sub-question | one per sub-question, plus an `academic` one where the sub-question turns on studies |
| Tool budget per collector | 12 | 20 |
| Claims verified (`--cap`) | 10 | 25 |
| Report prose | about 3,000 words | about 6,000 words |

## 1. Scope

1. Get the as-of date with Bash. Create `{RUN}` = `research/{YYYYMMDD}-{slug}/` unless the
   request names a directory. Write nothing outside it.
2. Write `brief.md` from `{SKILL}/assets/brief_template.md`: the decision, the question type, the
   presuppositions to verify, the sub-questions, the competing hypotheses, the local materials.
   Derive the sub-questions from the decision: each is a condition the decision turns on, and no
   two are answered by the same evidence. Register the user's own view as one hypothesis and
   search for its support and its refutation alike.
3. In DEEP, when the session can ask, show the user the sub-questions and get agreement in one
   turn. A subagent records "plan agreement skipped" in the brief and continues.

## 2. Collect (wait 1)

Launch every collector in one message, `model: sonnet`. Each launch prompt, invariant text first:

```text
Collect evidence for one sub-question, following your agent definition.

- Topic: {TOPIC}
- As-of date: {AS_OF}
- Run directory: {RUN}
- Skill directory: {SKILL}
- Local materials: {MATERIALS or none}

<assignment>
- Sub-question {SQ}: {text}
- Source: {web | academic}
- Tool budget: {12 | 20}
- Evidence path: {RUN}/collect/{SQ}_{web|academic}.jsonl
- Searches path: {RUN}/collect/searches_{SQ}_{web|academic}.jsonl
</assignment>
```

Wait for every collector to return. A collector that returns no files is relaunched once; after
a second failure, record the sub-question as a gap.

## 3. Check and outline

1. `python {SKILL}/scripts/check.py --run-dir {RUN}`. Read its summary only.
2. Read `{RUN}/digests/SQ*.md`. Write `{RUN}/outline.md`: the report's headings in order and, under
   each, the evidence ids it will use. Organise by what the decision needs to know, and put
   opposing items under the heading they oppose.
3. DEEP only, when `gaps.json` lists a sub-question with no passing item: launch one collector
   for it with a budget of 12 and a narrower or reworded sub-question, draft the other sections
   while it runs, then run `check.py --run-dir {RUN} --only {SQ}` and add its heading's ids.

## 4. Write

Write `{RUN}/report.md` once, from the outline and the digests, following
`{SKILL}/assets/report_template.md`.

- The Answer comes first and answers the decision in the brief, with the evidence that carries it.
- Every sentence that states a fact carries the ids it rests on, `[E3]` or `[E3, E7]`, at its
  end. Every sentence with a number carries one.
- Write every date as `YYYY-MM-DD` or `YYYY-MM` and every count in Arabic digits ("3-month",
  "2 weeks"), so the translation in step 7 carries the same numbers.
- Cite only items in the digests. Cite a `warn` item only where no `pass` item says the same.
- An item whose publisher gains from the figure, with no independent cluster behind it, stays out
  of the Answer; the Findings present it with its interest stated.
- Where passing items disagree, present both values and why they differ (definition, period,
  population).
- State each estimate with its basis and one label from this scale:
  `almost certain` / `very likely` / `likely` / `roughly even chance` / `unlikely` /
  `very unlikely` / `almost no chance`.
- Disagreements and limits: the opposing evidence, the gaps from `gaps.json`, what would change
  the Answer.
- Write plain report prose for a reader who will act on it. Please remove all mannered prose.
- When a sentence repeats a source's wording, mark it as a quotation. Example: the digest quote
  is "token usage by itself explains 80% of the variance". Correct: Anthropic reports that
  "token usage by itself explains 80% of the variance" in its BrowseComp runs [E4]. This is
  correct because the source's words sit inside quotation marks and the id follows.

## 5. Verify (wait 2)

1. `python {SKILL}/scripts/select_claims.py --run-dir {RUN} --cap {10|25}`.
2. Launch one `research-verifier` per batch, all in one message, `model: opus`. Pass the paths
   only; never the report, the brief or any reasoning:

```text
Judge the claims in the batch below, following your agent definition.

- Run directory: {RUN}
- Skill directory: {SKILL}

<assignment>
- Batch: {RUN}/claims/batch_{k}.json
- Write verdicts to: {RUN}/claims/verdicts_{k}.json
</assignment>
```

3. `python {SKILL}/scripts/apply_verdicts.py --run-dir {RUN}`. Resolve any error it lists by
   relaunching that verifier once.

## 6. Patch and check

1. Edit each sentence in the patch list, one Edit per sentence, as its action says. Leave every
   other sentence as it is.
2. `python {SKILL}/scripts/report_check.py --run-dir {RUN}`. Fix each failure at its line and
   re-run until it passes.

## 7. Translate

When the request was written in a language other than English, translate `report.md` in one pass
into `{RUN}/report.{lang}.md` (`lang` an ISO 639-1 code such as `ja`):

- keep every heading, every marker `[E..]` in place, and every number in Arabic digits exactly as
  in English: no conversion to 万, 千 or kanji numerals; dates stay `YYYY-MM-DD`;
- keep verbatim quotes and proper names as they are;
- write the field's own terms, in the register of a business report in that language.

Then `python {SKILL}/scripts/report_check.py --run-dir {RUN} --translation {RUN}/report.{lang}.md`
and fix each mismatch.

## 8. Deliver

The final message, in the request's language: the Answer in 2-5 sentences with its ids; up to
five key findings with ids; the opposing evidence and the limits; the verification counts
(claims verified, supported, patched); the paths of `report.md`, the translation if any,
`sources.md` and `brief.md`. Put nothing in it that `report.md` does not say.

## Errors

| Situation | Action |
|---|---|
| The Agent tool is absent (a subagent depth limit) | a lead returns `{"error": "the Agent tool is unavailable"}`; the main session runs this procedure itself |
| WebSearch returns a budget-exceeded string | record it in the brief's limits; raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` next time |
| A script exits 2 | read its message, fix the input, re-run once |
| `report_check.py` still fails after two fixes | deliver with the failure stated under limits |
