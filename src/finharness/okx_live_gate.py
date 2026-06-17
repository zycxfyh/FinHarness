"""Fail-closed gate every live OKX mutation must pass through.

Red-team 2026-06-13 found the live write path bypassed the behavioral guard,
ignored persisted trading-state, enforced no notional cap, and wrote no receipt
(findings F1/F3/F4/F5). This module is the single chokepoint that closes those:

    request -> guard (persisted state) -> notional cap -> receipt -> execute
            -> trading-state writeback

`assess_live_order` is a pure decision (no side effects beyond reading state) so
it is fully testable. `execute_live_order` performs the gated mutation: it
always writes a receipt — for blocked attempts too — and on success folds the
placed order back into persisted state.

Nothing here authorizes autonomous trading. The env gate
(FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1) and human attestation still apply; this
gate adds the structural bounds the live path was missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.effective_ceilings import (
    CeilingResolutionError,
    EnforcedCap,
    enforce_request_limit,
)
from finharness.effective_rules import resolve_guard_thresholds
from finharness.market_access_ledger import (
    MarketAccessDecision,
    MarketAccessKey,
    MarketAccessLedgerError,
    MarketAccessLimit,
    evaluate_market_access,
    load_market_access_ledger,
    record_consumption,
)
from finharness.market_data import ROOT, display_path, sha256_text
from finharness.okx_cli import OkxCliError, run_okx_live_mutation_command
from finharness.trading_guard import (
    GuardThresholds,
    TradingState,
    evaluate_trading_state,
)
from finharness.trading_state_store import (
    load_trading_state,
    record_live_order_placed,
)

LIVE_ORDER_RECEIPT_ROOT = ROOT / "data" / "receipts" / "okx-live"

# Conservative human-owned defaults for a single-operator lab. Request values
# may tighten these caps, but cannot raise the effective ceiling.
DEFAULT_MAX_LIVE_NOTIONAL = 50.0
LIVE_NOTIONAL_CEILING_FIELD = "max_live_notional"
LIVE_MARKET_ACCESS_CEILING_FIELD = "live_market_access_window_notional"
DEFAULT_LIVE_MARKET_ACCESS_LIMIT = MarketAccessLimit(
    max_window_notional=50.0,
    max_window_order_count=10,
)


class LiveOrderBlocked(OkxCliError):
    """Raised when the gate refuses a live order. Carries the decision."""

    def __init__(self, decision: LiveGateDecision):
        self.decision = decision
        super().__init__("; ".join(decision.blocking_reasons) or "live order blocked")


@dataclass(frozen=True)
class LiveOrderRequest:
    """A requested live OKX mutation plus the attestation that authorizes it."""

    module: str
    action: str
    args: list[str]
    attester: str  # who authorized this order (F7)
    reason: str  # why (F7)
    has_written_thesis: bool = False
    size: float | None = None
    price: float | None = None
    request_limit: float = DEFAULT_MAX_LIVE_NOTIONAL
    minutes_since_last_trade: int | None = None

    @property
    def max_notional(self) -> float:
        """Backward-compatible alias for the per-request tightening limit."""
        return self.request_limit


@dataclass(frozen=True)
class LiveGateDecision:
    allowed: bool
    guard_level: str
    notional: float | None
    request_limit: float
    enforced_cap: float | None
    configured_ceiling: float | None
    effective_ceiling: float | None
    ceiling_provenance: dict[str, Any] | None = None
    ignored_ceiling_changes: list[str] = field(default_factory=list)
    request_limit_clamped_to_ceiling: bool = False
    cap_invariant_holds: bool = True
    market_access_limit: MarketAccessLimit | None = None
    market_access_cap: EnforcedCap | None = None
    market_access: MarketAccessDecision | None = None
    blocking_reasons: list[str] = field(default_factory=list)
    guard_reasons: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)

    @property
    def max_notional(self) -> float | None:
        """Backward-compatible alias for the actual enforced single-order cap."""
        return self.enforced_cap


def _flag_value(args: list[str], flag: str) -> str | None:
    """Read --flag value or --flag=value from an arg list."""
    for i, token in enumerate(args):
        if token == flag and i + 1 < len(args):
            return args[i + 1]
        if token.startswith(flag + "="):
            return token.split("=", 1)[1]
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def order_notional(request: LiveOrderRequest) -> float | None:
    """Best-effort notional = size * price.

    Falls back to parsing --sz / --px from args. Returns None when it cannot be
    bounded, which the gate treats as fail-closed.
    """
    size = request.size
    if size is None:
        size = _parse_float(_flag_value(request.args, "--sz"))
    price = request.price
    if price is None:
        price = _parse_float(_flag_value(request.args, "--px"))
    if size is None or price is None:
        return None
    return abs(size) * abs(price)


def market_access_key_for_live_order(request: LiveOrderRequest) -> MarketAccessKey:
    symbol = _flag_value(request.args, "--instId") or f"{request.module}:{request.action}"
    return MarketAccessKey(
        environment="live",
        venue="okx",
        operator=request.attester.strip(),
        account="okx_live_default",
        symbol=symbol.upper(),
    )


def assess_live_order(
    request: LiveOrderRequest,
    *,
    state_path: str | Path | None = None,
    thresholds: GuardThresholds | None = None,
    ledger_root: Path | None = None,
    ceiling_rule_root: Path | None = None,
    ceiling_certification_root: Path | None = None,
    market_access_limit: MarketAccessLimit | None = DEFAULT_LIVE_MARKET_ACCESS_LIMIT,
    market_access_state_root: str | Path | None = None,
) -> LiveGateDecision:
    """Decide whether a live order may proceed. No mutation, no execution.

    When thresholds are not supplied, the EFFECTIVE thresholds are resolved from
    the rule-change ledger (B4 enforcement): a promoted lesson that tightened a
    guard threshold actually binds here, with provenance back to the rule change.
    """
    record = load_trading_state(state_path)
    if thresholds is None:
        thresholds, _provenance, _ignored = resolve_guard_thresholds(ledger_root=ledger_root)
    guard = evaluate_trading_state(
        TradingState(
            drawdown_pct=record.drawdown_pct,
            consecutive_losses=record.consecutive_losses,
            minutes_since_last_trade=request.minutes_since_last_trade,
            planned_trade_has_written_thesis=request.has_written_thesis,
        ),
        thresholds,
    )

    blocking: list[str] = []
    request_cap: EnforcedCap | None = None
    market_access_cap: EnforcedCap | None = None
    effective_market_access_limit: MarketAccessLimit | None = None

    try:
        request_cap = enforce_request_limit(
            field=LIVE_NOTIONAL_CEILING_FIELD,
            default_ceiling=DEFAULT_MAX_LIVE_NOTIONAL,
            request_limit=request.request_limit,
            rule_change_root=ceiling_rule_root,
            certification_root=ceiling_certification_root,
        )
    except CeilingResolutionError as exc:
        blocking.append(f"live notional ceiling could not be resolved; refusing fail-closed: {exc}")

    try:
        requested_market_access_notional = (
            market_access_limit.max_window_notional
            if market_access_limit is not None
            else None
        )
        market_access_cap = enforce_request_limit(
            field=LIVE_MARKET_ACCESS_CEILING_FIELD,
            default_ceiling=DEFAULT_LIVE_MARKET_ACCESS_LIMIT.max_window_notional,
            request_limit=requested_market_access_notional,
            rule_change_root=ceiling_rule_root,
            certification_root=ceiling_certification_root,
        )
        requested_order_count = (
            market_access_limit.max_window_order_count
            if market_access_limit is not None
            else DEFAULT_LIVE_MARKET_ACCESS_LIMIT.max_window_order_count
        )
        effective_market_access_limit = MarketAccessLimit(
            max_window_notional=market_access_cap.enforced_cap,
            max_window_order_count=min(
                requested_order_count,
                DEFAULT_LIVE_MARKET_ACCESS_LIMIT.max_window_order_count,
            ),
        )
    except CeilingResolutionError as exc:
        blocking.append(
            "market-access notional ceiling could not be resolved; "
            f"refusing fail-closed: {exc}"
        )

    # F4: the guard now ENFORCES. A non-clear decision blocks the order.
    if not guard.trade_allowed:
        blocking.append(f"behavioral guard {guard.level}: {'; '.join(guard.reasons)}")

    # F5/F6: a persisted reset flag blocks until a human clears it.
    if record.behavior_reset_required:
        blocking.append(
            "trading-state behavior_reset_required is set; a human must clear it "
            f"(reason: {record.behavior_reset_reason})"
        )

    # F3: notional cap. Unbounded (uncomputable) notional fails closed.
    market_access: MarketAccessDecision | None = None
    notional = order_notional(request)
    if notional is None:
        blocking.append(
            "notional could not be bounded (need size and price / --sz and --px); "
            "refusing fail-closed"
        )
    elif request_cap is not None and notional > request_cap.enforced_cap:
        blocking.append(
            f"notional {notional:.4f} exceeds enforced cap {request_cap.enforced_cap:.4f}"
        )
    else:
        try:
            market_access = evaluate_market_access(
                key=market_access_key_for_live_order(request),
                notional=notional,
                limit=effective_market_access_limit,
                ledger=load_market_access_ledger(market_access_state_root),
                limit_evidence=market_access_cap.as_receipt_dict()
                if market_access_cap is not None
                else None,
            )
        except MarketAccessLedgerError as exc:
            market_access = None
            blocking.append(f"market-access ledger unreadable; refusing fail-closed: {exc}")
        else:
            if not market_access.allowed_within_limit:
                blocking.extend(
                    f"market-access ledger: {reason}"
                    for reason in market_access.blocking_reasons
                )

    # F7: attestation must be present.
    if not request.attester.strip():
        blocking.append("missing attester identity")
    if not request.reason.strip():
        blocking.append("missing written reason")

    return LiveGateDecision(
        allowed=not blocking,
        guard_level=guard.level,
        notional=notional,
        request_limit=request.request_limit,
        enforced_cap=request_cap.enforced_cap if request_cap is not None else None,
        configured_ceiling=(
            request_cap.configured_ceiling if request_cap is not None else None
        ),
        effective_ceiling=(
            request_cap.effective_ceiling if request_cap is not None else None
        ),
        ceiling_provenance=(
            request_cap.provenance.as_receipt_dict()
            if request_cap is not None and request_cap.provenance is not None
            else None
        ),
        ignored_ceiling_changes=(
            list(request_cap.ignored) if request_cap is not None else []
        ),
        request_limit_clamped_to_ceiling=(
            request_cap.request_limit_clamped_to_ceiling
            if request_cap is not None
            else False
        ),
        cap_invariant_holds=(
            request_cap.cap_invariant_holds if request_cap is not None else False
        ),
        market_access_limit=effective_market_access_limit,
        market_access_cap=market_access_cap,
        market_access=market_access,
        blocking_reasons=blocking,
        guard_reasons=list(guard.reasons),
        required_actions=list(guard.required_actions),
    )


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _write_receipt(
    *,
    request: LiveOrderRequest,
    decision: LiveGateDecision,
    outcome: str,
    okx_result_ref: str | None,
    market_access_entry_id: str | None,
    error: str | None,
) -> str:
    receipt_id = f"okxlive_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "kind": "okx_live_order_attempt",
        "created_at_utc": _now_utc(),
        "outcome": outcome,  # "executed" | "blocked" | "error"
        "request": {
            "module": request.module,
            "action": request.action,
            # args may carry instId/size/price but never secrets; redaction of
            # the okx *response* is handled by okx_cli. Args are operator input.
            "args": request.args,
            "attester": request.attester,
            "reason": request.reason,
            "has_written_thesis": request.has_written_thesis,
            "request_limit": request.request_limit,
        },
        "decision": {
            "allowed": decision.allowed,
            "guard_level": decision.guard_level,
            "notional": decision.notional,
            "configured_ceiling": decision.configured_ceiling,
            "effective_ceiling": decision.effective_ceiling,
            "ceiling_provenance": decision.ceiling_provenance,
            "ignored_ceiling_changes": decision.ignored_ceiling_changes,
            "request_limit": decision.request_limit,
            "enforced_cap": decision.enforced_cap,
            "request_limit_clamped_to_ceiling": (
                decision.request_limit_clamped_to_ceiling
            ),
            "cap_invariant_holds": decision.cap_invariant_holds,
            "market_access_cap": (
                decision.market_access_cap.as_receipt_dict()
                if decision.market_access_cap is not None
                else None
            ),
            "market_access": decision.market_access.model_dump(mode="json")
            if decision.market_access is not None
            else None,
            "blocking_reasons": decision.blocking_reasons,
            "guard_reasons": decision.guard_reasons,
        },
        "okx_result_ref": okx_result_ref,
        "market_access_entry_id": market_access_entry_id,
        "error": error,
    }
    payload["content_hash"] = sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    path = LIVE_ORDER_RECEIPT_ROOT / f"{receipt_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    return display_path(path)


def execute_live_order(
    request: LiveOrderRequest,
    *,
    state_path: str | Path | None = None,
    thresholds: GuardThresholds | None = None,
    ceiling_rule_root: Path | None = None,
    ceiling_certification_root: Path | None = None,
    market_access_limit: MarketAccessLimit | None = DEFAULT_LIVE_MARKET_ACCESS_LIMIT,
    market_access_state_root: str | Path | None = None,
    market_access_receipt_root: str | Path | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Gate then execute a live OKX mutation.

    Always writes a receipt (including for blocked/errored attempts). Raises
    LiveOrderBlocked when the gate refuses, after recording the blocked receipt.
    On success, folds the placed order into persisted trading-state (F5).
    """
    decision = assess_live_order(
        request,
        state_path=state_path,
        thresholds=thresholds,
        ceiling_rule_root=ceiling_rule_root,
        ceiling_certification_root=ceiling_certification_root,
        market_access_limit=market_access_limit,
        market_access_state_root=market_access_state_root,
    )
    if not decision.allowed:
        _write_receipt(
            request=request,
            decision=decision,
            outcome="blocked",
            okx_result_ref=None,
            market_access_entry_id=None,
            error=None,
        )
        raise LiveOrderBlocked(decision) from None

    try:
        market_access_entry = record_consumption(
            key=market_access_key_for_live_order(request),
            notional=decision.notional,
            limit=decision.market_access_limit,
            limit_evidence=decision.market_access_cap.as_receipt_dict()
            if decision.market_access_cap is not None
            else None,
            source_ref="okx_live_pre_submit",
            state_root=market_access_state_root,
            receipt_root=market_access_receipt_root,
        )
    except MarketAccessLedgerError as exc:
        _write_receipt(
            request=request,
            decision=decision,
            outcome="error",
            okx_result_ref=None,
            market_access_entry_id=None,
            error=f"market-access consumption failed before OKX submit: {exc}",
        )
        raise OkxCliError(str(exc)) from exc

    try:
        result = run_okx_live_mutation_command(
            request.module,
            request.action,
            request.args,
            timeout_seconds=timeout_seconds,
        )
    except OkxCliError as exc:
        _write_receipt(
            request=request,
            decision=decision,
            outcome="error",
            okx_result_ref=None,
            market_access_entry_id=market_access_entry.entry_id,
            error=str(exc),
        )
        raise

    receipt_ref = _write_receipt(
        request=request,
        decision=decision,
        outcome="executed",
        okx_result_ref=None,
        market_access_entry_id=market_access_entry.entry_id,
        error=None,
    )
    # F5: live activity must update the state that bounds behavior.
    record_live_order_placed(receipt_ref=receipt_ref, path=state_path)
    return {
        "receipt_ref": receipt_ref,
        "decision": decision,
        "okx": {"module": result.module, "action": result.action, "data": result.data},
    }
