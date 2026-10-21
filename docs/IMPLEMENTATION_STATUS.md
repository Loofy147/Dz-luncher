# Implementation Status — 2026-10-21

## Implemented in this MVP foundation

- Arabic-first RTL server-rendered web app with FastAPI/Jinja, registration/login, database-backed sessions and CSRF protection.
- Email verification and password-reset flows: purpose-bound random tokens stored as SHA-256 digests, 24-hour verification and 30-minute recovery expiry, one-time consumption, resend cooldown, privacy-preserving generic recovery responses, password-reset session revocation, audit events, and SMTP TLS configuration gates.
- Database-backed fixed-window rate limits protect registration (5/hour), login (10/15 minutes), password recovery (5/hour), verification resends (3/hour), password reset (10/15 minutes), email-token verification (20/15 minutes), and survey-response POSTs (60/hour per source, 10/hour per participant+campaign). PostgreSQL and SQLite counters use atomic upserts; only HMAC fingerprints are stored, and blocked responses include Retry-After. Forwarded client IP headers are ignored unless the immediate peer belongs to an explicitly configured RATE_LIMIT_TRUSTED_PROXY_CIDRS network. Survey-start, export, reward, and webhook limits remain open.
- Authenticated privacy-request intake for access/correction/deletion/objection/other; requesters can view only their own records. Admin-only status triage supports audited state transitions, mandatory resolution notes for terminal decisions, and keeps free-text request detail out of audit metadata. Completion is an operator assertion, not an automatic erasure action.
- Admin-only human review queue for responses held by quality signals, with a one-decision record, reason code, reviewer note, and minimal audit metadata. Acceptance is transactional with quota/campaign-cap rechecks and reward reservation; rejected holds remain distinguishable in reports without a destructive or misleading database status rewrite.
- Participant response history and single-appeal flow for a human-rejected response, plus a separate admin second-level adjudication queue. Appeal overturning preserves the original rejection record, rechecks limits/quotas/funding, reserves a reward atomically when due, and updates sample flow; upholding leaves the response excluded and does not create a reward.
- Private in-app notification inbox with per-user access isolation, durable read state, and internal-only targets. Submission, review decision, appeal submission/resolution, and externally reconciled reward payout add event notifications inside their database transactions; external email notification for these events remains unconfigured.
- SQLAlchemy domain model: users with email-verification state, sessions, purpose-bound one-time auth tokens, campaigns, immutable published versions, responses, reward obligations, double-entry-style ledger deltas, and audit events.
- Survey contract supporting single-choice, scale, numeric, and optional text questions; conditional display, screening, quotas, response-quality signals, duplicate submissions, and idempotency.
- Nine complete Arabic-first study templates are available in the business builder and template API; choosing a template prefills an unsaved form, and an explicit save creates a private draft without publishing it.
- Hypothesis validation rejects nonexistent choice values, incompatible numeric types, out-of-range values, unsupported free-text mappings, and malformed thresholds/sample minimums instead of silently reporting zero positive responses.
- Fieldwork operations playbook and study-template catalog cover decision framing, recruitment/sample flow, participant comprehension, reviewer rubric, reward reconciliation, and release gates.
- Declared-evidence report with sample flow, segment minimums, interval labels, explicit sampling caveats, and no false upgrade to observed behavior or transactional proof.
- Reward funding requirement before publishing a rewarded campaign; accepted-response obligations, idempotent reservation and manually reconciled payment state.
- Operator CLI for pending reward obligations, externally verified funding records, and externally completed payout records.
- SQLite local adapter with write serialization for deterministic local/pilot tests; PostgreSQL selected for production.
- Alembic initial migration; CI tests, lint, and Python compilation checks.

## Explicitly not complete

- No integrated payment rail, banking link, automatic payout, escrow service, or financial licence determination.
- Enterprise SSO, email/push delivery for event notifications, role invitations, and managed retention/deletion scheduler remain open. Privacy-request intake and audited operator triage exist, but they do not perform automatic account/data deletion or legal determinations.
- No real Algerian participant pilot; quality weights and false-positive/false-negative rates are not calibrated against human-labelled data.
- No independent security review, penetration test, general load test, PostgreSQL campaign/reward race test, or tested backup restoration. PostgreSQL rate-counter concurrency is exercised in CI.
- No legal conclusion on hosting jurisdiction, cross-border transfers, or campaign-specific lawful basis. These remain go-live gates.

## Release gates

Do not collect sensitive or unnecessary data. Do not market declared preferences as proven demand. Do not state that a reward was paid unless an external payment has actually completed and its reference has been checked. Configure independent production secrets, PostgreSQL, TLS, trusted proxy handling, application-wide rate limits (survey starts, exports, rewards and webhook ingress remain uncovered), logs/alerts, backups, and a privacy review before launch.
