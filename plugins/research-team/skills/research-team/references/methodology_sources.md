# Methodology sources

The published evidence behind research-team 2.0's design. No execution path reads this file.
Every arXiv ID below was resolved against the arXiv API on 2026-10-24, and the title and first
author matched. Tiers: **peer-reviewed** (journal or archival conference), **preprint**, and
**first-party** (an engineering post or prompt file from the organisation that built the system;
self-reported, and reproducible only by that organisation).

## Cost, effort and orchestration

| Source | Tier | Design rule it supports |
|---|---|---|
| Anthropic Engineering (2025-06-13). How we built our multi-agent research system. https://www.anthropic.com/engineering/multi-agent-research-system | first-party | "token usage by itself explains 80% of the variance" on BrowseComp; effort tiers ("Simple fact-finding requires just 1 agent with 3-10 tool calls") |
| Anthropic, claude-cookbooks, `patterns/agents/prompts/research_subagent.md`. https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/prompts/research_subagent.md | first-party | the subagent cap "under a limit of 20 tool calls"; the DEEP tool budget |
| Anthropic Engineering (2025-09-29). Effective context engineering for AI agents. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | first-party | workers return "a condensed, distilled summary"; file hand-off |
| Tran, D., & Kiela, D. (2026). Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets. arXiv:2604.02460 | preprint | agents only where context isolation or independence is the point |
| Cemri, M., et al. (2025). Why Do Multi-Agent LLM Systems Fail? arXiv:2503.13657 | preprint | explicit hand-off contracts; relaunch rules |
| Zhu, C., et al. (2026). FS-Researcher: Test-Time Scaling for Long-Horizon Research Tasks with File-System-Based Agents. ACL 2026. arXiv:2602.01566 | peer-reviewed | diminishing returns past 5 rounds; the persistent file workspace |
| Zeng, W., et al. (2025). Pushing Test-Time Scaling Limits of Deep Search with Asymmetric Verification. arXiv:2510.06135 | preprint | budget moved from collection to verification |
| Hong, K., Troynikov, A., & Huber, J. (2025). Context Rot. Chroma. https://www.trychroma.com/research/context-rot | vendor report | a small orchestrator context |
| Liu, N. F., et al. (2024). Lost in the Middle: How Language Models Use Long Contexts. TACL 12, 157-173. arXiv:2307.03172 | peer-reviewed | short digests; the Answer first |

## Citations and verification

| Source | Tier | Design rule it supports |
|---|---|---|
| Venkit, P. N., et al. (2025). DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations and Evidence. arXiv:2509.04499 | preprint | the deterministic quote check |
| Rao, D., Wong, E., & Callison-Burch, C. (2026). Detecting and Correcting Reference Hallucinations in Commercial LLMs and Deep Research Agents. arXiv:2604.03173 | preprint | URL, DOI and arXiv resolution |
| Onweller, H., et al. (2026). Cited but Not Verified: Parsing and Evaluating Source Attribution in LLM Deep Research Agents. arXiv:2605.06635 | preprint | sentence-to-source verification |
| Du, M., et al. (2025). DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents. arXiv:2506.11763 | preprint | fewer, verified citations |
| Rashkin, H., et al. (2023). Measuring Attribution in Natural Language Generation Models. Computational Linguistics 49(4), 777-840. arXiv:2112.12870 | peer-reviewed | every claim attributable to a passage |
| Dhuliawala, S., et al. (2023). Chain-of-Verification Reduces Hallucination in Large Language Models. arXiv:2309.11495 | preprint | the verifier sees one claim and its source, never the report |
| Min, S., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023. arXiv:2305.14251 | peer-reviewed | sentence-level support as the unit of verification and evaluation |
| Wei, J., et al. (2024). Long-form factuality in large language models. NeurIPS 2024. arXiv:2403.18802 | peer-reviewed | search-backed claim checking by an LLM |
| Chaganti, V. K. (2026). On-Device Deep Research at 4B: Exposure Bounds Faithfulness, Retrieval Bounds Coverage. arXiv:2607.12257 | preprint | digests carry the quote with its surrounding passage |

## Writing and judgement

| Source | Tier | Design rule it supports |
|---|---|---|
| Shao, Y., et al. (2024). Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models. NAACL 2024. arXiv:2402.14207 | peer-reviewed | the outline before prose (Table 2: RAG to oRAG, and STORM without its outline stage) |
| Sharma, M., et al. (2024). Towards Understanding Sycophancy in Language Models. ICLR 2024. arXiv:2310.13548 | peer-reviewed | the user's view is one hypothesis among others |
| Sieker, J., Lachenmaier, C., & Zarrieß, S. (2025). LLMs Struggle to Reject False Presuppositions when Misinformation Stakes are High. CogSci 2025. arXiv:2505.22354 | peer-reviewed | presuppositions in the request become sub-questions to verify |
| Vu, T., et al. (2024). FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation. Findings of ACL 2024. arXiv:2310.03214 | peer-reviewed | the as-of date and absolute dates |
| Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023 Datasets and Benchmarks. arXiv:2306.05685 | peer-reviewed | the evaluation judges each pair twice with the order swapped |

## Notes

- Preprint and first-party results set the direction of a design choice. The effect on this
  plugin is measured in its own evaluation (`eval/README.md` in the repository).
- The A/B/C grades, the tool budgets and the seven-label confidence scale are this skill's own
  design values.
- Before adding a source, resolve its DOI or arXiv ID and confirm the title and first author.
