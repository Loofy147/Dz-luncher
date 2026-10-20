# Implementation Status — 2026-10-20

## Implemented in this MVP foundation

- Arabic-first RTL server-rendered web app with FastAPI/Jinja, registration/login, database-backed sessions and CSRF protection.
- SQLAlchemy domain model: users, sessions, campaigns, immutable published versions, responses, reward obligations, double-entry-style ledger deltas, and audit events.
- Survey contract supporting single-choice, scale, numeric, and optional text questions; conditional display, screening, quotas, response-quality signals, duplicate submissions, and idempotency.
- Declared-evidence report with sample flow, segment minimums, interval labels, explicit sampling caveats, and no false upgrade to observed behavior or transactional proof.
- Reward funding requirement before publishing a rewarded campaign; accepted-response obligations, idempotent reservation and manually reconciled payment state.
- Operator CLI for pending reward obligations, externally verified funding records, and externally completed payout records.
- SQLite local adapter with write serialization for deterministic local/pilot tests; PostgreSQL selected for production.
- Alembic initial migration; CI tests, lint, and Python compilation checks.

## Explicitly not complete

- No integrated payment rail, banking link, automatic payout, escrow service, or financial licence determination.
- No email verification/password reset, enterprise SSO, role invitations, moderation console, appeal workflow, data-subject request workflows, or managed retention/deletion scheduler.
- No real Algerian participant pilot; quality weights and false-positive/false-negative rates are not calibrated against human-labelled data.
- No independent security review, penetration test, load test, PostgreSQL race test in CI, or tested backup restoration.
- No legal conclusion on hosting jurisdiction, cross-border transfers, or campaign-specific lawful basis. These remain go-live gates.

## Release gates

Do not collect sensitive or unnecessary data. Do not market declared preferences as proven demand. Do not state that a reward was paid unless an external payment has actually completed and its reference has been checked. Configure independent production secrets, PostgreSQL, TLS, trusted proxy handling, rate limiting, logs/alerts, backups, and a privacy review before launch.
