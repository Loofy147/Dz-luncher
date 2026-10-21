# Product Requirements Document (PRD)

**Version:** 0.1  
**Status:** Draft for validation  
**Audience:** Product, engineering, research operations, business development, legal/privacy reviewers

## 1. Product goal

Help people launching businesses, services, products, and digital projects in Algeria validate the most important assumptions before investing heavily. Let suitable participants contribute honest feedback and product-test evidence for transparent rewards.

### Primary outcome

A business user completes a study and receives a report that changes or confirms a concrete next decision, with traceable evidence and explicitly stated limitations.

### Secondary outcome

A participant can identify relevant opportunities, understand the expected effort and reward before starting, complete eligible work, and trust the status and fulfillment of their reward.

## 2. Problem statement

Founders often collect informal opinions through social posts or personal networks. Those results can be biased, poorly targeted, leading, too small, disconnected from pricing or behavior, and difficult to translate into a decision. Formal research can be inaccessible for smaller projects. Meanwhile, respondents need clear study terms and a trustworthy way to participate in research or product tests.

**HYPOTHESIS:** a guided, Arabic-first platform that bundles study design, local recruitment, response-quality controls, and decision-oriented reporting can serve a gap between informal polls and high-touch research agencies. This requires customer discovery and competitor validation before being treated as fact.

## 3. Target users and jobs to be done

### 3.1 Business-side users

**Initial segments to test:**
- Individual founders and student entrepreneurs.
- Micro and small businesses testing a new product or service.
- Local retailers, service providers, and makers testing demand or customer experience.
- Digital product teams testing prototypes and onboarding.
- Research/marketing consultants who need a local panel or execution layer.

**Jobs to be done:**
- “Help me define the actual decision I need to make.”
- “Help me identify who should answer and what evidence would change my decision.”
- “Help me recruit participants beyond my friends and followers.”
- “Help me compare concepts/prices/alternatives without leading the respondents.”
- “Show me whether my sample is sufficient for the intended conclusion.”
- “Give me an actionable report and next experiment, not only charts.”

### 3.2 Participant-side users

**Jobs to be done:**
- Find relevant studies without searching multiple social pages.
- Know the time, eligibility, reward, approval rules, and privacy terms before beginning.
- Avoid repeated disqualification after investing time.
- Track submitted, under-review, accepted, disputed, and rewarded states.
- Participate in low-risk product tests with clear instructions and support.

### 3.3 Operations users

Moderators need evidence to review suspected low-quality responses and participant appeals. Reward operators need to reconcile commitments and fulfillment while avoiding access to raw answer data when unnecessary.

## 4. Product principles

1. The decision and hypotheses are defined before the survey goes live.
2. Participant reward value and approval conditions are disclosed before participation.
3. “Supported” is not the same as “proven”; findings carry method and sampling limitations.
4. Data collection is purpose-bound and minimized.
5. Surveys are mobile-first, short where possible, accessible, and RTL-correct.
6. Rewards and data quality are handled with auditable state transitions.
7. No category or sample coverage is promised without operational evidence.

## 5. Core user journeys

### 5.1 Create and validate a business idea

1. Select a study goal: problem discovery, concept test, pricing, prototype usability, customer experience, or product test.
2. Enter the business context, decision deadline, target segment, geography, alternatives, and known constraints.
3. Define key hypotheses and evidence thresholds; system flags vague or leading research questions.
4. Select a reviewed template or build questions.
5. Configure eligibility, quotas, target completes, recruitment method, reward, campaign budget, privacy notice, and retention period.
6. Preview as a participant on mobile; pass quality checklist and any moderation/legal review.
7. Fund/authorize campaign budget through an approved process; launch.
8. Monitor responses, quota progress, quality flags, and costs.
9. Close collection; review exclusions and any appeals; reconcile rewards.
10. Receive a report with descriptive findings, evidence status, limitations, and the recommended next test.

### 5.2 Participate in a survey

1. Discover a study card showing topic, estimated time, reward, status, audience requirements, and product/sensitive-data warnings where relevant.
2. Read short privacy and study terms; consent where required.
3. Complete screening questions; if screened out, the screen-out policy is shown before the study begins.
4. Complete the survey with progress, accessible inputs, and save/resume where supported.
5. Submit once; receive a receipt and status.
6. If quality checks flag a response, show an understandable status and review/appeal route without exposing fraud controls that enable evasion.
7. For accepted responses, show reward due and then fulfilled with reference/receipt where available.

### 5.3 Run a product/prototype test

1. Campaign states what is being tested, test requirements, target users, risks, item ownership/return expectations, and reward.
2. Participant qualifies and explicitly accepts the test protocol.
3. Logistics and test access are recorded separately from survey answers.
4. Participant performs defined task(s) and submits feedback/evidence only as necessary.
5. Operator reviews completion and any safety/support issues.
6. Reward is approved and fulfilled; study report separates product-use observations from survey opinions.

## 6. Functional scope

### 6.1 MVP — must have

**Identity and access**
- Participant account and business account paths.
- Organization/project membership and role checks.
- Admin/moderator role separation; no shared “admin” account in operational use.
- Basic verification appropriate to risk; do not require government identity documents for ordinary anonymous opinion surveys by default.

**Project validation workspace**
- Project profile: business/product/service, stage, market, customer segment, alternatives, geography, deadline.
- Explicit decision and hypothesis records.
- Validation checklist for problem, segment, demand, alternatives, price, acquisition/distribution, feasibility, and relevant compliance.
- Evidence-status labels and references to evidence/results.

**Survey builder and runtime**
- Supported question types: single choice, multiple choice, scale, ranking, short text, long text, numeric, and image/concept card where justified.
- Required/optional questions, answer constraints, simple branching, screening, quotas, survey versioning, preview.
- Arabic RTL and responsive mobile rendering; correct keyboard and screen-reader labels.
- Clear estimated time and save/submit state.
- Published surveys use immutable version snapshots so results can be interpreted against the exact instrument shown.

**Campaign and recruitment**
- Target audience criteria and wilaya field.
- Quota definitions and achieved quota display.
- Target completes, open/close dates, campaign cap, recruitment source, and study status.
- Participant frequency cap per study/category as configured.
- Invite link and in-platform discovery; no requirement to reach every wilaya before launch.

**Response quality**
- Duplicate-attempt prevention.
- Eligibility screening and documented exclusion rules.
- Time, consistency, repeated-pattern, attention-check, and duplicate signals as review inputs.
- Manual review and an auditable accept/reject/appeal decision.
- Quality policy disclosed in plain language without publishing evasion-sensitive details.

**Rewards**
- Clear reward and acceptance conditions shown before start.
- Budget/reward commitment record and ledger of due, accepted, held, fulfilled, reversed, and disputed amounts/items.
- Initially supported fulfillment channels configured by operators after partner/legal validation (e.g., merchant voucher or top-up); no platform wallet or peer transfers in MVP.
- Reward status and history for participant and authorized business users.
- Failed fulfillment retry and reconciliation queue.

**Reports**
- Response counts, demographic/segment breakdowns only where safe and adequately sized, quota coverage, timing, exclusions, missing data, descriptive charts, open-text themes, and exports.
- Recruitment method, field dates, question version, incentive, and limitations always accompany results.
- Findings mapped to hypotheses and pre-defined decision thresholds.
- No unsupported representativeness claims.

**Operations**
- Campaign moderation queue, report/complaint queue, reward reconciliation, study pause/close controls, incident controls, and audit trail.
- Backups, restore tests, error monitoring, operational runbook, and data deletion process.

### 6.2 Next phase — only after pilot evidence

- Advanced question logic and reusable question library.
- Panel profiling with opt-in preferences and refresh controls.
- Scheduled/longitudinal studies and participant communities.
- Multi-language survey content per project while Arabic remains the platform default.
- Partner integrations for vouchers, top-ups, and product fulfillment.
- Optional guided researcher/analyst services.
- More advanced weighting where sampling design and expertise support it.

### 6.3 Explicitly out of scope for MVP

- Guaranteeing product-market fit or business success.
- Claims of nationally representative results from opt-in/convenience recruitment.
- Public political polling, high-risk sensitive-data research, or biometric collection.
- Medical diagnosis, clinical research, prescription/regulated products, ingestible/cosmetic/children's product trials, or other high-liability product testing before specialist review.
- Randomized prize draws or lottery-like reward mechanics.
- Transferable points, peer-to-peer transfers, cash-out balances, lending, or a general-purpose wallet.
- Automatic AI decisions that permanently ban a participant or reject a reward without review.
- Selling individual-level personal answers to business customers.

## 7. Permissions model

| Capability | Owner | Research editor | Analyst/viewer | Reward operator | Moderator | Platform admin |
|---|---:|---:|---:|---:|---:|---:|
| Manage organization members | Yes | No | No | No | No | Support-only/system |
| Create/edit study drafts | Yes | Yes | No | No | No | Policy review only |
| Publish/fund/close campaign | Yes | Configurable | No | Budget status only | Pause/review | Emergency controls |
| View raw answers | Yes, scoped | Yes, scoped | Aggregate by default | No | Only if needed for review | Restricted break-glass |
| Export identifiable data | Default deny | Default deny | No | No | No | Audited exceptional path |
| Review response quality | See project scope | See project scope | No | No | Yes | Audit/review |
| Fulfill/reconcile rewards | View status | View status | No | Yes | No | Audit/recovery |
| Delete/export personal data request | Initiate | No | No | No | No | Execute authorized process |

All access is tenant-scoped, least-privilege, and logged. Business account roles must not grant access across unrelated organizations.

## 8. Business model hypotheses

Validate these rather than selecting prices now:
- Campaign package fee based on target completes, eligibility complexity, and delivery requirements.
- Clearly separated reward/fulfillment budget.
- Optional paid help for study design, analysis, or moderated testing.
- Agency/researcher plans after the core execution process is reliable.

The participant's disclosed reward must not be quietly reduced to fund platform margin.

## 8.1 Evidence status vocabulary

Reports and validation records use a controlled vocabulary: **ESTABLISHED**, **EXPERIMENTALLY_SUPPORTED**, **USER_REPORTED**, **INFERENCE**, **HYPOTHESIS**, **CONTRADICTED**, **UNKNOWN**, and **OPEN**. A status must include a reason and supporting evidence reference; statuses are not a numeric probability of business success. See `VALIDATION_METHODOLOGY.md`.

## 9. Success metrics

**Business value**
- Qualified prospect-to-paid-pilot conversion.
- Percentage of completed reports tied to an explicit decision.
- Repeat campaign rate and time from brief to first useful finding.
- Percentage of users who take the next action recommended by the report.

**Marketplace health**
- Time to recruit a qualified complete by segment/wilaya.
- Invitation-to-start, start-to-complete, screen-out, and accepted-response rates.
- Cost per accepted complete and reward fulfillment time.
- Quota completion and distribution gaps.

**Trust and safety**
- Reward fulfillment success and on-time rate.
- Appeal rate, reversed exclusions, complaint rate, and unexplained reward holds.
- Duplicate/fraud flags confirmed after review; false-positive rate.
- Data-rights request completion and deletion SLA compliance.
- Incidents and unauthorized data exports.

**Data usefulness**
- Percentage of studies with pre-defined hypotheses and decision thresholds.
- Reports that disclose recruitment and sampling limitations.
- Rate of results classified as inconclusive (not inherently a failure).

## 10. Proposed pilot success gate

**PROPOSED TEST, NOT AN INDUSTRY BENCHMARK:** run a managed pilot with 3–5 paying or seriously committed business clients across 2–3 low-risk study types, and recruit approximately 100–300 qualified completes in aggregate. Adapt counts after interviews and budget confirmation. Pass only if businesses use the reports for real decisions, participants understand reward terms, reward fulfillment works, and the data/quality controls are operationally credible.

## 11. Critical open decisions

- Formal business entity/controller and participant-facing terms.
- Hosting location, backups, analytics, error reporting, AI usage, and data-transfer review.
- Initial reward methods and provider contracts.
- Who conducts moderation/research review and at what cost.
- Exact market segments and initial study categories.
- Campaign pricing and payment/funding model.
- Data retention schedule by data category.
- Whether/when French UI and survey-language support are introduced.
