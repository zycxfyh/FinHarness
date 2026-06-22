"""Constants and public literal types for validation."""

from __future__ import annotations

from typing import Literal

from finharness.market_data import ROOT, data_bias_limitation

VALIDATION_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "validations"
VALIDATION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "validations"

ValidationResult = Literal[
    "supported",
    "linked",
    "present",
    "well_formed",
    "weakened",
    "disconfirmed",
    "inconclusive",
    "not_testable",
]

ValidationCheckType = Literal[
    "source_validity",
    "mechanism",
    "event_reaction",
    "benchmark_context",
    "disconfirmation",
    "limitations",
    "backtest",
]

BACKTEST_LIMITATIONS = [
    "MA-crossover historical screen; rung-limited evidence only, not predictive; "
    "costs/slippage only as parameterized; not an execution signal.",
    data_bias_limitation(),
]

BLOCKED_VALIDATION_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\bexecute\b",
    r"\bready to trade\b",
    r"\btrade recommendation\b",
    r"\bvalidated alpha\b",
    r"\bguaranteed\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "执行",
    "已验证alpha",
    "保证",
]
