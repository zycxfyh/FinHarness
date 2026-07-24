"""Shared reject-mode redline scanners for governance boundaries.

This module captures the reusable pattern behind existing redaction / blocklist
code: recursively walk structured payloads and scan text surfaces. Unlike OKX
redaction, these helpers reject by raising ``ValueError``; they do not mask and
continue. The vocabulary is deliberately domain-specific to research evidence
boundaries, but the scanner is generic enough for future governed outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ADVICE_EXECUTION_PATTERNS: tuple[str, ...] = (
    r"target[\s_-]?price",
    r"price[\s_-]?target",
    r"target[\s_-]?weights?",
    r"order[\s_-]?size",
    r"position[\s_-]?size",
    r"confidence[\s_-]?to[\s_-]?profit",
    r"buy",
    r"sell",
    r"recommend\w*",
    r"execut\w*",
    r"leverage",
    r"margin",
    r"transfer[\s_-]?funds?",
    r"建议|推荐|买入|卖出|下单|执行交易|目标价|目标仓位|仓位大小|杠杆|保证金|转账|转入资金|资金转移",
    r"購入|売却|買う|売る|推奨|注文|目標価格|レバレッジ|証拠金|送金",
)

PREDICTION_PATTERNS: tuple[str, ...] = (
    r"expected[\s_-]?return",
    r"predicted[\s_-]?return",
    r"forecast",
)

STRUCTURED_ADVICE_KEYS: frozenset[str] = frozenset(
    {
        "buy",
        "confidence_to_profit",
        "execute",
        "execution_allowed",
        "execution_plan",
        "forecast",
        "order_quantity",
        "order_size",
        "predicted_return",
        "price_target",
        "quantity",
        "recommendation",
        "recommendations",
        "sell",
        "target_allocation",
        "target_price",
        "target_weight",
        "target_weights",
        "expected_return",
        "position_size",
        "return_forecast",
    }
)


@dataclass(frozen=True)
class Redline:
    """A named regex redline used for user/provider-visible text."""

    name: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RedlineFinding:
    """A concrete redline hit inside a text or structured payload."""

    path: str
    matched: str
    surface: str


def compile_redline(name: str, patterns: tuple[str, ...]) -> Redline:
    """Compile word-ish redline patterns.

    Boundaries treat underscores and dashes as separators, so both
    ``target_price`` and ``target-price`` are caught, while words such as
    ``buyback`` or ``selloff`` do not match the plain buy/sell tokens.
    """

    joined = "|".join(patterns)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9])(?:{joined})(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return Redline(name=name, pattern=pattern)


NARROW_RESEARCH_REDLINE = compile_redline(
    "advice/execution",
    ADVICE_EXECUTION_PATTERNS,
)
FULL_RESEARCH_REDLINE = compile_redline(
    "advice/execution/prediction",
    ADVICE_EXECUTION_PATTERNS + PREDICTION_PATTERNS,
)


def find_text_redline(text: str, redline: Redline, *, path: str = "$") -> RedlineFinding | None:
    """Return the first redline match in text, if any."""

    match = redline.pattern.search(text)
    if match is None:
        return None
    return RedlineFinding(path=path, matched=match.group(0), surface=redline.name)


def find_nested_redlines(
    value: Any,
    redline: Redline,
    *,
    forbidden_keys: frozenset[str] = frozenset(),
    path: str = "$",
) -> tuple[RedlineFinding, ...]:
    """Recursively scan dict/list payloads for forbidden keys and string values."""

    findings: list[RedlineFinding] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}"
            normalized = key_text.lower()
            if normalized in forbidden_keys:
                findings.append(
                    RedlineFinding(path=key_path, matched=key_text, surface="forbidden key")
                )
            key_finding = find_text_redline(key_text, redline, path=key_path)
            if key_finding is not None:
                findings.append(key_finding)
            findings.extend(
                find_nested_redlines(
                    nested,
                    redline,
                    forbidden_keys=forbidden_keys,
                    path=key_path,
                )
            )
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            findings.extend(
                find_nested_redlines(
                    item,
                    redline,
                    forbidden_keys=forbidden_keys,
                    path=f"{path}[{index}]",
                )
            )
    elif isinstance(value, str):
        finding = find_text_redline(value, redline, path=path)
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def reject_text(text: str, redline: Redline, *, surface: str) -> str:
    """Reject one text field if it carries a redline hit."""

    finding = find_text_redline(text, redline)
    if finding is not None:
        raise ValueError(
            f"{surface} carries forbidden {finding.surface} language: "
            f"{finding.matched!r}"
        )
    return text


def reject_text_sequence(
    texts: tuple[str, ...],
    redline: Redline,
    *,
    surface: str,
) -> tuple[str, ...]:
    """Reject any text in a tuple if it carries a redline hit."""

    for index, text in enumerate(texts):
        finding = find_text_redline(text, redline, path=f"$[{index}]")
        if finding is not None:
            raise ValueError(
                f"{surface} carries forbidden {finding.surface} language at "
                f"{finding.path}: {finding.matched!r}"
            )
    return texts


def reject_nested(
    value: dict[str, Any],
    redline: Redline,
    *,
    forbidden_keys: frozenset[str],
    surface: str,
) -> dict[str, Any]:
    """Reject a structured dict if any nested key or string value trips a redline."""

    findings = find_nested_redlines(value, redline, forbidden_keys=forbidden_keys)
    if findings:
        first = findings[0]
        raise ValueError(
            f"{surface} carries forbidden {first.surface} language at "
            f"{first.path}: {first.matched!r}"
        )
    return value
