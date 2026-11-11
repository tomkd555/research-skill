# research-team

A Claude Code plugin for research on any subject. Parallel collectors gather quoted evidence, a
script matches every quote against the cached source page, one writer drafts the report,
screeners compare every sentence with its quotes, and verifiers check the flagged and key
sentences against their sources. The plugin writes and checks each
report in English, then translates it into the language of the request.

Since 2.1 the run is built to do three more things:

- **Go past the usual account.** The lead scouts the field's own terms before planning;
  collectors spend at most a quarter of their budget on the obvious query and at least half
  digging past it; the paper search lists recent work and follows the citation graph instead
  of stopping at the most-cited papers.
- **Cover what surrounds the request.** The brief maps six lenses around the question
  (upstream, downstream, unnamed alternatives, neighbouring fields, other parties, recent
  change); a breadth collector covers them; collectors hand back leads and the best are
  followed up; the report has a "Beyond the question" section.
- **Read a study for what it shows.** Every study item records its design, its basis and
  the role of the quoted passage; the writer sees the abstract; screeners and verifiers flag a
  sentence that claims more than the design carries.

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
| `sources.md` | each source with its check result, the gaps, the leads, the search log |
| `brief.md`, `evidence.jsonl`, `screen.json`, `verdicts.json`, `pages/` | the plan, the evidence, the screen, the verdicts, the cached pages |

## Requirements

Python 3 with the standard library (tested on 3.11), WebSearch and WebFetch. PDF sources need
`pypdf`. Set `OPENALEX_MAILTO` to your address to join OpenAlex's faster queue.

## License

MIT
