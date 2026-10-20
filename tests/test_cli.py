from __future__ import annotations

from scripts.manage_rewards import build_parser


def test_reward_cli_requires_operator_and_external_reference_for_funding():
    parser = build_parser()
    args = parser.parse_args([
        "fund", "--survey", "survey-1", "--amount-dzd", "2500",
        "--reference", "verified-receipt", "--idempotency-key", "fund-001", "--operator", "finance operator",
    ])
    assert args.command == "fund"
    assert args.amount_dzd == 2500
    assert args.operator == "finance operator"


def test_reward_cli_accepts_only_explicit_mark_paid_reference():
    parser = build_parser()
    args = parser.parse_args([
        "mark-paid", "--obligation", "reward-1", "--reference", "external-transfer-1", "--operator", "ops",
    ])
    assert args.command == "mark-paid"
    assert args.reference == "external-transfer-1"
