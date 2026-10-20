# Test Plan and Acceptance Criteria

**Version:** 0.2

## 0. Reference-core verification snapshot

**Verified separately on 20 October 2026:** ✅ 34 standard-library unit/contract tests passed. Coverage includes strict JSON parsing, schema contracts, Arabic digits and decimal separators, branching, screen-out separation, response version binding, quality-signal groups, duplicate submission IDs, project-scoped pseudonyms, free-text omission, quota caps, sample-flow reports, and evidence-scope safeguards. The 15-response synthetic demo ran successfully.

This snapshot verifies the standalone Python reference engine only. It does not verify persistence, concurrent quotas, tenant authorization, the RTL browser UI, reward accounting, payment providers, or legal compliance. Those remain release-gated tests below.

## 1. Verification levels

- **Unit:** question validation, branching, eligibility, quota math, reward ledger transitions, report metrics.
- **Property/invariant:** invariants hold across generated event sequences, duplicate requests, retries, and state transitions.
- **Integration:** transactional persistence, queue/outbox, artifact store, provider adapter contracts.
- **End-to-end:** business creates campaign; participant qualifies/submits; response is reviewed; reward is fulfilled; report is produced.
- **Security/privacy:** authorization, tenant isolation, export boundaries, consent/notice, deletion, audit logs, rate limits.
- **Accessibility/usability:** Arabic RTL rendering, keyboard navigation, mobile viewport, clear status and error states.
- **Operational:** backup restore, provider outage/retry, idempotent job replay, campaign pause, incident playbook.

## 2. Domain invariants

1. A participant cannot create more than one accepted completion for a single-completion study.
2. A survey submission is bound to the immutable instrument version shown to the participant.
3. A closed or paused campaign cannot accept new eligible starts outside its policy.
4. A quota reservation cannot exceed a hard cap because of concurrent requests.
5. A reward obligation is created at most once per accepted participation.
6. A retried fulfillment request cannot produce a duplicate reward.
7. Every reward state change records actor/system, timestamp, reason/source, and correlation/idempotency reference.
8. No business user can access another organization's records by guessing IDs or altering client-side state.
9. Participant identity details are not present in default business report exports.
10. A campaign cannot publish without target population, study purpose/decision, reward terms, privacy notice, and reviewed instrument.
11. Every report records study and survey versions, recruitment method, field period, achieved sample, exclusions, and limitations.
12. Convenience/self-selected data cannot be labelled nationally representative by the system without a documented, reviewed sampling design.
13. Response-quality flags alone do not automatically cause irreversible lifetime account bans or silent reward forfeiture.
14. Product-test campaigns require a test protocol and required safety/fulfillment review fields before publication.
15. Deletion/correction requests follow the reviewed retention/legal policy and leave only justified audit evidence.

## 3. Functional acceptance scenarios

### A. Business workflow
- [ ] Create organization and assign an editor/viewer; verify organization and project scopes.
- [ ] Create project and decision contract with hypotheses and thresholds.
- [ ] Add questions and branching; validation blocks unreachable/invalid logic.
- [ ] Publish; survey version becomes immutable.
- [ ] Pause and close campaign; verify start/submission policy for active sessions.
- [ ] Generate report; reproduce counts from raw test fixtures and document exclusions.

### B. Participant workflow
- [ ] Opportunity card shows language, topic, time, reward, eligibility, study type, and privacy details.
- [ ] Ineligible screen-out follows disclosed policy and does not create a misleading accepted reward.
- [ ] Participant saves progress and resumes without losing valid answers.
- [ ] Double-click/network retry does not duplicate submission.
- [ ] Participant sees status changes and can file a dispute/appeal.

### C. Quality controls
- [ ] Duplicate participation is blocked/flagged consistently.
- [ ] Very fast responses produce a review signal only according to the configured policy, not an unexplained automatic permanent ban.
- [ ] Quality decision captures policy version, reason category, and reviewer.
- [ ] Appeal reversal produces an auditable correction and restores reward eligibility when appropriate.

### D. Reward flow
- [ ] Campaign cannot launch with insufficient authorized budget under configured terms.
- [ ] Accepted completion creates a single reward obligation.
- [ ] Provider timeout leads to retryable failure state without losing the obligation.
- [ ] Replaying the same fulfillment job does not issue a duplicate voucher/top-up.
- [ ] Provider callback is authenticated/validated and idempotent.
- [ ] Reward operator cannot view survey answers by default.
- [ ] Campaign reconciliation accounts for fulfilled, outstanding, cancelled, disputed, and failed rewards.

### E. Privacy/security
- [ ] Cross-tenant object ID tampering returns denied/not found.
- [ ] Participant identity is absent from aggregate report exports.
- [ ] Raw exports require permission, produce an audit event, and use bounded/expiring access.
- [ ] Consent/notice version and relevant preference changes are recorded.
- [ ] Data-rights workflow verifies requester proportionately and applies retention/legal policy.
- [ ] Logs do not include passwords, session tokens, full answer payloads, or reward secrets.
- [ ] No production personal data is used in automated test fixtures.
- [ ] Storage/processor configuration matches the approved data-flow inventory.

### F. RTL and mobile usability
- [ ] Arabic pages have correct reading order, alignment, icons, numbers, and bidirectional text behavior.
- [ ] Main tasks work at 320–375 px viewport width without horizontal overflow.
- [ ] Questions, choices, error messages, and progress indicators are accessible by keyboard and assistive technology.
- [ ] Slow-network state, retry state, and submission confirmation are clear.
- [ ] Critical participant actions do not depend on hover.

## 4. Property and mutation tests

Recommended generated tests:
- Random event sequence for participation/reward state machines; reject invalid transitions.
- Duplicate delivery of every queue event; state remains correct.
- Concurrent quota reservation at/over capacity; accepted count never exceeds cap.
- Random survey trees; publication validator catches invalid branches and preserves valid ones.
- Tenant/role matrix fuzzing for all API endpoints.
- Report aggregation against independent calculations for varied missing-data and exclusion patterns.

Mutation targets: remove tenant filter; remove idempotency check; skip quota transaction; bypass survey version binding; skip reward approval; omit report sampling disclosure; bypass privacy/export permission. The test suite should kill these mutations.

## 5. Release criteria

Release only when:
- All critical acceptance tests pass in CI against the exact commit/revision.
- No known critical/high unresolved security or privacy issue remains.
- Migrations and rollback/recovery steps are documented and tested.
- A restore test has succeeded.
- Reward provider test and reconciliation test pass.
- Legal/hosting/reward go-live checklist is signed off by the designated owners.
- Arabic/mobile smoke test passes on the supported viewport set.
- Operators can pause campaigns, stop rewards when justified, resolve disputes, and respond to incidents.

## 6. Observability

Track operational measurements: API error/latency, queue age, failed fulfillment retries, report generation failures, database saturation, campaign quota drift, duplicate submission blocks, moderation backlog, reward aging, rights-request aging, and unusual export volumes. Avoid placing answers or personal data in metric labels.
