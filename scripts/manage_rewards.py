"""Offline operator commands for reward ledger reconciliation.

This CLI records externally verified funding and payouts. It does not move money.
Only run `fund` after funds have actually been received and verified, and only run
`mark-paid` after an external payout has actually completed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import select

from app.db import make_engine, make_session_factory
from app.models import RewardObligation, SurveyCampaign
from app.services import ServiceError, fund_campaign, mark_reward_paid


def _factory():
    engine = make_engine()
    return engine, make_session_factory(engine)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manually reconcile externally verified Dz-luncher rewards.")
    sub = parser.add_subparsers(dest="command", required=True)

    pending = sub.add_parser("pending", help="List pending reward obligations")
    pending.add_argument("--survey", help="Optional campaign slug or ID")
    pending.add_argument("--limit", type=int, default=100)

    funding = sub.add_parser("fund", help="Record funding already received and verified")
    funding.add_argument("--survey", required=True, help="Campaign slug or ID")
    funding.add_argument("--amount-dzd", type=int, required=True)
    funding.add_argument("--reference", required=True, help="External receipt or bank reference")
    funding.add_argument("--idempotency-key", required=True, help="Stable, unique key for this funding entry")
    funding.add_argument("--operator", required=True, help="Human operator name/role for audit trail")

    paid = sub.add_parser("mark-paid", help="Record a payout that has already completed externally")
    paid.add_argument("--obligation", required=True, help="Reward obligation ID")
    paid.add_argument("--reference", required=True, help="External transfer/payment proof reference")
    paid.add_argument("--operator", required=True, help="Human operator name/role for audit trail")
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.getenv("APP_ENV", "development").lower() == "production" and not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    engine, factory = _factory()
    try:
        if args.command == "pending":
            if not 1 <= args.limit <= 1000:
                print("--limit must be between 1 and 1000", file=sys.stderr)
                return 2
            with factory() as session:
                query = select(RewardObligation, SurveyCampaign).join(
                    SurveyCampaign, SurveyCampaign.id == RewardObligation.survey_id
                ).where(RewardObligation.status == "pending")
                if args.survey:
                    query = query.where((SurveyCampaign.slug == args.survey) | (SurveyCampaign.id == args.survey))
                query = query.order_by(RewardObligation.created_at.asc()).limit(args.limit)
                rows = session.execute(query).all()
                data = [{
                    "obligation_id": obligation.id,
                    "survey": campaign.slug,
                    "survey_title": campaign.title,
                    "participant_id": obligation.participant_id,
                    "amount_dzd": obligation.amount_dzd,
                    "created_at": obligation.created_at.isoformat(),
                } for obligation, campaign in rows]
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "fund":
            if not args.operator.strip():
                print("--operator cannot be blank", file=sys.stderr)
                return 2
            # The command records verified funding; it cannot verify a real-world receipt itself.
            result = fund_campaign(
                factory, slug_or_id=args.survey, amount_dzd=args.amount_dzd,
                reference=args.reference, idempotency_key=args.idempotency_key,
                operator_label=args.operator,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "mark-paid":
            if not args.operator.strip():
                print("--operator cannot be blank", file=sys.stderr)
                return 2
            result = mark_reward_paid(
                factory, obligation_id=args.obligation, reference=args.reference,
                operator_label=args.operator,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        return 2
    except ServiceError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
