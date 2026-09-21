# Methodology sources (the source of record)

Full bibliographic entries for the sources behind research-team's three rule sets (collection,
interpretation, evaluation). The numbered references inside each reference file resolve here.
The "Ref" column shows which document and which number each entry corresponds to: `collection[1]`
is `[1]` in `collection_standards.md`, `interpretation[1]` is `[1]` in `interpretation_contract.md`, and
`evaluation[1]` is `[1]` in `evaluation_protocol.md`. Sources that no document references by number
are marked `—`. Sources fall into three tiers: **peer-reviewed** (papers and journals;
usable as conclusive grounds), **conference/preprint** (arXiv and the like; strong evidence but
not conclusive grounds), and **official / book / practitioner** (treated as bibliography; corroborate
their claims against two or more sources).

Verification state: rows whose "Verified" column reads 2026-07 were checked with WebSearch /
WebFetch when this skill was written (3 July 2026), confirming that the DOI, arXiv ID, journal,
and URL exist and match. Rows reading 2026-06 inherit sources already verified in
consulting-team-v2/references/methodology_evidence.md.

## 1. Grounds for the collection standards

| Ref | Source | Tier | How this skill applies it | Verified |
|---|---|---|---|---|
| collection[1] | Nickerson, R. S. (1998). Confirmation Bias: A Ubiquitous Phenomenon in Many Guises. Review of General Psychology, 2(2), 175-220. DOI: 10.1037/1089-2680.2.2.175 | peer-reviewed | The main grounds for making disconfirmation search a duty. Confirmation bias is the largest systematic error in collection | 2026-07 |
| collection[2] | Wason, P. C. (1960). On the failure to eliminate hypotheses in a conceptual task. Quarterly Journal of Experimental Psychology, 12(3), 129-140. DOI: 10.1080/17470216008416717 | peer-reviewed | The classic grounds for inverting the search instruction (think-in-opposites) | 2026-06 |
| collection[3] | Lord, C. G., Lepper, M. R., & Preston, E. (1984). Considering the opposite: A corrective strategy for social judgment. Journal of Personality and Social Psychology, 47(6), 1231-1243. DOI: 10.1037/0022-3514.47.6.1231 | peer-reviewed | The rule that disconfirmation targets the strongest form of the opposing view | 2026-07 |
| collection[4] | Page, M. J., et al. (2021). The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. BMJ, 372, n71. DOI: 10.1136/bmj.n71 | peer-reviewed | Search transparency on the academic branch (the reporting style for queries and exclusion reasons) | 2026-07 |
| collection[5] | Guyatt, G. H., et al. (2008). GRADE: an emerging consensus on rating quality of evidence and strength of recommendations. BMJ, 336(7650), 924-926. DOI: 10.1136/bmj.39489.470347.AD | peer-reviewed | The design philosophy of the evidence hierarchy within academic sources | 2026-07 |
| collection[6] | Wohlin, C. (2014). Guidelines for snowballing in systematic literature studies and a replication in software engineering. EASE '14, Article 38. DOI: 10.1145/2601248.2601268 | peer-reviewed (conference) | The procedural grounds for snowball sampling (following references and citations) | 2026-07 |
| collection[7] | Wineburg, S., & McGrew, S. (2019). Lateral Reading and the Nature of Expertise: Reading Less and Learning More When Evaluating Digital Information. Teachers College Record, 121(11), 1-40. DOI: 10.1177/016146811912101102 | peer-reviewed | Judging source reliability across sites (lateral reading) | 2026-07 |
| collection[9] | Guest, G., Bunce, A., & Johnson, L. (2006). How Many Interviews Are Enough? Field Methods, 18(1), 59-82. DOI: 10.1177/1525822X05279903 | peer-reviewed | The saturation stopping rule (stop as new information diminishes) | 2026-06 |
| collection[8]  / interpretation[10] | ODNI (2015). Intelligence Community Directive 203: Analytic Standards. https://www.dni.gov/files/documents/ICD/ICD-203.pdf | official | The design philosophy of sourcing per judgement, transparency about corroboration, and standardised estimative language | 2026-07 |
| collection[10] | U.S. Department of the Army (2006). FM 2-22.3: Human Intelligence Collector Operations, Appendix B. https://irp.fas.org/doddir/army/fm2-22-3.pdf | official | The prototype of the two-axis grading that assesses origin reliability (A-F) and information credibility (1-6) separately (the NATO counterpart is AJP-2.1) | 2026-07 |
| — | Chamberlin, T. C. (1890). The Method of Multiple Working Hypotheses. Science, ns-15(366), 92-96. DOI: 10.1126/science.ns-15.366.92 | peer-reviewed (classic) | The planning-stage rule of holding several competing hypotheses | 2026-06 |
| — | Heuer, R. J. Jr. (1999). Psychology of Intelligence Analysis. CIA Center for the Study of Intelligence | official | Analysis of Competing Hypotheses (ACH): the hypothesis that survives disconfirmation is the most likely. The report's Hypothesis matrix block (pipeline.md Step 4) is its compact form: evidence × hypotheses with a diagnosticity column, worked from the diagnostic rows alone | 2026-06 |
| — | Kahneman, D., & Lovallo, D. (1993). Timid Choices and Bold Forecasts: A Cognitive Perspective on Risk Taking. Management Science, 39(1), 17-31. DOI: 10.1287/mnsc.39.1.17 | peer-reviewed | The outside view: a forecast starts from the base rate of its reference class and adjusts from there (the Outside view block for predictive questions) | 2026-09 |

## 2. Grounds for the interpretation contract

| Ref | Source | Tier | How this skill applies it | Verified |
|---|---|---|---|---|
| interpretation[1] | Liu, N. F., et al. (2024). Lost in the Middle: How Language Models Use Long Contexts. TACL, 12, 157-173. DOI: 10.1162/tacl_a_00638 (preprint arXiv:2307.03172) | peer-reviewed | Split synthesis and restating key facts in tables (countering the middle-of-context blind spot) | 2026-07 |
| interpretation[2] | Sharma, M., et al. (2023/2024). Towards Understanding Sycophancy in Language Models. arXiv:2310.13548 (ICLR 2024) | conference/preprint | Not privileging the user's hypothesis (sycophancy countermeasure) | 2026-06 |
| interpretation[3] | Sieker, J., Lachenmaier, C., & Zarrieß, S. (2025). LLMs Struggle to Reject False Presuppositions when Misinformation Stakes are High. CogSci 2025. arXiv:2505.22354 | conference/preprint | The rule that turns presuppositions in the request into verification targets | 2026-06 |
| interpretation[4] | Zheng, C., et al. (2024). Large Language Models Are Not Robust Multiple Choice Selectors. arXiv:2309.03882 (ICLR 2024) | conference/preprint | Evaluating twice with the order swapped | 2026-06 |
| interpretation[5] | Walters, W. H., & Wilder, E. I. (2023). Fabrication and errors in the bibliographic citations generated by ChatGPT. Scientific Reports, 13, 14045. DOI: 10.1038/s41598-023-41032-5 | peer-reviewed | Evidence that verbatim-quote matching and DOI resolution are needed against fabricated citations | 2026-07 |
| interpretation[7] | Rashkin, H., et al. (2023). Measuring Attribution in Natural Language Generation Models. Computational Linguistics, 49(4), 777-840. DOI: 10.1162/coli_a_00486 (preprint arXiv:2112.12870) | peer-reviewed | The concept of attributability: every claim links to the passage in its source | 2026-07 |
| interpretation[6] | Vu, T., et al. (2024). FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation. Findings of ACL 2024. DOI: 10.18653/v1/2024.findings-acl.813 (arXiv:2310.03214) | peer-reviewed (conference) | Countering the confusion of training-time knowledge with search results (recording the as-of date, absolute dates) | 2026-07 |
| interpretation[8] | Tversky, A., & Kahneman, D. (1974). Judgment under Uncertainty: Heuristics and Biases. Science, 185(4157), 1124-1131. DOI: 10.1126/science.185.4157.1124 | peer-reviewed | The anchoring countermeasure (do not make the first figure the reference point) | 2026-06 |
| interpretation[9] | Kent, S. (1964). Words of Estimative Probability. Studies in Intelligence, 8(4), 49-65. https://www.cia.gov/resources/csi/studies-in-intelligence/archives/vol-8-no-4/words-of-estimative-probability/ | official | The prototype for mapping confidence labels onto probability bands | 2026-07 |
| — | Johnson, M. K., Hashtroudi, S., & Lindsay, D. S. (1993). Source Monitoring. Psychological Bulletin, 114(1), 3-28. DOI: 10.1037/0033-2909.114.1.3 | peer-reviewed | Separating claim_type (distinguishing where a fact, an estimate, and an opinion came from) | 2026-06 |

## 3. Grounds for the evaluation protocol

| Ref | Source | Tier | How this skill applies it | Verified |
|---|---|---|---|---|
| evaluation[1] | Zheng, M., et al. (2024). When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models. arXiv:2311.10054 | conference/preprint | The grounds for using no personas (the same policy as the workflow-review family of skills) | 2026-06 |
| evaluation[2] | Dhuliawala, S., et al. (2023). Chain-of-Verification Reduces Hallucination in Large Language Models. arXiv:2309.11495. DOI: 10.48550/arXiv.2309.11495 | conference/preprint | Corroboration by answering verification questions independently; rejecting false positives | 2026-06 |
| evaluation[4] | Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023 Datasets and Benchmarks. arXiv:2306.05685 | peer-reviewed (conference) | Evidence for, and countermeasures against, position, verbosity, and self-enhancement bias in LLM evaluators | 2026-07 |
| evaluation[3] | Panickssery, A., Bowman, S. R., & Feng, S. (2024). LLM Evaluators Recognize and Favor Their Own Generations. NeurIPS 2024. arXiv:2404.13076 | peer-reviewed (conference) | Separating the writing and evaluation contexts (self-preference countermeasure) | 2026-07 |
| evaluation[5] | Liu, Y., et al. (2023). G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment. EMNLP 2023, 2511-2522. DOI: 10.18653/v1/2023.emnlp-main.153 (arXiv:2303.16634) | peer-reviewed (conference) | Explicit decomposition of the evaluation criteria (judging per criterion rather than by an impression score) | 2026-07 |
| evaluation[6] | Min, S., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023, 12076-12100. DOI: 10.18653/v1/2023.emnlp-main.741 (arXiv:2305.14251) | peer-reviewed (conference) | Measuring accuracy by decomposing into atomic facts and checking them against sources | 2026-07 |
| — | Wei, J., et al. (2024). Long-form factuality in large language models. NeurIPS 2024. arXiv:2403.18802 | peer-reviewed (conference) | Automated atomic-fact checking with search (SAFE); a procedural reference for the sampling check | 2026-07 |
| — | Wang, X., et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. ICLR 2023. arXiv:2203.11171 | peer-reviewed (conference) | The design of raising confidence through agreement across independent trials (agreement between verifiers informs a note on confidence) | 2026-07 |
| evaluation[7] | Tetlock, P. E., & Gardner, D. (2015). Superforecasting: The Art and Science of Prediction. Crown. ISBN 978-0-8041-3669-3 | book | Writing forecasts so they can be checked, and calibrating by tracking outcomes | 2026-07 |
| — | Mitchell, D. J., Russo, J. E., & Pennington, N. (1989). Back to the future: Temporal perspective in the explanation of events. Journal of Behavioral Decision Making, 2(1), 25-38. DOI: 10.1002/bdm.3960020103 | peer-reviewed | The empirical basis for imagining failure before a resubmission (premortem) | 2026-07 |
| — | Klein, G. (2007). Performing a Project Premortem. Harvard Business Review, 85(9), 18-19 | practitioner (HBR) | The same, in its practitioner formulation; the report's Premortem block for prescriptive questions writes the failure as already having happened | 2026-06 |

## 4. Grounds for the 2026-07-11 changes (deterministic citation checking, schema extensions, the delegation template, file-based hand-off, an expanded audit rubric)

| Ref | Source | Tier | How this skill applies it | Verified |
|---|---|---|---|---|
| — | Anthropic (2025). How we built our multi-agent research system. Anthropic Engineering Blog. https://www.anthropic.com/engineering/multi-agent-research-system | practitioner (primary) | The grounds for the four elements of a delegation instruction, the scale rule, and "search broadly, then narrow" | 2026-07 |
| — | Anthropic (2025). Effective context engineering for AI agents. Anthropic Engineering Blog. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | practitioner (primary) | The grounds for file-based hand-off (returning lightweight references) | 2026-07 |
| — | Cemri, M., et al. (2025). Why Do Multi-Agent LLM Systems Fail? arXiv:2503.13657 (MAST) | conference/preprint | The grounds for the subagent error-handling rules (relaunching by failure type, making task boundaries explicit) | 2026-07 |
| collection[11] | Shao, Y., et al. (2024). Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models. NAACL 2024. arXiv:2402.14207 (STORM) | peer-reviewed (conference) | The grounds for splitting collection by viewpoint (persona) on broad themes | 2026-07 |
| — | Wei, J., et al. (2024). Long-form factuality in large language models. NeurIPS 2024. arXiv:2403.18802 (SAFE/LongFact) | peer-reviewed (conference) | The policy of not asserting from self_reported effect sizes; a reference for adding rubric items R13-R15 | 2026-07 |
| — | Min, S., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023. DOI: 10.18653/v1/2023.emnlp-main.741. arXiv:2305.14251 | peer-reviewed (conference) | A design reference for the atomic-fact check and R13 (the citation_verifier integration) | 2026-07 |
| — | Gao, T., et al. (2023). Enabling Large Language Models to Generate Text with Citations (ALCE). EMNLP 2023. DOI: 10.18653/v1/2023.emnlp-main.398 | peer-reviewed (conference) | The operational grounds for the three-valued attribution judgement (supports/partial/misattributed) | 2026-07 |
| evaluation[10] | Farquhar, S., Kuhn, L., Kossen, J., & Gal, Y. (2024). Detecting hallucinations in large language models using semantic entropy. Nature, 630, 625-630. DOI: 10.1038/s41586-024-07421-0 | peer-reviewed | The grounds for R15 (noting the scope of the verification methods in the report's limitations section) | 2026-07 |
| evaluation[8] | Jaźwińska, K., & Chandrasekar, A. (2025). AI Search Has a Citation Problem. Columbia Journalism Review, Tow Center for Digital Journalism. https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php | practitioner (investigative journalism) | The poor citation accuracy of generative search; the grounds for R13 (making the deterministic citation check mandatory) | 2026-07 |
| evaluation[9] | Onweller, H., Lumer, E., Huber, A., Ramchandani, P., Subbiah, V. K., & Feld, C. (2026). Cited but Not Verified: Parsing and Evaluating Source Attribution in LLM Deep Research Agents. arXiv:2605.06635 | conference/preprint | Insufficient verification of source attribution in deep-research agents; the grounds for R13 | 2026-07 |
| interpretation[11] | Geng, S., et al. (2025). JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models. arXiv:2501.10868 | conference/preprint | That schema conformance does not guarantee content reliability (the design grounds for the degraded mark) | 2026-07 |
| — | Crossref. REST API tips for usage. https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ | practitioner (technical doc) | The technical grounds for citation_verifier.py's DOI resolution check | 2026-07 |
| — | Internet Archive. Wayback Machine Availability API. https://archive.org/help/wayback_api.php | practitioner (technical doc) | The technical grounds for citation_verifier.py's alternative route for URL reachability (the archive field) | 2026-07 |
| — | LangChain (2025). Open Deep Research. https://www.langchain.com/blog/open-deep-research | practitioner (primary) | The practitioner grounds for single-context writing at the synthesis stage and file-based hand-off | 2026-07 |
| interpretation[12] | Instructor (Liu, J. and others). Retry Mechanisms. https://python.useinstructor.com/concepts/retrying/ | practitioner (technical doc) | The design grounds for the schema-validation retry rules (at most twice, re-inserting the error verbatim) | 2026-07 |

## Operating notes

- LLM research in the conference/preprint tier (sycophancy, presupposition acceptance,
  self-preference, and so on) counts as a directional warning only: this skill uses it as grounds for building in a countermeasure procedure, never for asserting a particular effect size
- The collection-floor numbers, the seven-level confidence vocabulary, and the A/B/C source
  grades are this skill's own design values, informed by the design philosophy of ICD 203 and the like rather than taken from any external standard
- The seven-level confidence vocabulary table is identical to the confidence_bands in the
  consulting-team-v2 family. Using both skills together produces no mixing of vocabularies
- When updating or adding a source in this ledger, resolve the DOI or arXiv ID and confirm that
  it exists and matches before listing it (the same existence-verification procedure as
  consulting-team-v2's literature role, research_analyst_role.md; the countermeasure against
  fabricated citations applies to this document too)
- **Re-verification dates**: the Verified column in each table shows the month of the last check. If
  you find a dead link, a changed DOI, or a revision while referring to a source, update that
  row's Verified column to the year and month of the discovery, and for a dead link add an
  alternative URL (a Wayback Machine snapshot, for example)
