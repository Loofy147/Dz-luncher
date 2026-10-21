# Privacy, Security, and Compliance Design

**Version:** 0.1  
**Status:** Engineering requirements plus legal-review checklist; not legal advice

## 1. Regulatory baseline

The research brief reviewed Law No. 18-07 and Law No. 25-11, published in Algeria's Official Journal on 24 July 2025. The amendment adds, among other elements, provisions for processing-activity registers, automated logs of processing operations, and a personal-data protection delegate in the amended text. The National Authority for Personal Data Protection (ANPDP) describes personal data as information that identifies a person directly or indirectly and explains rights including information, access, correction, and objection.

The original Law 18-07 Article 44 addresses transfers of personal data to a foreign state and states a rule involving prior authorisation from the national authority and adequate protection, subject to the law's exceptions. Law 25-11 added Articles 45 bis 13–14 inside the new Title V bis, which is specifically about processing for prevention/detection of offences, investigations, prosecution, and enforcement of penalties. Those special-purpose transfer provisions must not be presented as a general cross-border transfer permission for an ordinary SaaS platform. Article 7 of Law 25-11 expressly repeals Articles 10 and 11; it does not state that Article 44 is repealed. These points are a reading of the published texts, not a final legal opinion on the consolidated law. Before production collection or foreign hosting, Algerian counsel and/or the ANPDP must confirm the current consolidated interpretation, applicable exceptions, any implementing rules, and the authorisations/notifications that this specific processing requires.

Primary/relevant sources:
- Official Journal, Law No. 25-11 (24 July 2025): https://www.joradp.dz/FTP/JO-FRANCAIS/2025/F2025048.pdf
- ANPDP notice (Arabic): https://plaintes.anpdp.dz/notice_ar.php
- Official Journal, Law No. 18-07 (original law; Articles 44–45): https://www.joradp.dz/FTP/JO-FRANCAIS/2018/F2018034.pdf

## 2. Data categories and default positions

| Category | Examples | Default approach |
|---|---|---|
| Account data | Login identifier, language, account status | Collect minimum; do not expose publicly. |
| Business data | Organization, project description, billing/contact details | Scope to authorized organization members; public fields separately controlled. |
| Participant profile | Wilaya, optional age band, broad interests/category use | Voluntary, specific-purpose, non-sensitive where possible; avoid precise location by default. |
| Survey answers | Preferences, feedback, open text | Separate from identity; pseudonymous linkage; restrict raw access. |
| Reward/fulfillment data | Voucher reference, top-up destination, delivery status | Restrict to reward operators; do not expose to business clients. |
| Product-test data | Protocol steps, required test proof, incident reports | Collect only what is necessary; obtain specific protocol acknowledgement. |
| Technical/security logs | Time, event, actor, request ID, outcome | Avoid logging full answers, tokens, passwords, and unnecessary identifiers. |
| Sensitive data | Health, biometrics, political/religious views, precise location, other high-risk categories | Not collected in MVP without independent necessity, legal review, controls, and approved purpose. |

## 3. Privacy-by-design rules

1. **Purpose definition:** each study states the purpose, controller/contact, data collected, recipients, retention, and applicable notice/consent before collection.
2. **Minimization:** no national ID, contact-book access, or precise GPS for ordinary survey participation by default.
3. **Separation:** participant identity/profile and answers reside in logically separated tables/permissions; reports use pseudonymous/aggregate data by default.
4. **Access restriction:** business users do not receive contact details or identity-level answers unless an explicitly justified and authorized workflow needs them.
5. **Retention:** assign a retention schedule to each data category. Delete or anonymize data when its purpose ends, subject to reviewed legal/accounting obligations.
6. **Rights handling:** provide a discoverable route to request information, access, correction, objection, and deletion where applicable. Verify the requester proportionately without asking for excessive identity documentation.
7. **Consent versioning:** record the notice/consent version, purpose, timestamp, interaction, and choice where consent is required; allow withdrawal where applicable.
8. **Processors and providers:** keep a register of hosting, backups, email/SMS, analytics, payment/reward, support, and AI processors, including location and access.
9. **Exports:** default to aggregate downloads; use expiring links, permission checks, rate limits, and export audit logs.
10. **AI processing:** no raw identifiable responses are sent to a third-party AI provider by default. If added later, document purposes, retention, provider, transfer, and appropriate minimization/review.

## 4. Data-flow map required before production

For every system component, document:

- Data fields collected and why.
- Whether fields are personal data or can be linked to a person.
- Controller/processor role and owner.
- Storage location and backup locations.
- Processors/subprocessors and support access.
- Transfer/remote access path, including analytics, logging, email, support, and AI providers.
- Encryption, authentication, access, retention, and deletion controls.
- Applicable notice/consent or other legal basis.
- Export path to each customer and the smallest data set exposed.

A provider's advertised “region” is insufficient on its own; check logs, backups, support, and subprocessors too.

## 5. Processing register and audit trail

Implement fields needed for a processing-activity register, including:
- Controller and privacy-contact details.
- Processing purpose and legal basis as reviewed by counsel.
- Categories of data subjects and personal data.
- Recipients/processors, including relevant foreign recipients.
- Retention/deletion schedule.
- Technical/organizational safeguards.

Log material events such as collection, modification, consultation/access where required, export, sharing, encryption, deletion, and administrative actions. Logs should record actor, timestamp, object, purpose/reason where relevant, and recipient. Do not make logs themselves a new sensitive-data dump.

## 6. DPIA / high-risk review

Before a study involving sensitive data, children, systematic profiling, extensive monitoring, large-scale linkage, or a new high-risk technology, stop publication until privacy/legal review determines whether a data-protection impact assessment, authority consultation, or additional authorization is required. The platform must support an unresolved compliance blocker rather than let an operator bypass it.

## 7. Security controls

- MFA for privileged/operations accounts; strong session protections.
- Server-side tenant and role authorization on every sensitive read/write.
- Least-privilege provider credentials and secret rotation.
- Encryption in transit and at rest; separate encryption key permissions where practical.
- Secure file upload policy: allowlist types, size limits, malware scanning where feasible, no executable uploads, restricted object access.
- Rate limits and abuse detection for authentication, surveys, exports, and rewards.
- Dependency/container scanning and reproducible release artifacts.
- Backup encryption, restore tests, and documented data-loss objectives.
- Incident runbook with severity, evidence preservation, containment, recovery, and legally reviewed communication steps.
- No production answers in development/test fixtures; use synthetic data.

## 8. Participant fairness and transparency

Before starting, disclose:
- Purpose/topic and who sponsors the study when possible.
- Estimated time and eligibility rules.
- Whether screen-outs are possible and what happens to any reward.
- Reward form/value, approval conditions, expected fulfillment window, expiry where applicable, and dispute process.
- What data is collected, its intended use, and who receives it.
- Whether the activity is an ordinary opinion survey, prototype test, or physical product test.

Do not use deceptive completion timers, hidden reward conditions, or punitive account bans based on a single unreviewed quality signal.

## 9. Legal/compliance go-live checklist

- [ ] Identify the operating entity and controller(s).
- [ ] Get local legal review of current Law 18-07 as amended, notices/consent, processing records, DPO applicability/appointment, rights handling, and incident duties.
- [ ] Review cross-border hosting, backups, remote support, analytics, and subprocessors under the applicable transfer rules before selecting production vendors.
- [ ] Confirm any ANPDP declarations/authorizations/consultations applicable to the intended processing.
- [ ] Confirm business/fiscal treatment of platform revenue and participant rewards.
- [ ] Confirm payment and reward channels are commercially and legally supported; do not implement stored value or cash-out until reviewed.
- [ ] Review terms for product testing, returns, injury/defect complaints, and responsibility allocation.
- [ ] Approve a privacy notice and participant terms in accessible Arabic.
- [ ] Verify access/export/deletion flows and audit logs in a staging test.
- [ ] Complete incident-response tabletop and backup restore test.

## 10. Sources and caution

Legal details can change and application depends on the actual processing activity, parties, and infrastructure. The platform must treat this checklist as a go-live dependency, not a substitute for current legal advice.
