# Dz-luncher Go-Live Remediation Plan

**Research date:** 2026-10-20  
**Status:** Engineering plan; legal and provider decisions remain open  
**Scope:** Move the MVP toward a scoped Algerian pilot without confusing passing tests with production readiness.

## 1. Decisions

1. **Do not collect live participant data yet.** Use synthetic data only until the operating entity, processing obligations, hosting/data flows, notice and required ANPDP steps have been reviewed.
2. **Prefer Algerian-hosted infrastructure for the first pilot.** Djezzy Cloud advertises data centres in Algeria, but its location, backup, support-access and subprocessor claims must be confirmed contractually.
3. **Separate campaign payment collection from participant reward fulfilment.** Chargily Pay is a candidate for receiving B2B campaign payments after merchant onboarding; it is not yet approved for participant payouts or escrow for Dz-luncher.
4. **Start with no-cash rewards or directly fulfilled vouchers/top-ups under a written partner arrangement.** Do not launch a stored-value wallet, transferable balance, cash-out balance or self-managed escrow.
5. **Run a controlled, human-labelled pilot.** Synthetic tests can verify code behaviour; real, consented fieldwork is needed to test recruitment, response quality, rewards and business value.

## 2. Evidence and legal interpretation

Labels: **ESTABLISHED** = stated by a primary source; **INFERENCE** = engineering implication; **OPEN** = must be confirmed for the actual entity, processing and contracts.

### 2.1 Personal data and Law 18-07 as amended by Law 25-11

- **ESTABLISHED:** Law No. 25-11 was published in the Official Journal on 24 July 2025 and amends Law No. 18-07. It inserts provisions on a personal-data protection delegate and registers/carnets for processing activities and operations. Primary source: [Official Journal n°48, Law 25-11](https://www.joradp.dz/FTP/JO-FRANCAIS/2025/F2025048.pdf). The ANPDP's current notice identifies Law 18-07 as amended by Law 25-11 and describes information, access, correction and objection rights: [ANPDP privacy notice](https://plaintes.anpdp.dz/notice.php).
- **ESTABLISHED:** Original Law 18-07 Article 44 says personal data may be transferred to a foreign state only with authorisation from the national authority and if the destination provides sufficient protection, subject to the exceptions in Article 45. Primary source: [Official Journal n°34, Law 18-07, pp. 18–19](https://www.joradp.dz/FTP/JO-FRANCAIS/2018/F2018034.pdf).
- **IMPORTANT SCOPE NOTE:** Law 25-11 adds Articles 45 bis 13–14 inside a new Title V bis for processing performed for prevention/detection of offences, investigations, prosecutions and enforcement. Do not treat that special-purpose chapter as a general SaaS cross-border-transfer permission. Law 25-11 Article 7 repeals Articles 10 and 11, not Article 44. A lawyer and/or ANPDP must confirm the current consolidated interpretation and any implementing rules for our proposed processing.
- **INFERENCE:** A pseudonymous answer remains personal data if it can be linked to a participant or reasonably identify them. Pseudonymisation reduces exposure; it does not by itself close the legal question.
- **OPEN:** Whether each planned operation requires a declaration, prior authorisation, consultation, a named privacy delegate or other specific step; which legal basis applies; whether foreign transfer permission is available; and which rights/retention duties apply to each data category.

**Solution / acceptance criteria**
- Obtain a short written Algerian legal review against the consolidated text, explicitly covering Law 18-07 as amended by Law 25-11, Articles 32/34/35/36, 38/39, 43/44/45, the introduced Articles 41 bis and 41 bis 2–3, and applicable implementing rules.
- Prepare a processing-activity register covering controller/contact, purpose and reviewed legal basis, data subjects/categories, recipients/processors and countries, retention/deletion period, and safeguards.
- Prepare an operation log/carnet with actor, time, object, action and purpose where appropriate. Do not log full answers, passwords, session tokens, API keys or raw webhook bodies.
- Identify the privacy contact and comply with delegate provisions where legally required. Consult ANPDP using its published channel where counsel advises: [ANPDP notice/contact](https://plaintes.anpdp.dz/notice.php).
- Publish Arabic participant notices and terms before fieldwork: purpose, sponsor where discloseable, fields, recipients, storage/transfer, retention, rights/contact, rewards, screening and appeal route.
- Add participant access/correction/objection and reviewed deletion/export workflows. Delete or anonymise eligible data while preserving only evidence legally required for audit/accounting.
- Start without health, biometric, political, religious, precise-location, children’s, government-ID, contact-book or other unnecessary high-risk data.

### 2.2 E-commerce classification and website requirements

- **ESTABLISHED:** The Ministry of Commerce's explanation of Law No. 18-05 says e-commerce activity is subject to applicable commercial registration, a site/page hosted in Algeria with a .com.dz extension, site authentication, and visible/readable offers including identity/contact/registration details, price/taxes, terms, payment, data protection, cancellation and complaint procedures. Source: [Ministry of Commerce — Law 18-05](https://www.commerce.gov.dz/fr/actualites/la-loi-relative-au-commerce-electronique-fixant-les-regles-generales-du-commerce-electronique-des-biens-et-des-services).
- **OPEN:** Whether each Dz-luncher workflow (B2B SaaS subscription, campaign funding, optional participant reward) falls within the definition and each requirement.
- **Solution:** Have counsel determine commercial registration, tax treatment, .com.dz, hosting location, terms, invoices, refunds and consumer-facing display requirements before taking money. Do not assume an ordinary .com deployment is sufficient.

### 2.3 Hosting and data-flow control

- **ESTABLISHED as a provider claim, not an independent audit:** [Djezzy Cloud](https://djezzycloud.dz/english) advertises an Algerian sovereign cloud, data centres in Algeria, compute/storage and Kubernetes services, and claims alignment with local data-protection requirements.
- **INFERENCE:** Local hosting is the best first candidate to investigate because it can reduce transfer and e-commerce-hosting uncertainty. It does not settle everything: managed backups, remote support, CDN, email/SMS, error reporting, analytics, repositories and AI tools may still receive data abroad.
- **Solution:** Request the provider's service description and contract: exact primary/backup locations, remote administrator/support access, subprocessors, encryption/key ownership, incident SLA, backup retention/deletion, data export, restore commitments, security attestations and exit process. Confirm support for this app plus PostgreSQL.
- **Deployment shape:** Containerised FastAPI service and PostgreSQL in the approved hosting environment; private DB networking; TLS; least-privilege DB user; encrypted backups; no public DB port. Keep test/dev data synthetic. Avoid third-party analytics and AI processing of raw answers at launch.
- **Do not use Vercel or another foreign-region service for participant data by default.** Reconsider only after location/subprocessor review and a written determination of transfer requirements. A provider's advertised region alone is not enough.

**Acceptance tests**
- Document the full path for every field: browser → application → database → logs → backups → exports → provider/support access.
- Restore a database backup into an isolated environment and verify access restrictions.
- Demonstrate deletion/retention, audit trails, encryption-in-transit/at-rest, key rotation, incident response and access revocation.
- Verify production rejects unsafe defaults such as development secrets, SQLite, debug mode or missing required configuration.

### 2.4 Campaign payments and participant rewards

- **ESTABLISHED:** The Bank of Algeria lists Regulation No. 25-02 of 14 April 2025 governing authorisation and operation of payment service providers (PSPs): [Bank of Algeria regulatory page](https://www.bank-of-algeria.dz/importations-exportations-reglement/) and [official Regulation 25-02 PDF](https://www.bank-of-algeria.dz/stoodroa/2025/05/REG.N%25C2%25B025-02.FR_.pdf).
- **ESTABLISHED:** Chargily Pay documents CIB/EDAHABIA acceptance, test/live modes, checkout creation/retrieval, webhooks and HMAC signatures: [Developer introduction](https://dev.chargily.com/pay-v2/introduction), [checkout create API](https://dev.chargily.com/pay-v2/api-reference/checkouts/create), [checkout retrieve API](https://dev.chargily.com/pay-v2/api-reference/checkouts/retrieve), [webhook security](https://dev.chargily.com/pay-v2/webhooks).
- **ESTABLISHED:** Chargily's merchant terms describe local card collection, merchant onboarding/verification, DZD transactions and commercial-site requirements. The published terms are dated 1 July 2024; current eligibility and price must be reconfirmed: [merchant terms](https://chargily.com/dz/business/pay/term), [current pricing page](https://chargily.com/dz/business/pay/pricing).
- **OPEN:** Whether our operating entity and research/SaaS business model are accepted; whether any balance/payout facility permits the intended participant reward flow; and current prices, settlement, reserve/hold, refund, dispute, tax and API limits.
- **Decision:** Investigate Chargily first as a campaign-payment collection adapter, not as an assumed participant cash-payout or escrow provider. Obtain written answers before coding live mode.
- **Lowest-risk pilot:** zero-cash rewards or a directly fulfilled voucher/product/top-up under a written partner arrangement. Show no reward option in the interface until operationally supported.
- **Accounting:** keep the reward ledger as an obligation/reconciliation record, not as a stored-value wallet. Never label an internal number as cleared funds. Never mark a reward fulfilled until external proof is checked.

**If gateway integration is approved**
1. The server calculates the order amount from stored campaign pricing; never trust a browser-supplied amount.
2. The server creates a checkout in test mode and stores a local pending-payment record with an idempotency key and provider ID.
3. The webhook endpoint validates the provider's HMAC signature against the exact raw request body using an out-of-repository secret.
4. Persist event/provider IDs under unique constraints; process duplicates safely. Reconcile event type, payment status, expected DZD amount, order and test/live mode.
5. For ambiguous states, retrieve the checkout server-to-server. A browser success redirect is not proof of payment.
6. Only then post the ledger event and allow a funded campaign transition. Reconcile provider records daily; test refunds and disputes.
7. Test bad signatures, duplicate/out-of-order events, delayed events, wrong amounts/currencies, replay and timeouts before live mode.

### 2.5 Authentication, application security and operations

The project's current implementation notes identify these gaps: email verification/password reset; privileged MFA; team invitations; moderation/appeal console; data-subject requests and deletion scheduler; PostgreSQL race tests; independent security review; load tests; and proven backup restoration. See [Implementation Status](IMPLEMENTATION_STATUS.md).

**Solution and acceptance tests**
- **Implemented in the current branch:** database-backed fixed-window limits for registration (5/hour), login (10/15 minutes), password recovery (5/hour), verification resends (3/hour), password reset (10/15 minutes), and verification-token submission (20/15 minutes). PostgreSQL/SQLite counters use atomic upserts; persisted identifiers are HMAC fingerprints, not raw IP addresses. The TCP peer is used by default. Configure RATE_LIMIT_TRUSTED_CLIENT_IP_HEADER as x-real-ip or cf-connecting-ip only when the trusted ingress overwrites the selected header. These limits do not replace edge WAF/DDoS controls.
- **Still open:** rate limits for survey start/submit, exports, rewards and webhook ingress; the proxy-header configuration must be verified against the actual deployment ingress before fieldwork.
- Require email verification before business campaigns can be published; implement one-use, expiring password-reset tokens; revoke sessions after credential/security changes.
- Require MFA for administrators/reward operators; enforce role/tenant checks on every sensitive action; audit privileged reads and exports.
- Establish dependency/container scanning and security regression tests. Use [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) as the application test baseline and [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final) for secure-development process. NIST's SP 800-218 Rev. 1 page still described version 1.2 as an initial public draft in December 2025, so do not treat that draft as a final normative standard: [SSDF 1.2 draft](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd).
- Run concurrency tests against PostgreSQL (not only SQLite) for response limits, quota reservations, duplicate submissions, reward creation and idempotency.
- Preliminary pilot operations targets (hypotheses to validate): recovery-point objective ≤24 hours, recovery-time objective ≤8 hours, successful restore before live fieldwork, zero critical security findings and 100% reward/payment reconciliation.

### 2.6 Response quality, fairness and evidence validity

- Treat automated checks as signals, not proof of fraud. Duplicate accepted submissions and hard eligibility contradictions may be deterministically rejected; duration, straight-lining and attention checks should normally create review reasons rather than irreversible bans or automatic reward forfeiture.
- Freeze the quality-policy version for the first pilot. Human-label samples of held and accepted responses against a prewritten rubric, record reviewer disagreement, appeals and false-positive reversals.
- Reports must show sample flow, recruitment source, field dates, quotas, exclusions, segment counts and interval interpretation. Suppress small cells that could identify a participant.
- Distinguish declared attitudes/intention from observed action, completed purchase or market demand. A lawful behavioural test (e.g. genuine offer or pre-order) is a separate project gate.
- Pilot design: 2–3 local business campaigns and small cohorts of adult volunteers. Around 30–50 accepted responses per campaign is an initial operational exercise, **not** a statistically representative Algerian sample. Measure recruitment cost/time, start-to-completion funnel, technical failure rate, quality-review precision proxy, appeals/reversals, reward delivery time, the business decision changed, and report actionability.
- Stop fieldwork on a privacy/security incident, undisclosed reward failure, unreconciled funds or evidence that sampling/quality rules systematically exclude legitimate participants.

### 2.7 CI, migrations and release integrity

- CI runs Ruff, tests and compilation on Python 3.12/3.13. The last observed remote CI run failed at Ruff lint before tests could start. Unused imports in app/security.py and app/services.py and one unused local in tests/test_validation_core.py were removed on the feature branch; the new commit must complete both matrix jobs before PR #1 is considered green.
- Add a PostgreSQL CI service job to exercise the production database dialect, migrations and concurrent writes. SQLite convenience tests do not prove PostgreSQL race safety.
- Run Alembic upgrade against an empty PostgreSQL database and an upgrade from the previous schema. Do not rely on create_all as a production migration strategy.
- Keep the PR draft until tests, clean history, source-tree review and release gates are satisfactory. The temporary bootstrap workflow's success verified archive integrity/extraction only; it was not application CI.

## 3. Prioritised action register

| Priority | Action | Input required | Evidence to close |
|---|---|---|---|
| P0 | Clear CI and review final diff | Engineering | Both Python matrix jobs green; migration/tests exercised |
| P0 | Legal memo for current data law, e-commerce status, notices and transfer rules | Algerian counsel; ANPDP as advised | Written applicability/authorisation checklist; no unresolved legal blocker |
| P0 | Verify domestic hosting and complete data flows | Engineering + selected provider | Contract and completed data-flow/register; locations, backups and support clarified |
| P0 | Establish operating entity, commercial/fiscal requirements and customer terms | Founder + accountant/counsel | Registration, invoice and terms pathway confirmed |
| P1 | Confirm gateway eligibility and economics | Chargily + legal/finance | Written merchant onboarding, fees/settlement/refunds/limits and explicit payment scope |
| P1 | Select non-cash reward fulfillment channel | Contracted voucher/top-up/product partner | Partner terms, unit cost, delivery evidence, failure and dispute process |
| P1 | Implement recovery, verification, MFA and request/retention workflows | Engineering | Expiry/replay/revocation, access boundary, retention and deletion tests |
| P1 | PostgreSQL reliability/security tests | Engineering/independent reviewer | Race tests, backup restore, threat model, dependency scan and critical findings addressed |
| P2 | Human-labelled participant pilot | Research operator + businesses | Frozen protocol/data snapshot, sample-flow report, reviewer disagreement, appeals and reconciliation |
| P2 | Go-live decision | Founder + legal + engineering | P0/P1 gates passed; explicit approval and runbook signed off |

## 4. Go/no-go rule

**GO** only for a scoped pilot with an approved host/data flow, confirmed legal/commercial steps, provider secrets kept out of source control, audited payment/reward states and a functioning privacy/support/incident route.

**NO-GO** if foreign-transfer requirements are unresolved while participant data would be transferred; the host cannot substantiate locations/access/subprocessors; funds would be held outside an approved flow; rewards cannot be fulfilled and reconciled; or critical CI/security/restore tests fail.

A green CI suite is necessary but does not establish compliance, representativeness, security assurance, profitability or public-launch readiness.
