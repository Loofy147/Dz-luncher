# Research Design and Business-Validation Methodology

**Version:** 0.1  
**Purpose:** Ensure that surveys answer business decisions and that reports accurately represent what the evidence supports.

## 1. The study contract

Every campaign must have a versioned study contract before publication:

1. **Decision:** What concrete action will the business take after seeing the result?
2. **Hypotheses:** What would need to be true for that decision to be sensible?
3. **Target population:** Who is relevant, and who is explicitly not relevant?
4. **Recruitment and sampling:** Where will people come from? Is this opt-in/convenience, quota-based, stratified, or probability-based?
5. **Primary measures:** Which answers or behaviors drive the decision?
6. **Decision thresholds:** What evidence leads to proceed, revise, stop, or gather more evidence?
7. **Sample plan:** Intended completes, quotas, exclusions, and why this is sufficient for the purpose.
8. **Risk and privacy:** Data collected, purpose, access recipients, retention, consent/notice, and sensitivities.
9. **Incentive:** Exact reward, qualification conditions, timing, and dispute route.
10. **Known limitations:** Coverage, selection bias, self-reporting, small subgroups, seasonality, and conflicts of interest.

The platform should prevent campaign publication when the decision, target population, reward terms, or privacy notice are missing.

## 2. Validation stages

### Stage A — Problem and customer

- What does the target customer do today to solve this problem?
- When did the problem last occur?
- What did they do, spend, or give up to resolve it?
- How often does it occur and what makes the current alternatives inadequate?
- Who experiences it, pays for it, and decides to buy?

Avoid leading prompts such as “Would you use our amazing solution?” Prefer concrete past behavior and trade-offs.

### Stage B — Alternatives and competitive context

Record current alternatives, informal workarounds, competitor names where volunteered, switching cost, and reason for dissatisfaction. Compare the proposed product against plausible alternatives, including “do nothing.”

### Stage C — Concept comprehension

Show one clear concept at a time. Ask respondents to explain in their own words what it does, who it is for, and what is unclear before asking whether they like it. Randomize presentation order where comparison effects matter.

### Stage D — Demand and intent

Measure the problem frequency, current solution use, and likelihood of trying/buying. Separate stated intent from behavior. Where feasible, add a real next step such as a qualified contact request, prototype task, waitlist registration, product trial, or paid pilot.

### Stage E — Pricing

Avoid relying solely on “How much would you pay?” Use one or more of: realistic price choice, package trade-off, competitor price comparison, purchase-intent change at specific amounts, or a small real paid pilot. Be transparent where a price is hypothetical.

### Stage F — Distribution and execution

Test where the target segment discovers options, which channel they trust, delivery/pickup needs, support expectations, payment constraints, and what could prevent adoption after stated interest.

### Stage G — Operational and compliance risks

Check requirements that can invalidate the concept: product restrictions, permits, consumer safety, data collection, payment/fulfillment, returns, support, and unit economics. Refer regulated topics to qualified reviewers; do not offer legal conclusions automatically.

## 3. Evidence labels

Each reported claim should have one primary status and supporting references:

- **ESTABLISHED:** supported by direct, reliable evidence already available.
- **EXPERIMENTALLY_SUPPORTED:** an experiment met its pre-defined threshold under the stated conditions.
- **USER_REPORTED:** respondent/customer statement not independently corroborated.
- **INFERENCE:** interpretation that follows from evidence but is not directly observed.
- **HYPOTHESIS:** not yet tested adequately.
- **CONTRADICTED:** reliable evidence conflicts with the claim.
- **UNKNOWN:** no adequate evidence.
- **OPEN:** a question/decision remains unresolved.

Statuses are not a numeric “business success score.” A claim may change status when new evidence is added. Reports should preserve earlier results and show which evidence caused the change.

## 4. Sampling and claims

Every study report records:
- Recruitment source and mode.
- Field dates and locations.
- Eligibility criteria and screen-outs.
- Planned and achieved quotas.
- Targeted and achieved sample size.
- Number invited, started, submitted, accepted, excluded, and appealed.
- Any weighting method and rationale, if used.
- Limitations and likely sources of bias.

### Rule against false precision

Do not show a population margin of sampling error for opt-in or convenience samples as though they were probability samples. If an interval is calculated for a descriptive metric, explain the assumptions. Do not break out small subgroups where the result risks identifying people or is too unstable to interpret.

Quotas improve coverage against chosen dimensions but do not by themselves make a sample representative. A large sample may still be biased.

## 5. Survey-writing standards

- One concept per question.
- Avoid double-barrelled, leading, emotionally loaded, or ambiguous wording.
- Provide mutually exclusive and collectively appropriate answers where applicable; include “none,” “other,” “not sure,” or “prefer not to answer” where relevant.
- Use balanced scales with clear endpoints.
- Use recall periods for frequency questions.
- Keep the mobile experience readable and avoid overly wide matrix grids.
- Put sensitive or intrusive questions only when justified and approved.
- Use short, understandable Arabic. Allow campaign authors to specify simplified MSA or Darja style, while preserving the platform’s Arabic-first default.
- Randomize choices only where ordering is not meaningful.
- Pilot-test the form with a few people from the intended audience before broad launch.

## 6. Template families

### Idea / problem discovery

Outputs: priority problems, existing workarounds, severity/frequency, affected segments, language the customer uses to describe the need.

### Product / concept test

Outputs: comprehension, strongest/weakest propositions, comparison to alternatives, objections, and next prototype questions.

### Price and package test

Outputs: preference by price/package, trade-offs, segment-level sensitivity, and a recommendation for further validation rather than a claim of exact market price.

### App / digital service test

Outputs: task completion, failure points, comprehension, perceived usefulness, trust barriers, onboarding friction, and stated versus observed behavior.

### Local-service test

Outputs: service location/coverage, preferred booking channel, hours, delivery expectations, trust concerns, acceptable price, and key operational barriers.

### Customer experience

Outputs: satisfaction/effort, reasons for dissatisfaction, churn risks, and service improvements. NPS/CSAT can be included but must not replace diagnostic questions.

### Product sample test

Outputs: test protocol adherence, use observations, sensory/functional feedback where safe, product issues, and complaint/incident record. Requires separate product safety, fulfillment, and liability controls.

## 7. Reporting structure

1. Executive decision question.
2. Study design and hypotheses.
3. Sample and recruitment details.
4. Key findings linked to each hypothesis.
5. Evidence status and threshold evaluation.
6. Segment/geography views where supportable.
7. Response-quality and exclusion summary.
8. Limitations and counter-evidence.
9. Recommended decision: proceed, revise, stop, or run a discriminating test.
10. Raw exports and respondent-level data only where justified and authorized; aggregate report is default.

## 8. Review gates

Before publish: research design checklist, neutral question review, sample feasibility, reward clarity, privacy review, and product/category policy check.

During fieldwork: monitor quota imbalance, screening anomalies, completion time, quality signals, and respondent complaints.

Before report: freeze instrument version, deduplicate, review quality flags, document exclusions, reconcile reward obligations, and verify calculations against a known test dataset.
