# research-team

A Claude Code plugin for research on any subject. Parallel collectors gather quoted evidence, a
script matches every quote against the cached source page, one writer drafts the report, and
verifiers check its key sentences against their sources. The plugin writes and checks each
report in English, then translates it into the language of the request.

## Install

```
/plugin marketplace add tomkd555/research-skill
/plugin install research-team@research-skill
```

Ask for research in any language. The skill picks a tier: QUICK answers one fact in the
conversation; STANDARD and DEEP run the full process and write to `research/{YYYYMMDD}-{slug}/`:

| File | Content |
|---|---|
| `report.md`, `report.{lang}.md` | the report and its translation; every factual sentence cites `[E#]` |
| `sources.md` | each source with its check result, the gaps, the search log |
| `brief.md`, `evidence.jsonl`, `verdicts.json`, `pages/` | the plan, the evidence, the verdicts, the cached pages |

## Requirements

Python 3 with the standard library only (tested on 3.11), WebSearch and WebFetch. Tests:
`for t in tests/test_*.py; do python "$t"; done`.

## License

MIT
