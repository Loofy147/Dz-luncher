# Validation Engine — Reference Implementation Record

**Version:** 0.1  
**Date:** 20 October 2026  
**Status:** Reference core implemented and tested; not integrated into a deployed application.

## 1. What is implemented

The standalone, standard-library Python core provides:

- Strict JSON-like survey and response contract parsing; unknown fields are rejected.
- Survey definition validation, stable ASCII question/option IDs, numeric bounds, and forward-only branching.
- Arabic-Indic/Eastern Arabic-Indic digit normalization, Arabic decimal/thousands separators, and conservative text normalization.
- Required-answer and hidden-branch validation; screen-out is distinct from invalidity and response-quality assessment.
- Immutable version binding on each response; a response with a different `survey_version_id` is invalid.
- Timing, straightlining, attention-check, text, duplicate-text, and shared-device signals.
- Group-based review policy: a single evidence group produces an accepted-with-flag outcome; two or more distinct groups create a manual-review hold. Multiple text signals contribute one text group.
- Deterministic batch deduplication by `submission_id`; conflicting payloads under the same ID fail closed.
- Accepted-response quota accounting in a batch; quota questions must be required and always visible.
- HMAC pseudonyms scoped to `project_id`; default business row exports omit direct identifiers and free text.
- Evidence-labelled reports containing stable sample-flow counts, minimum sample rules, Wilson intervals, and explicit convenience-sample limitations.

## 2. Contracts and public functions

- `survey_from_dict(payload)` — parse and validate the versioned survey contract.
- `response_from_dict(payload)` — parse a response transport object.
- `validate_survey(survey)` — validate a survey definition before publication.
- `validate_response(survey, response)` — validate one response, branching and screening included.
- `process_responses(survey, responses, secret, policy)` — deterministic batch quality/quota processing.
- `analysis_records(rows, survey, secret)` — pseudonymous business row export; free text is omitted by default.
- `build_report(rows, survey, hypotheses)` — aggregate report with flow counts and evidence limitations.

See the standalone `survey-engine-hardening` artifact for implementation, tests, a runnable demo, and JSON examples. The contract is transport-neutral and does not select a web framework or database.

## 3. Frozen policy choices pending pilot

| Decision | Current rule | Reason / caveat |
|---|---|---|
| Quality score | Count independent review groups rather than repeat occurrences | Prevents repeated manifestations of one underlying signal from inflating the score. |
| Attention check | One failed attention check is a soft signal, not a hold by itself | False-positive risk must be measured with human-labelled pilot cases. |
| Short text | A short answer such as `لا` is not low-effort solely because of length | Short Arabic answers can be legitimate. |
| Shared device | Missing device ID yields no signal; a shared device is contextual evidence only | Shared household devices are legitimate; no permanent ban is triggered. |
| Quotas | Only accepted/accepted-flagged batch outcomes consume configured cells | Production concurrency requires transactional reservations, not this in-memory loop. |
| Export | Pseudonymous row export omits free text and direct identifiers by default | Free text may contain identifying data; this core is not a semantic PII detector. |
| Evidence labels | Answers submitted in a survey are treated as declared/reported evidence | The reporting API rejects observed/transactional evidence claims without separate provenance. |
| Versioning | Each response names the exact survey version | Avoids aggregating answers against an instrument that differs from the one shown to the respondent. |

## 4. Verification result

- ✅ 36 unit/contract tests passed using Python's built-in `unittest` runner.
- ✅ Python compilation passed for the core, demo, and test module.
- ✅ JSON survey example round-tripped through `survey_from_dict`.
- ✅ JSON response example parsed and validated against the matching immutable version.
- ✅ Synthetic demo completed with 15 generated submissions: 3 screen-outs, 3 accepted, 7 accepted with one soft flag, 2 holds, and no invalid, duplicate, or quota-full outcomes in that particular fixture.
- ✅ Quota invariant test: 30 eligible synthetic responses against a cap of 5 produced exactly 5 accepted and 25 quota-full outcomes.

All demo data are synthetic. These checks establish implementation behavior under the tested cases; they do not establish real Algerian respondent fraud rates, representativeness, product demand, or legal compliance.

## 5. Production blockers not covered by the reference core

- Database persistence, migrations, tenant/role authorization, and immutable published survey storage.
- Concurrent quota reservations and accepted-completion uniqueness protected by database constraints/transactions.
- Authentication, participant profile controls, consent/notice, data-rights workflows, retention/deletion, and processing registers.
- Reward obligation/ledger, external fulfillment provider, disputes, appeals, and transaction reconciliation.
- Web/API integration, Arabic RTL/mobile interface, save/resume, rate limits, operational metrics, backup/restore, and incident runbooks.
- Legal review of data-controller/processor roles, hosting jurisdiction, international transfers, and the permitted reward/payment model.

## 6. Next engineering gate

1. Implement a transactional persistence adapter with unique constraints for `(survey_version_id, participant_id)` and `submission_id` idempotency.
2. Reserve quota cells transactionally and create accepted participation plus reward obligation atomically using an outbox or equivalent durable pattern.
3. Add API authorization/tenant isolation tests before connecting the business workspace.
4. Build the RTL form runner against the JSON contract and test 320–375 px viewports, branching, retry, and submission confirmation.
5. Run a manually adjudicated pilot before calibrating quality policy or claiming recruitment economics.
