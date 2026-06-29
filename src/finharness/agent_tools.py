"""OpenAI Agents SDK tools for the FinHarness lab."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agents import Agent, FunctionTool, Tool, function_tool
from sqlalchemy.engine import Engine

from finharness.agent_capabilities import (
    AgentCapability,
    get_agent_profile,
    profile_allows_capability,
    tool_names_for_profile,
)
from finharness.agent_context import (
    AgentContextPack,
    build_capital_summary_context,
    build_current_ips_context,
    build_ips_check_context,
    build_open_proposals_context,
    build_proposal_timeline_context,
    unavailable_context_pack,
)
from finharness.config import load_settings
from finharness.data_entry import fetch_quote_snapshot, fetch_yfinance_history
from finharness.metrics import summarize
from finharness.statecore.decision_scaffold import ensure_forcing
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import StateCoreStoreError, open_state_core

ROOT = Path(__file__).resolve().parents[2]
LATEST_RISK_NOTE = ROOT / "data" / "cache" / "latest_risk_note.txt"
DEFAULT_RISK_NOTE = """Not investment advice.

This educational risk note uses yfinance/Yahoo Finance history and not TradingView/TV data.
Historical metrics do not guarantee future returns.

Max drawdown and volatility can change when market regimes, liquidity, or data freshness change.
Transaction costs, slippage, taxes, and venue constraints must be reviewed before any paper
or live use.
"""
AGENT_PROPOSAL_DRAFT_NON_CLAIMS = (
    "Agent-created proposals are review drafts, not recommendations.",
    "Human review is required before any decision of record.",
    "Not execution authorization.",
    "Not investment advice.",
)
AGENT_DRAFT_BLOCKED_KIND_TOKENS = frozenset(
    {
        "execute",
        "execution",
        "order",
        "transfer",
        "trade",
        "broker",
        "action",
        "intent",
    }
)
AGENT_NAME = "Finance Research Harness Agent"
AGENT_BASE_INSTRUCTIONS = (
    "Use profile-selected tools to inspect bounded FinHarness context packs, fetch data, "
    "run backtests, evaluate risk notes, and create only the review objects exposed by "
    "the active profile. "
    "Capital OS context packs are for explanation and review only; they never "
    "authorize actions or execution. "
    "Always state that outputs are for education, not investment advice. "
    "Always disclose that the current default data source is yfinance/Yahoo Finance, "
    "not TradingView/TV, and that optional providers are evidence sources only."
)


@function_tool
def get_quote_snapshot(symbol: str) -> dict[str, object]:
    """Get a quote snapshot through the default available data provider."""
    quote = fetch_quote_snapshot(symbol)
    return quote.__dict__


@function_tool
def get_historical_risk_metrics(symbol: str, start: str, end: str) -> dict[str, object]:
    """Fetch yfinance/Yahoo Finance history and compute core risk metrics."""
    return historical_risk_metrics_payload(symbol=symbol, start=start, end=end)


def historical_risk_metrics_payload(symbol: str, start: str, end: str) -> dict[str, object]:
    """Build the historical risk metrics payload behind the Agents SDK adapter."""
    history = fetch_yfinance_history(symbol, start, end)
    metrics = summarize(history["close"].astype(float).tolist())
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "rows": len(history),
        "data_source": "yfinance/Yahoo Finance, not TradingView/TV",
        "metrics": metrics.__dict__,
    }


@function_tool
def evaluate_latest_risk_note() -> dict[str, object]:
    """Run promptfoo assertions against the latest generated risk note."""
    return evaluate_latest_risk_note_payload()


def evaluate_latest_risk_note_payload(timeout_seconds: float = 60.0) -> dict[str, object]:
    """Run promptfoo assertions with a bounded subprocess timeout."""
    if not LATEST_RISK_NOTE.exists():
        LATEST_RISK_NOTE.parent.mkdir(parents=True, exist_ok=True)
        LATEST_RISK_NOTE.write_text(DEFAULT_RISK_NOTE, encoding="utf-8")

    command = [
        "pnpm",
        "exec",
        "promptfoo",
        "eval",
        "-c",
        "evals/promptfoo/risk-note.yaml",
        "--no-cache",
    ]
    try:
        result = subprocess.run(  # noqa: S603 -- fixed local promptfoo command, shell disabled.
            command,
            cwd=ROOT,
            env={
                **dict(os.environ),
                "PROMPTFOO_DISABLE_TELEMETRY": "1",
                "PROMPTFOO_DISABLE_UPDATE": "1",
            },
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout_tail": str(exc.output or "")[-2000:],
            "stderr_tail": f"promptfoo timed out after {timeout_seconds} seconds",
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def _pack_payload(pack: AgentContextPack) -> dict[str, object]:
    return pack.model_dump(mode="json")


def _with_default_engine(
    name: str,
    builder: Callable[..., AgentContextPack],
    *args: object,
    **kwargs: object,
) -> dict[str, object]:
    try:
        engine = open_state_core()
    except StateCoreStoreError as exc:
        return _pack_payload(unavailable_context_pack(name, str(exc)))
    try:
        pack = builder(engine, *args, **kwargs)
        return _pack_payload(pack)
    finally:
        engine.dispose()


def capital_summary_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_capital_summary_context(engine))
    return _with_default_engine("capital_summary", build_capital_summary_context)


def current_ips_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_current_ips_context(engine))
    return _with_default_engine("current_ips", build_current_ips_context)


def ips_check_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_ips_check_context(engine))
    return _with_default_engine("ips_check", build_ips_check_context)


def open_proposals_context_payload(
    *, limit: int = 10, engine: Engine | None = None
) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_open_proposals_context(engine, limit=limit))
    return _with_default_engine("open_proposals", build_open_proposals_context, limit=limit)


def proposal_timeline_context_payload(
    proposal_id: str,
    *,
    limit: int = 20,
    engine: Engine | None = None,
) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(
            build_proposal_timeline_context(engine, proposal_id=proposal_id, limit=limit)
        )
    return _with_default_engine(
        "proposal_timeline",
        build_proposal_timeline_context,
        proposal_id=proposal_id,
        limit=limit,
    )


def draft_governed_proposal_from_context_payload(
    *,
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    source_refs: list[str],
    reason: str,
    assumptions: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    context_pack_refs: list[str] | None = None,
    profile_name: str = "review-draft",
    engine: Engine | None = None,
    receipt_root: str | Path | None = None,
) -> dict[str, object]:
    """Create an append-only governed proposal draft through the Agent profile gate."""
    _validate_agent_proposal_draft(
        profile_name=profile_name,
        kind=kind,
        claim=claim,
        reason=reason,
        evidence=evidence,
        decision_scaffold=decision_scaffold,
        assumptions=assumptions or {},
        limitations=limitations or {},
        source_refs=source_refs,
    )
    normalized_scaffold = ensure_forcing(decision_scaffold)
    refs = _dedupe_refs([*source_refs, *(context_pack_refs or [])])
    revision_context = {
        "kind": "agent_proposal_draft",
        "profile": profile_name,
        "reason": reason.strip(),
        "context_pack_refs": list(context_pack_refs or []),
        "requires_human_review": True,
        "execution_allowed": False,
    }
    owned_engine = engine is None
    active_engine = engine or open_state_core()
    active_receipt_root = Path(receipt_root or load_settings().receipt_root)
    try:
        write = create_governed_proposal(
            kind=kind.strip(),
            claim=claim.strip(),
            evidence=evidence,
            assumptions=assumptions or {},
            limitations=limitations or {},
            non_claims=list(AGENT_PROPOSAL_DRAFT_NON_CLAIMS),
            source_refs=refs,
            decision_scaffold=normalized_scaffold,
            engine=active_engine,
            receipt_root=active_receipt_root,
            revision_context=revision_context,
        )
    finally:
        if owned_engine:
            active_engine.dispose()
    return {
        "proposal_id": write.proposal.proposal_id,
        "kind": write.proposal.kind,
        "receipt_ref": write.receipt_ref,
        "authority_level": write.proposal.authority_level,
        "requires_human_review": True,
        "execution_allowed": False,
        "non_claims": write.proposal.non_claims,
        "source_refs": write.proposal.source_refs,
    }


def _validate_agent_proposal_draft(
    *,
    profile_name: str,
    kind: str,
    claim: str,
    reason: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    assumptions: dict[str, Any],
    limitations: dict[str, Any],
    source_refs: list[str],
) -> None:
    if not profile_allows_capability(profile_name, AgentCapability.CAPITAL_PROPOSE):
        raise ValueError(f"agent profile {profile_name!r} does not allow capital-propose")
    if not claim.strip():
        raise ValueError("agent proposal draft requires a non-blank claim")
    if not reason.strip():
        raise ValueError("agent proposal draft requires a non-blank reason")
    if not _dedupe_refs(source_refs):
        raise ValueError("agent proposal draft requires at least one source ref")
    kind_text = kind.strip().lower()
    if not kind_text:
        raise ValueError("agent proposal draft requires a non-blank kind")
    if _proposal_kind_tokens(kind_text) & AGENT_DRAFT_BLOCKED_KIND_TOKENS:
        raise ValueError("agent proposal draft kind cannot request execution/order/transfer")
    for name, value in (
        ("evidence", evidence),
        ("decision_scaffold", decision_scaffold),
        ("assumptions", assumptions),
        ("limitations", limitations),
    ):
        if _contains_execution_allowed_true(value):
            raise ValueError(f"{name} cannot set execution_allowed=true")


def _contains_execution_allowed_true(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "execution_allowed" and child is True)
            or _contains_execution_allowed_true(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_execution_allowed_true(child) for child in value)
    return False


def _proposal_kind_tokens(kind: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", kind.lower()) if token}


def _dedupe_refs(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@function_tool
def get_capital_summary_context() -> dict[str, object]:
    """Read the bounded Capital OS exposure context pack."""
    return capital_summary_context_payload()


@function_tool
def get_current_ips_context() -> dict[str, object]:
    """Read the active IPS context pack, if one exists."""
    return current_ips_context_payload()


@function_tool
def get_ips_check_context() -> dict[str, object]:
    """Read the IPS compliance context pack for current exposure."""
    return ips_check_context_payload()


@function_tool
def get_open_proposals_context(limit: int = 10) -> dict[str, object]:
    """Read open governed proposals awaiting human review."""
    return open_proposals_context_payload(limit=limit)


@function_tool
def get_proposal_timeline_context(proposal_id: str, limit: int = 20) -> dict[str, object]:
    """Read a governed proposal's bounded review timeline."""
    return proposal_timeline_context_payload(proposal_id=proposal_id, limit=limit)


# The Agents SDK cannot currently keep strict mode for flexible nested evidence/scaffold
# dicts. The fixed top-level schema is tested; runtime validators govern nested content.
@function_tool(strict_mode=False)
def draft_governed_proposal_from_context(
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    source_refs: list[str],
    reason: str,
    assumptions: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    context_pack_refs: list[str] | None = None,
    profile_name: str = "review-draft",
) -> dict[str, object]:
    """Create a receipt-backed governed proposal draft for human review."""
    return draft_governed_proposal_from_context_payload(
        kind=kind,
        claim=claim,
        evidence=evidence,
        decision_scaffold=decision_scaffold,
        source_refs=source_refs,
        reason=reason,
        assumptions=assumptions,
        limitations=limitations,
        context_pack_refs=context_pack_refs,
        profile_name=profile_name,
    )


AGENT_TOOL_REGISTRY: dict[str, FunctionTool] = {
    tool.name: tool
    for tool in (
        get_quote_snapshot,
        get_historical_risk_metrics,
        evaluate_latest_risk_note,
        get_capital_summary_context,
        get_current_ips_context,
        get_ips_check_context,
        get_open_proposals_context,
        get_proposal_timeline_context,
        draft_governed_proposal_from_context,
    )
}


def agent_tools_for_profile(profile_name: str = "default") -> list[Tool]:
    names = tool_names_for_profile(profile_name)
    missing = [name for name in names if name not in AGENT_TOOL_REGISTRY]
    if missing:
        raise ValueError(
            f"agent profile {profile_name!r} references unregistered tools: "
            f"{', '.join(missing)}"
        )
    return [AGENT_TOOL_REGISTRY[name] for name in names]


def build_finance_research_agent(profile_name: str = "default") -> Agent:
    profile = get_agent_profile(profile_name)
    instructions = (
        f"{AGENT_BASE_INSTRUCTIONS} "
        f"Active capability profile: {profile.name}. {profile.description} "
        "Agent capability profiles select visible tools; they do not grant authority. "
        "Execution is not allowed."
    )
    return Agent(
        name=AGENT_NAME,
        instructions=instructions,
        tools=agent_tools_for_profile(profile.name),
    )


finance_research_agent = build_finance_research_agent()


def tool_names(profile_name: str = "default") -> list[str]:
    return list(tool_names_for_profile(profile_name))


def describe_agent(profile_name: str = "default") -> str:
    profile = get_agent_profile(profile_name)
    agent = build_finance_research_agent(profile.name)
    return json.dumps(
        {
            "agent": agent.name,
            "profile": profile.model_dump(mode="json"),
            "tools": [tool.name for tool in agent.tools],
        },
        indent=2,
        sort_keys=True,
    )
