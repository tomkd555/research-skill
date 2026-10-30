# Procedure (STANDARD and DEEP)

`{SKILL}` is this skill's directory and `{RUN}` the run directory. Substitute absolute paths.
Everything in `{RUN}` is written in English except verbatim quotes and `report.{lang}.md`.

Your context is the run's scarcest resource: every turn re-reads it. Read script summaries,
digests and agent return lines; leave raw pages, `evidence.jsonl` and verdict files to the
scripts. Run each step's scripts in one Bash call. Keep each Bash command under 7,000
characters; write longer text to a file with Write first.

While agents run, do the work that does not depend on them. The translation depends on the
patches, so it starts after step 6. When nothing is left, end the turn with one line on what
is running; their notifications resume the run. When the user follows the
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

Write the report once with the Write tool to `{RUN}/draft.md`, from the outline and the
digests, following `{SKILL}/assets/report_template.md`. Claude Code refuses a subagent's Write
to a file named `report*`, so the draft is renamed in the Bash call that first checks it, and
later changes to `report.md` go through Edit.

- The Answer comes first and answers the decision in the brief, with the evidence that carries it.
- Every sentence that states a fact carries the ids it rests on, `[E3]` or `[E3, E7]`, at its
  end.
- Write each cited sentence from the quote and its context in the digest; the item's claim
  line points to the passage and is never the source of the wording.
- Keep the source's scope words, hedges and conditions ("most", "often", "up to", "may",
  "in summarisation") and name the population, setting, model or period a result holds for.
- A sentence that generalises across items names each item's setting and cites every passing
  item that runs against the generalisation; figures from different studies, cells or
  conditions are never joined with "from ... to".
- The report's own reading, judgement or recommendation goes in a sentence of its own after
  the facts it rests on, worded as the report's reading, and carries no ids; the ids stay on
  the fact sentences.
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
- Run `mv {RUN}/draft.md {RUN}/report.md && python {SKILL}/scripts/report_check.py --run-dir {RUN}`
  and fix it to 0 failures before step 5, so the markers are final when claims are selected.

## 5. Screen and verify (waits 2 and 3)

1. `python {SKILL}/scripts/screen_claims.py --run-dir {RUN} --write`, then launch one
   `research-screener` per batch, all in one message, `model: sonnet`. Pass the paths only:

```text
Label the sentences in the batch below, following your agent definition.

<assignment>
- Batch: {RUN}/screen/batch_{k}.json
- Write labels to: {RUN}/screen/labels_{k}.json
</assignment>
```

2. `python {SKILL}/scripts/screen_claims.py --run-dir {RUN} --apply`. For each fix line it
   prints, one Edit: an `uncited_fact` cites the digest item that states it, or becomes the
   report's reading with no ids, or goes; an `own_cited` sentence splits into the fact with its
   ids and the reading without them. A new citation needs a digest item that states the fact;
   the verifiers check these sentences first. Then run `report_check.py` again to 0 failures,
   so every new id exists before claims are selected. A screener that fails its one relaunch:
   delete its `batch_{k}.json` and any `labels_{k}.json` before `--apply`; its sentences stay
   unscreened.
3. `python {SKILL}/scripts/select_claims.py --run-dir {RUN} --cap {10|25}`. The cap is the
   tier's; keep it as the table sets it.
4. Launch one `research-verifier` per batch, all in one message, `model: opus`. Pass the paths
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

5. `python {SKILL}/scripts/apply_verdicts.py --run-dir {RUN}`. Resolve any error it lists by
   relaunching that verifier once. When that verifier fails again, delete its `batch_{k}.json`,
   re-run the script, and list that batch's sentences under Disagreements and limits as
   unverified.

## 6. Patch and check

1. For each `contradicted` patch whose source is not yet in `evidence.jsonl`: run
   `fetch_page.py --run-dir {RUN} {source} --json`, then Write one evidence item for the found
   passage (the claim's sub-question, `stance: opposes`, the quote copied from the cached page)
   to `{RUN}/claims/opposing.jsonl`. Run `python {SKILL}/scripts/check.py --run-dir {RUN} --append
   {RUN}/claims/opposing.jsonl` once for all of them, fix any item it fails, and cite the ids it
   prints when the sentence states both values.
2. Edit each sentence in the patch list, one Edit per sentence, as its action says and as the
   reason and the found passage that `apply_verdicts.py` prints say. Leave every other sentence
   as it is.
3. `python {SKILL}/scripts/report_check.py --run-dir {RUN}`. Fix each failure at its line and
   re-run until it passes.

## 7. Translate

When the request was written in a language other than English, translate `report.md` in one pass
with the Write tool into `{RUN}/draft.{lang}.md` (`lang` an ISO 639-1 code such as `ja`):

- keep every heading, every marker `[E..]` in place, and every number in Arabic digits exactly as
  in English: no conversion to 万, 千 or kanji numerals; dates stay `YYYY-MM-DD`;
- keep names that contain digits (H1, Q3, FY2025, GPT-4) as written;
- keep verbatim quotes and proper names as they are;
- write the field's own terms, in the register of a business report in that language.

Then `mv {RUN}/draft.{lang}.md {RUN}/report.{lang}.md && python {SKILL}/scripts/report_check.py
--run-dir {RUN} --translation {RUN}/report.{lang}.md` and fix each mismatch.

## 8. Deliver

The final message, in the request's language: the Answer in 2-5 sentences with its ids; up to
five key findings with ids; the opposing evidence and the limits; the verification counts
(claims verified, supported, patched) and the screen counts `screen.json` holds, as "screened
N sentences: D drift, U uncited facts, O readings under a source marker"; the paths of `report.md`, the translation if any,
`sources.md` and `brief.md`. Put nothing in it that `report.md` does not say.

## Errors

| Situation | Action |
|---|---|
| The Agent tool is absent (a subagent depth limit) | a lead returns `{"error": "the Agent tool is unavailable"}`; the main session runs this procedure itself |
| WebSearch returns a budget-exceeded string | record it in the brief's Notes; raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` next time |
| A script exits 2 | read its message, fix the input, re-run once |
| `report_check.py` still fails after two fixes | deliver with the failure stated under limits |
| A lead stops early | relaunch it on the same `{RUN}`; it resumes at the first missing file of brief.md, the collect files, evidence.jsonl, outline.md, report.md, screen.json, verdicts.json, report.{lang}.md |
