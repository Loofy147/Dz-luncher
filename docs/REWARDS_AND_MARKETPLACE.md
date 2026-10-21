# Marketplace, Rewards, and Product-Test Operations

**Version:** 0.1

## 1. Operating principles

- The business funds or authorizes the campaign's complete budget before recruiting, through a legally and commercially approved process.
- The participant sees the reward and approval conditions before starting.
- Reward obligations are created from explicit state transitions and reconciled independently from survey-answer analytics.
- Every approved completion should receive the promised reward, except where an explicitly disclosed legitimate exception applies.
- No unrestricted stored-value wallet, peer transfer, cash-out balance, random draw, or gambling-like reward mechanic in MVP.
- Product tests use a separate workflow from ordinary surveys.

## 2. Campaign budget model

Represent the campaign as separate amounts/items:

`Campaign budget = participant rewards + fulfillment costs + platform/service fee + moderation/research costs + contingency approved by the business`

Do not obscure the amount allocated to participants. Campaign launch should fail if the budget is insufficient for the target completions and configured terms. Exact pricing, tax treatment, and reserve methodology are OPEN and must be established by pilot data and professional advice.

The software may track a budget allocation and outstanding obligations; it must not imply that an internal number is a legally segregated escrow account. The real funding and custody flow requires payment/legal review.

## 3. Reward options to investigate

Possible pilot channels, subject to confirmation of lawful availability and partner terms:
- Merchant voucher/coupon.
- Mobile/data top-up.
- Product or service credit.
- Non-transferable reward fulfilled directly by a contracted provider.
- Cash-equivalent payout only after payment, tax, identity, and legal requirements are reviewed.

Do not promise any channel in the UI until it is operational. Do not rely on international survey-site payout conventions without confirming that the flow works for Algerian participants.

## 4. Reward ledger

The ledger is an immutable list of events, not a mutable balance field. Suggested event types:

- `campaign_budget_authorized`
- `completion_reward_created`
- `reward_approved`
- `reward_held_for_review`
- `reward_fulfillment_requested`
- `reward_fulfilled`
- `reward_fulfillment_failed`
- `reward_retried`
- `reward_disputed`
- `reward_reversed_with_reason`
- `campaign_budget_released_or_reconciled`

Each record needs a unique ID, campaign, participant pseudonymous ID, reward item/value, timestamp, actor/source, provider reference, idempotency key, and reason. Never delete a financial/reward event to “fix” it; append a correcting/reversal event.

## 5. Participant reward state machine

`not_earned -> due -> approved -> fulfillment_pending -> fulfilled`

Allowed exceptions:
- `held_for_review`: a quality or eligibility check requires human review.
- `failed_retryable`: provider failed, but the obligation remains due.
- `disputed`: participant has challenged a decision or fulfillment.
- `reversed_with_reason`: only when policy and legal review support a reversal.
- `cancelled_under_policy`: the campaign was cancelled under terms disclosed before participation.

The participant sees a plain-language status. If held/rejected, provide a reason category and review route that does not expose exploitable anti-fraud details. Set a service target for review and fulfillment after actual pilot throughput is measured.

## 6. Anti-fraud and response-quality controls

Use layered controls; a single “fraud score” is not enough.

**Before participation**
- Account throttling and basic duplicate-account heuristics.
- Study-specific eligibility and frequency caps.
- One accepted completion per person/study where required.
- Avoid collecting government identity documents as a general default.

**During participation**
- Signed/session-bound response token and idempotent submission.
- Server-controlled question sequence and branch validation.
- Rate limits and bot/automation signals.
- Monitor response timing and repeated option patterns, without treating fast completion alone as proof.

**After submission**
- Apply documented exclusion rules.
- Compare relevant consistency checks.
- Review outliers, copied text, duplicate patterns, and suspicious multi-account signals where proportionate.
- Route ambiguous cases to manual review.
- Keep the original submission and assessment history so a dispute can be audited.

**Fairness controls**
- Do not quietly change reward conditions after launch.
- Do not penalize participants for unrelated answers or honest negative product feedback.
- Give participants a way to report missing rewards and challenge incorrect decisions.
- Measure the false-positive rate and overturned decisions.

## 7. Marketplace allocation and supply

For each study, match participants only on relevant criteria. Respect campaign quotas, prior participation caps, and category exclusions. Show enough campaign detail for informed choice without exposing private client material or sensitive hypotheses prematurely.

Do not advertise guaranteed response counts or delivery times until pilot evidence establishes them by segment and geography. The system should show whether the target segment is currently recruitable, not imply uniform coverage across Algeria.

## 8. Product and prototype tests

Required fields beyond an ordinary survey:
- Test item/prototype and version.
- Required tasks and duration.
- Who may participate and exclusion criteria.
- Safety/warning information and known limitations.
- Delivery/access method; cost and ownership/return expectations.
- Evidence requested and how it will be used.
- Incident/support contact and complaint route.
- Reward and completion criteria.
- Data and image/video consent, where applicable.

**Initial exclusions:** medical/clinical products, prescription or regulated products, ingestibles, cosmetics, children's products, hazardous goods, and categories with significant safety/liability risk until category-specific legal, safety, and insurance review is complete. Begin with software prototypes, digital services, low-risk usability tests, and non-sensitive local-service concepts.

## 9. Disputes and incidents

- Assign every support case a unique reference and timeline.
- Pause reward finalization if there is a legitimate unresolved dispute, but notify the participant and provide an expected review path.
- Separate quality decisions from reward-provider failure; a provider outage does not erase an accepted reward obligation.
- Escalate safety incidents from a product test to a restricted incident process. Preserve only relevant evidence and do not repurpose incident data for marketing.
- Record resolution, actor, reasoning, any correction, and recurrence-prevention action.

## 10. Marketplace metrics

- Accepted completes per campaign and per source.
- Median/p90 time to fill sample and quota gaps.
- Cost per accepted completion and fulfillment.
- Reward due-to-fulfilled time and failure/retry rates.
- Appeal/complaint rate and overturned decisions.
- Duplicate and quality flags confirmed after review.
- Supply concentration by wilaya/segment and over-recruitment.
- Participant retention, frequency, and satisfaction without incentivizing habitual/compulsive behavior.
