# Roadmap and Implementation Backlog

**Version:** 0.2  
**Rule:** each phase has an evidence/acceptance gate. Do not grow scope just because an item is technically possible.

## Implementation delta — 20 October 2026

- ✅ Standalone Python reference core for Arabic normalization, survey schema/branch validation, screening, batch quotas, quality signal groups, version binding, pseudonymous exports, and evidence-labelled reports.
- ✅ 34 tests pass; JSON contract examples round-trip; synthetic demo runs.
- ⬜ Core is not yet connected to transactional storage, a web API, the Arabic RTL UI, user/tenant authorization, or the reward ledger.
- ⬜ Batch quota calculations remain sequential; concurrency correctness is a database transaction/constraint requirement, not a reference-core capability.

## Phase 0 — Discovery and legal/operational decisions

### P0.1 Customer research
- [ ] Interview 10–15 founders/business operators across at least three segments.
- [ ] Ask about a recent validation decision, current methods, money/time spent, and what a useful result would change.
- [ ] Test example report and price/package choices with realistic trade-offs.
- [ ] Interview potential participants about trust, time/reward expectations, privacy concerns, and reward formats.
- [ ] Record claims as user-reported until behavior or independent evidence verifies them.

### P0.2 Legal, hosting, and rewards
- [ ] Identify operating/controller entity and contracting model.
- [ ] Map data flows and processing purposes, including all processors and backups.
- [ ] Obtain Algerian legal/ANPDP review for applicable Law 18-07/25-11 obligations and cross-border hosting.
- [ ] Confirm which reward channels are available, lawful, costed, and fulfillable.
- [ ] Define campaign funding and refund/cancellation model without assuming escrow/wallet authorization.
- [ ] Approve participant terms, privacy notice, reward terms, and product-test terms in Arabic.

**Exit gate:** no unresolved blocker on lawful handling of account/profile/answer/reward data in the chosen pilot flow; reward can be delivered reliably; at least a small business cohort is willing to pilot.

## Phase 1 — Concierge pilot (minimal software + operator workflow)

Build or manually operate:
- [ ] Business brief intake and structured decision contract.
- [ ] 3–5 reviewed survey templates.
- [ ] Pilot campaign page and participant instructions.
- [ ] Secure response collection and access controls.
- [ ] Manual respondent eligibility/quality review with recorded reasons.
- [ ] Reward ledger and fulfillment reconciliation.
- [ ] Standard evidence report and participant support path.
- [ ] Sample/source/quota reporting.

Candidate pilot types: local-service concept, digital prototype usability, and non-sensitive consumer concept. Avoid high-liability product sampling.

**Exit gate:** business users can act on reports; accepted participants receive promised rewards; no unresolved critical privacy/security incident; quality review has measurable false-positive/reversal data.

## Phase 2 — MVP product

### P2.1 Foundation
- [ ] Arabic RTL layout, accessible design system, mobile-first survey runtime.
- [ ] Identity, organizations, memberships, roles, and server-side authorization.
- [ ] Processing register, consent/notice versioning, audit events, and retention scheduler.
- [ ] Transactional data model, migrations, backups, restore test, staging/production separation.

### P2.2 Study builder and execution
- [ ] Project profile and decision-contract editor.
- [ ] Immutable survey versions and pre-publish validator.
- [ ] Core question types, required rules, simple branching, screening, quotas.
- [x] Reference validation core and JSON contract implemented/tested separately; production persistence and integration remain open.
- [ ] Campaign listing/invitation and participant opportunity details.
- [ ] Save/resume, single submission, idempotency, and study-frequency caps.

### P2.3 Quality, rewards, and reporting
- [ ] Quality signals, manual review queue, and participant appeal state.
- [ ] Reward obligations/ledger and approved provider adapter.
- [ ] Failed fulfillment/reconciliation queue.
- [ ] Aggregate reporting snapshot, sample limitations, exclusions, report export.
- [ ] Operational dashboard and support case tracking.

**Exit gate:** all release acceptance tests pass; pilot flows work end to end; report results reproduce from frozen data/instrument; reward reconciliation is idempotent; no authorization/privacy blocker remains.

## Phase 3 — Improve marketplace efficiency

- [ ] Measure recruitment time/cost by source, wilaya, and target segment.
- [ ] Better participant profiling with purpose-specific opt-in and profile refresh.
- [ ] Template packs for validated sectors based on actual client demand.
- [ ] Partner integrations for voucher/top-up and low-risk product fulfilment.
- [ ] Improve survey quality linting and sample feasibility predictions using observed data.
- [ ] Introduce subscriptions/agency offerings only after pricing experiments.

## Phase 4 — Scale and advanced research

- [ ] Longitudinal/recurring panel studies and participant frequency governance.
- [ ] Advanced sampling/weighting with specialist review and transparent methods.
- [ ] Additional language support based on paid demand.
- [ ] Dedicated analytical storage only after measured query/volume pressure.
- [ ] Formal security assessment/penetration test and independent privacy audit where proportionate.

## Backlog priority rule

Prioritize items by: customer decision value, risk reduction, pilot dependency, implementation complexity, and reversibility. Legal/privacy/reward integrity blockers outrank growth features. Avoid spending on dashboards, advanced AI, or fancy analytics until reliable campaign execution and rewards are demonstrated.
