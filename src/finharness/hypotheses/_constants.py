"""Constants and literal types for hypothesis processing."""

from __future__ import annotations

from typing import Literal

from finharness.market_data import ROOT

HYPOTHESIS_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "hypotheses"
HYPOTHESIS_RECEIPT_ROOT = ROOT / "data" / "receipts" / "hypotheses"

HypothesisStatus = Literal["draft", "ready_for_validation", "failed_quality"]
ConfidencePrior = Literal["low", "medium", "high", "unknown"]

RECOMMENDATION_PATTERNS = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\boverweight\b",
    r"\bunderweight\b",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\btake profit\b",
    r"\bstop loss\b",
    r"\bposition sizing\b",
    r"\bplace order\b",
    r"\bexecute\b",
    r"\btrade recommendation\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "加仓",
    "减仓",
    "开仓",
    "平仓",
    "目标价",
    "止损",
    "止盈",
    "仓位",
    "下单",
    "执行",
]

VALIDATED_PATTERNS = [
    r"\bvalidated\b",
    r"\bproven\b",
    r"\bconfirmed alpha\b",
    r"\bguaranteed\b",
    "已经验证",
    "已经证明",
    "确定",
    "保证",
]

HERMES_DRAFT_ROOT = ROOT / "data" / "cache" / "hermes-drafts"
HERMES_DRAFT_PROMPT_VERSION = "finharness.hypotheses.hermes_prompt.v1"
ALLOWED_DRAFT_CHECK_TYPES = frozenset(
    {
        "market_reaction",
        "indicator_context",
        "event_follow_up",
        "basket_comparison",
        "human_review",
    }
)
