"""Constants and public literal types for risk gate."""

from __future__ import annotations

from typing import Literal

from finharness.market_data import ROOT

RISK_GATE_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "risk-gates"
RISK_GATE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "risk-gates"

RiskGateDecisionValue = Literal[
    "approved_for_paper_review",
    "blocked",
    "needs_more_evidence",
    "needs_human_review",
    "rejected",
]

RiskGateCheckStatus = Literal["passed", "failed", "warning", "not_applicable"]

BLOCKED_RISK_GATE_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\border\b",
    r"\bexecute\b",
    r"\blive execution\b",
    r"\bquantity\b",
    r"\bleverage\b",
    r"\bstop loss\b",
    r"\btake profit\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "执行",
    "杠杆",
]
