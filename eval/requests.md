# Evaluation requests

Each block is pasted, as it stands, into a new Claude Code session started in `C:\Mycode\ClaudeCode`.
The request text is the requester-settled part of the 1.x brief, quoted verbatim: its Purpose section, and for the two
lecture studies the key questions the requester posed. Brief paths are under `C:\Mycode\ClaudeCode\`.

## 20260825-solo-se-project-scale (STANDARD, request language ja)

````text
research-team で調べてください。段階は STANDARD です。以下が依頼内容です。

### 目的

事業会社の情報システム部門に所属する社内SE 1人が、開発施策をどこまでの規模で引き受けられるかを、工数・金額・保有システム数・機能規模の4単位で示す。読者はこの結果を、施策を1人に任せるか分割するか増員するかの判断に使う。

- 想定読者: 社内SE本人、および情報システム部門で要員配置と施策の切り分けを決める立場の人
- 既定値の記録: ユーザーが指定した事項は「社内SEの立場」「4単位での回答」「AIコーディング支援を前提に含めない」「STANDARD」の4点。それ以外は既定値を採用した。地域は日本を主とし、海外の知見は転用可否を明記して補助的に使う。期間は直近3年の統計を優先し、見積もりモデルなど古くても代替のない知見は理由を付けて使う。
````

## 20260928-llm-japanese-business-register (STANDARD, request language en)

````text
Research this with research-team at the STANDARD tier. The request follows.

### Purpose

The maintainer of the Claude Code skill html-doc decides, from this research, which generation-time writing rules (the "Language" section of the global CLAUDE.md, the 文体 and message-line rules of doc-types.md, SKILL.md Requirements 3, 4, 6 and 7) and which post-generation checks (the textlint technical-writing preset, the banned-phrase register, the natural-japanese lint, the 公用文 morphology lint, the doc-reader cold read) to add, change or remove, so that the skill's Japanese plans and completion reports read as written by a competent Japanese employee.

- Intended readers: the html-doc maintainer, a Japanese engineer who writes and maintains these rules and checks.
- Deliverable language: en. The prose is English; section headings, table headers and confidence labels are English; quotations from Japanese sources stay in Japanese, verbatim.
- Defaults recorded:
  - Local materials: the four files the requester named, read in place. CLAUDE.md is read for its "Language" section only.
  - Period: evidence on LLM markers and prompting from January 2023 to September 2026. Standards are taken at their current published version, whatever its date.
  - The requester's statement that the specimen passed all four lints is accepted without re-running them.
  - "A competent Japanese employee" is read as a Japanese software engineer writing an internal plan or report for a Japanese colleague or manager.
- Local materials: ~\.claude\plans\cobol-insight-gui-design-2026-09-27\doc.md (the specimen); ~\.claude\CLAUDE.md (section "Language" only); ~\.claude\skills\html-doc\references\doc-types.md (sections 文体 and The message line); ~\.claude\skills\html-doc\SKILL.md (Requirements 3, 4, 6 and 7). They are read in place and form one independence cluster, since one author wrote all four.
````

## teaching-delivery (DEEP, request language en)

````text
Research this with research-team at the DEEP tier. The request follows.

### Purpose / 目的

This research decides what rules a lecture **delivery** layer should implement: how a point is
explained, what examples carry it, and what makes it stay with the learner after the session. The
consumer is the designer of a Claude Code skill that plans professional technical lectures. Every
finding must therefore be stated as a constraint on a **teaching-delivery rule that a script or a
checklist can implement**, with the boundary of its evidence attached, so the designer can convert
it into a rule or reject it with a stated reason.

- Intended readers: the designer of the lecture-planning skill; secondarily, anyone auditing why a
  delivery rule exists or why one was refused.
- Destination audience of the eventual lectures: working adults in professional technical training
  (programming, system design, business-system training), in Japanese, in multi-hour sessions,
  delivered either **presented** (the instructor controls the pace) or **read alone** (the learner
  controls the pace). Where a technique's evidence is bounded to one of those two pacing regimes,
  the report says which, because the consumer's plans carry both.
- Settled by the requester, not defaulted: DEEP mode; the subject scope; the mandatory two-sided
  treatment of 学習指導要領; the deliverable language; the output directory; the seven key questions
  and their decision split; the four competing hypotheses; the disconfirmation seeds.
- Defaults adopted:
  - Geography and period: no country restriction; literature of any year is admissible, with
    preference for meta-analyses, registered replications and large trials published in or after
    2010 where they exist.
  - Where a principle was established on undergraduates or schoolchildren in short purpose-built
    lessons, the transfer to working adults in multi-hour professional training is recorded as an
    **inference**, not a finding.
  - Every evidence unit is tagged with the requester's four-level strength scale — `experiment`,
    `standard`, `contract`, `none` — and with the boundary of its study population.
  - No effect size is reported without its confidence interval, or without an explicit note that
    none was published.
  - A quote resting on a collection agent's reading alone, with no independent re-fetch, is marked
    **reported, not independently checked**.
  - The repository's own design documents and the earlier study's report were deliberately **not**
    read, per the requester's independence condition. The earlier study's brief was read for its
    formatting conventions only.
### Key questions / キークエスチョン

- KQ1: What does the evidence say about teaching from worked examples — the worked-example effect, fading to completion problems, and how the benefit changes as the learner's expertise grows? [決定]
- KQ2: How should the examples themselves be chosen and presented — concrete against abstract, one example against several, contrasting cases, analogy — and what does each buy in learning and in transfer? [決定]
- KQ3: What do retrieval practice, spaced practice and interleaving buy, does the effect hold for complex authentic material and at classroom scale, and which forms can run inside a lecture the learner does not pace? [決定]
- KQ4: Is a learner better served by being given an explanation or by being prompted to generate one, and what effect sizes and moderating conditions decide which wins? [決定]
- KQ5: What does 学習指導要領 normatively require of teaching — 資質・能力の三つの柱, 主体的・対話的で深い学び, 見方・考え方, 指導と評価の一体化 — read off primary sources? [背景]
- KQ6: For each of those 学習指導要領 requirements, does a controlled outcome study exist, in Japanese or any other language, and what does it report? [背景]
- KQ7: What do formative assessment, feedback and in-lecture questioning buy, and how well do the headline effect sizes survive scrutiny? [背景]

KQ5, KQ6 and KQ7 are `背景` because they establish premises and calibration rather than supply a
delivery rule directly. They still carry the full disconfirmation duty set out below — KQ6 exists
precisely to test KQ5's normative requirements against outcome evidence, and KQ7 carries the
Kluger & DeNisi and Black & Wiliam scrutiny the requester named.

### Competing hypotheses / 競合仮説

- H1: A learner learns more when the explanation is supplied well — a clear instructional explanation delivered at the right moment beats leaving the learner to construct one.
- H2: A learner learns more when prompted to generate the explanation themselves; a supplied explanation substitutes for the very processing that produces the learning.
- H3: Retrieval practice, spacing and interleaving transfer from the laboratory to real classrooms and to complex professional material, and belong in a lecture plan as defaults.
- H4: Their measured advantage shrinks or vanishes with complex material, adult learners and course-scale delivery — real, but small relative to everything else that varies in a professional training room, and therefore laboratory results oversold as classroom rules.

H1 and H2 are the requester's opposed pair for KQ4 and bear on KQ1 and KQ2; H3 and H4 are the
opposed pair for KQ3 and bear on KQ7. None of the four is the researcher's own prior, and none is
privileged. Supporting and disconfirming evidence is searched with equal effort for each, and each
is aimed at its strongest form: for H4 the strong form is not "retrieval practice is fake" but "it
is real and small relative to everything else that varies in a professional training room".
````

## teaching-design (DEEP, request language en)

````text
Research this with research-team at the DEEP tier. The request follows.

### Purpose / 目的

This research decides what rules a lecture **content-planning** layer should implement: what a
lecture covers, in what order, and how that changes with who is in the room. The consumer is the
designer of a Claude Code skill that will sit upstream of an existing slide-rendering skill and
hand it a session outline. Findings must therefore be stated as constraints on a *content plan*,
each with the boundary of its evidence, so the designer can convert them into rules or reject them.

- Intended readers: the designer of the content-planning skill; secondarily, anyone auditing why a
  planning rule exists.
- Defaults adopted:
  - Geography and period: no restriction on country; literature of any year is admissible, with
    preference for meta-analyses and replications published in or after 2010 where they exist.
  - Audience of the eventual lectures: working adults in professional technical training
    (programming, system design, business-system training). Where a principle was established on
    undergraduates in short purpose-built lessons, the transfer to this audience is recorded as an
    inference, not a finding.
  - The existing repository implementation was deliberately **not** read, per the requester's
    independence condition.

### The requester's questions

The requester posed eight questions (RQ0–RQ7); every one must be answered in the report.

| Requester's question | Key question in the earlier study | Decision relevance |
|---|---|---|
| RQ0 lecture-format effectiveness (premise check) | KQ1 | 背景 |
| RQ1 basis for selecting and discarding content | KQ2 | 決定 |
| RQ2 presentation order and prerequisite chains | KQ3 | 決定 |
| RQ3 upper bound on one lecture's content | KQ4 | 決定 |
| RQ4 prior-knowledge assessment and adaptation | KQ4 | 決定 |
| RQ5 misconceptions feeding content selection | KQ5 | 背景 |
| RQ6 motivation and relevance | KQ6 | 背景 |
| RQ7 what the designer investigates before designing | KQ7 | 決定 |

RQ0, RQ5 and RQ6 are `背景` because they establish premises rather than supply a planning rule
directly; they still receive the full disconfirmation duty set out below, which is where the
requester's emphasis on them lies.
### Key questions / キークエスチョン

- KQ1: How effective is the one-directional lecture format for measured learning outcomes, what separates the cases where it works from those where it does not, and how much can material design compensate? [背景]
- KQ2: On what basis is lecture content selected and discarded, and which of the selection frameworks in wide use have a measured relation to learning outcomes rather than only wide adoption? [決定]
- KQ3: What determines the presentation order of lecture content, and how is a prerequisite-knowledge chain constructed and validated? [決定]
- KQ4: What sets the upper bound on how much one lecture can cover, and how must the content change with the learners' prior knowledge? [決定]
- KQ5: How should the misconceptions learners already hold feed the selection of lecture content? [背景]
- KQ6: How do motivation and perceived relevance bear on which content is chosen, and how well do the reported effects replicate? [背景]
- KQ7: Before designing content, what should the designer investigate about the learners and the task, by what method, and what does the evidence say those methods buy? [決定]
````
