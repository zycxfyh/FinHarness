"""Constants and literal types for proposal processing."""

from __future__ import annotations

from typing import Literal

from finharness.market_data import ROOT

PROPOSAL_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "proposals"
PROPOSAL_RECEIPT_ROOT = ROOT / "data" / "receipts" / "proposals"
STRUCTURAL_READY_RESULTS = {"linked", "present", "well_formed"}

ActionType = Literal[
    "watch_only",
    "research_more",
    "paper_trade_candidate",
    "avoid_or_reject",
]

ProposalStatus = Literal[
    "draft_for_risk_review",
    "needs_more_research",
    "rejected_before_risk",
]

BLOCKED_PROPOSAL_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\bapproved\b",
    r"\bauthorized\b",
    r"\bquantity\b",
    r"\bleverage\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "批准",
    "授权",
    "杠杆",
]
