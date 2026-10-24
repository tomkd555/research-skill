# Evaluation

How research-team 2.0 is compared with 1.x. Repository only; the plugin install copies nothing
from here.

## Topics

Four studies already run with 1.x, each run again in 2.0 with the same request at the tier 1.x
used. The request texts are in `requests.md`. The baseline is the stored
1.x run; 1.x is not rerun.

| Run directory under `C:\Mycode\ClaudeCode\` | Tier | Request language |
|---|---|---|
| `research\20260825-solo-se-project-scale` | STANDARD | ja |
| `research\20260928-llm-japanese-business-register` | STANDARD | en |
| `講義資料スキル\research\teaching-delivery` | DEEP | en |
| `講義資料スキル\research\teaching-design` | DEEP | en |

## Measures

1. **Tokens and time**: `python eval/measure_run.py <session>.jsonl` sums input and output tokens
   per role over the research-team agents of one session and gives the slowest agent of each
   role. When the main session itself orchestrates (a Fable session), add the main session's own
   usage.
2. **Claim support**: 30 cited sentences sampled at random from each report (all of them when a
   report has fewer; 2.0 uses the English `report.md`). One fresh Opus agent per report judges each
   sentence against its cited source only, with the research-verifier's four verdicts. The rate
   is supported / judged.
3. **Blind preference**: an Opus judge reads the 1.x report and the delivered 2.0 report
   (`report.{lang}.md`, or `report.md` for an English request) with labels removed and the brief's
   decision, and names the one that serves the decision better. Each pair is judged twice with
   the order swapped (Zheng et al. 2023, arXiv:2306.05685). A topic counts for 2.0 only when both
   orders prefer it; split orders are a tie.

## Acceptance

- Input tokens at or below 20M (STANDARD) and 35M (DEEP) per run.
- Lead wall time at or below 20 min (STANDARD) and 35 min (DEEP).
- Claim support at or above the 1.x rate minus 1 sentence in 30.
- 2.0 wins or ties on at least 3 of the 4 topics.

## Known limits

- The stored 1.x runs used the models of their day (Sonnet 5 in `20260928-...`); part of a
  difference may come from the models.
- Claim support is judged on English sentences for 2.0 and on Japanese sentences for the 1.x
  report of `20260825-solo-se-project-scale`.
- Only `20260825-solo-se-project-scale` was a Japanese request, so 1 of the 4 topics exercises
  the translation step.
- The local materials of `20260928-...` (CLAUDE.md and the html-doc skill) have changed since the
  1.x run, so its 2.0 run reads newer versions of them.

## Results

{filled after the runs}
