# Arabic-first survey validation core — hardening slice

A standard-library Python implementation of the MVP's validation engine. It is intentionally a core module, not a deployed web application.

## Capabilities

- Survey schema checks: unique stable IDs, valid option IDs, numeric bounds, forward-only branch references, screening rules, and quota definitions.
- Response validation: Arabic-Indic/Eastern Arabic-Indic digits, Arabic decimal/thousands separators, numeric limits, required fields, hidden-branch enforcement, and separate screening outcomes.
- Quality signals: timing, straightlining, attention-check failures, low-effort text, repeated long text, and observed shared devices. Each signal contributes at most one review group; one soft group is not enough to hold a response.
- Immutable-version binding: every response must identify the exact survey version it answers.
- Batch idempotency: exact retries with the same submission ID are deduplicated; conflicting payloads with the same ID fail closed.
- Batch quotas: only accepted responses consume quota cells. In production, concurrent quota reservations must also use a database transaction and uniqueness/locking strategy.
- Privacy: HMAC pseudonyms scoped to the business project, and default business exports omit account/device/submission identifiers and free text.
- Evidence reports: stable sample-flow counts, minimum sample rules, Wilson intervals, evidence-scope qualifications, and explicit warnings about convenience-sample bias. Survey answers are always treated as declared/reported evidence; observed-behavior and transaction claims require separate provenance not implemented in this slice.

## Run

```bash
python -m unittest discover -s tests -v
python demo.py
```

`contracts/survey-example.json` and `contracts/response-example.json` demonstrate the transport shape accepted by `survey_from_dict` and `response_from_dict`. No third-party packages are required. Tested with CPython in this environment.

## Status semantics

- `invalid`: response does not satisfy survey/data contract.
- `screened_out`: valid screen-out, not a quality verdict.
- `excluded_duplicate`: participant already submitted a valid attempt for this survey batch.
- `hold`: at least two distinct quality evidence groups; requires human review.
- `quota_full`: otherwise valid response cannot occupy a full configured quota cell.
- `accepted_flagged`: accepted, with one soft evidence group for visibility/review.
- `accepted`: accepted without quality signals.

No soft signal alone causes an irreversible ban or automatic reward forfeiture. Reward eligibility and dispute review must be implemented as separate persisted workflow states.

## Security and production boundaries

1. `pseudonym_secret` is a secret key. The demo string is **not** a production secret; inject a generated key from an approved secret manager.
2. Pseudonymization is not anonymization. Treat participant IDs and the identity mapping as protected data.
3. Free-text export is off by default because responses can contain identifying information. This module does not perform semantic PII detection.
4. The batch engine cannot prevent concurrent requests in a distributed deployment from racing on quota or accepted-completion counts. Enforce uniqueness and quota changes transactionally in the persistence layer.
5. Persistence, authentication, role/tenant authorization, consent/notice, data retention/deletion, reward ledger, payment integrations, appeals, and the Arabic RTL web UI are not implemented in this slice.
6. Synthetic fixtures verify code behavior only; they do not estimate real respondent fraud, representativeness, or Algerian market demand.

## Evidence interpretation

A `supported` label means a predeclared threshold was met under the specified interval/minimum-N rule. For `declared` evidence, the report explicitly states that this is **not demand validation**. Convenience samples and Wilson intervals do not correct self-selection or coverage bias.
