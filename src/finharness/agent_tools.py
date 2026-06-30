"""OpenAI Agents SDK tools for the FinHarness lab."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
from finharness.agent_evidence import (
    local_eval_source_ref,
    market_data_source_ref,
    resolve_evidence_providers,
)
from finharness.config import load_settings
from finharness.data_entry import fetch_quote_snapshot, fetch_yfinance_history
from finharness.metrics import summarize
from finharness.statecore.decision_scaffold import ensure_forcing
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import (
    StateCoreStoreError,
    open_state_core,
    state_core_db_path,
)

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
AGENT_TOOL_ENTRY_NON_CLAIMS = (
    "Agent tool entries describe runtime visibility; they do not grant authority.",
    "Tool availability is diagnostic metadata, not approval.",
    "Not execution authorization.",
    "Not investment advice.",
)
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

AgentToolSideEffect = Literal["read", "local_eval", "append_only_review_write"]
AgentToolset = Literal["market_data", "eval", "capital_context", "proposal_draft"]
AgentToolUnavailablePolicy = Literal["hide", "diagnostic_stub", "fail_closed"]
AgentToolHandler = Callable[[dict[str, Any]], dict[str, object]]


@dataclass(frozen=True)
class AgentToolAvailability:
    """Cheap runtime availability result for a declared Agent tool."""

    available: bool
    reason: str | None = None

    def model(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AgentToolEntry:
    """Hermes-style metadata wrapper around an Agents SDK tool."""

    name: str
    tool: FunctionTool
    capability: AgentCapability
    toolset: AgentToolset
    description: str
    side_effect: AgentToolSideEffect
    check_fn: Callable[[], AgentToolAvailability]
    dispatch_handler: AgentToolHandler
    evidence_provider_ids: tuple[str, ...] = ()
    unavailable_policy: AgentToolUnavailablePolicy = "hide"
    max_result_chars: int = 12_000
    requires_human_review: bool = False
    execution_allowed: bool = False
    authority_transition: bool = False
    non_claims: tuple[str, ...] = AGENT_TOOL_ENTRY_NON_CLAIMS

    def __post_init__(self) -> None:
        if self.name != self.tool.name:
            raise ValueError(f"agent tool entry name mismatch: {self.name} != {self.tool.name}")
        if self.execution_allowed:
            raise ValueError("agent tool entries never grant execution authority")
        if self.authority_transition:
            raise ValueError("agent tool entries never grant authority transitions")
        resolve_evidence_providers(self.evidence_provider_ids)

    def metadata(self) -> dict[str, object]:
        availability = self.check_fn()
        return {
            "name": self.name,
            "capability": self.capability.value,
            "toolset": self.toolset,
            "description": self.description,
            "side_effect": self.side_effect,
            "availability": availability.model(),
            "evidence_provider_ids": list(self.evidence_provider_ids),
            "unavailable_policy": self.unavailable_policy,
            "max_result_chars": self.max_result_chars,
            "requires_human_review": self.requires_human_review,
            "execution_allowed": False,
            "authority_transition": False,
            "non_claims": list(self.non_claims),
        }


def _available() -> AgentToolAvailability:
    return AgentToolAvailability(True)


def _state_core_path_available() -> AgentToolAvailability:
    path = state_core_db_path(load_settings().state_core_db_path)
    if path.exists():
        return AgentToolAvailability(True)
    return AgentToolAvailability(False, f"state-core sqlite file missing: {path}")


def _promptfoo_available() -> AgentToolAvailability:
    if shutil.which("pnpm") is None:
        return AgentToolAvailability(False, "pnpm is not available on PATH")
    return AgentToolAvailability(True)


def _call_payload(handler: Callable[..., dict[str, object]]) -> AgentToolHandler:
    def call(arguments: dict[str, Any]) -> dict[str, object]:
        return handler(**arguments)

    return call


@function_tool
def get_quote_snapshot(symbol: str) -> dict[str, object]:
    """Get a quote snapshot through the default available data provider."""
    return get_quote_snapshot_payload(symbol=symbol)


def get_quote_snapshot_payload(symbol: str) -> dict[str, object]:
    """Build the quote snapshot payload behind the Agents SDK adapter."""
    quote = fetch_quote_snapshot(symbol)
    payload = quote.__dict__.copy()
    payload["source_refs"] = [
        market_data_source_ref(
            provider=quote.provider,
            dataset="quote",
            symbol=quote.symbol,
        )
    ]
    payload["non_claims"] = [
        "Quote snapshots are descriptive market data, not investment advice.",
        "Not execution authorization.",
    ]
    return payload


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
        "source_refs": [
            market_data_source_ref(
                provider="yfinance",
                dataset="history",
                symbol=symbol,
                qualifier=f"start={start}&end={end}",
            )
        ],
        "non_claims": [
            "Historical metrics are descriptive and do not predict future returns.",
            "Not investment advice.",
            "Not execution authorization.",
        ],
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
            "source_refs": [
                local_eval_source_ref("evals/promptfoo/risk-note.yaml"),
                "cache://latest_risk_note",
            ],
            "data_gaps": [f"promptfoo timed out after {timeout_seconds} seconds"],
            "non_claims": [
                "Local eval evidence is diagnostic; it does not prove correctness.",
                "Not execution authorization.",
            ],
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "source_refs": [
            local_eval_source_ref("evals/promptfoo/risk-note.yaml"),
            "cache://latest_risk_note",
        ],
        "non_claims": [
            "Local eval evidence is diagnostic; it does not prove correctness.",
            "Not execution authorization.",
        ],
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
        "receipt_refs": [write.receipt_ref],
        "context_pack_refs": list(context_pack_refs or []),
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


AGENT_TOOL_ENTRIES: dict[str, AgentToolEntry] = {
    entry.name: entry
    for entry in (
        AgentToolEntry(
            name=get_quote_snapshot.name,
            tool=get_quote_snapshot,
            capability=AgentCapability.CAPITAL_READ,
            toolset="market_data",
            description="Read one quote snapshot through the configured market-data adapter.",
            side_effect="read",
            check_fn=_available,
            dispatch_handler=_call_payload(get_quote_snapshot_payload),
            evidence_provider_ids=("market_data.yfinance",),
        ),
        AgentToolEntry(
            name=get_historical_risk_metrics.name,
            tool=get_historical_risk_metrics,
            capability=AgentCapability.CAPITAL_READ,
            toolset="market_data",
            description="Fetch historical prices and compute descriptive risk metrics.",
            side_effect="read",
            check_fn=_available,
            dispatch_handler=_call_payload(historical_risk_metrics_payload),
            evidence_provider_ids=("market_data.yfinance",),
        ),
        AgentToolEntry(
            name=evaluate_latest_risk_note.name,
            tool=evaluate_latest_risk_note,
            capability=AgentCapability.CAPITAL_EXPLAIN,
            toolset="eval",
            description="Run local promptfoo assertions against the latest generated risk note.",
            side_effect="local_eval",
            check_fn=_promptfoo_available,
            dispatch_handler=_call_payload(evaluate_latest_risk_note_payload),
            evidence_provider_ids=("local_eval.promptfoo",),
            unavailable_policy="hide",
        ),
        AgentToolEntry(
            name=get_capital_summary_context.name,
            tool=get_capital_summary_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the bounded Capital OS exposure context pack.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(capital_summary_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_current_ips_context.name,
            tool=get_current_ips_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the active IPS context pack when one exists.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(current_ips_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_ips_check_context.name,
            tool=get_ips_check_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the IPS compliance context pack for current exposure.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(ips_check_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_open_proposals_context.name,
            tool=get_open_proposals_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read open governed proposals awaiting human review.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(open_proposals_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_proposal_timeline_context.name,
            tool=get_proposal_timeline_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read a governed proposal's bounded review timeline.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(proposal_timeline_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=draft_governed_proposal_from_context.name,
            tool=draft_governed_proposal_from_context,
            capability=AgentCapability.CAPITAL_PROPOSE,
            toolset="proposal_draft",
            description="Create an append-only governed proposal draft for human review.",
            side_effect="append_only_review_write",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(draft_governed_proposal_from_context_payload),
            evidence_provider_ids=(
                "capital_context.state_core",
                "proposal_receipt.state_core",
            ),
            unavailable_policy="fail_closed",
            requires_human_review=True,
        ),
    )
}
AGENT_TOOL_REGISTRY: dict[str, FunctionTool] = {
    name: entry.tool for name, entry in AGENT_TOOL_ENTRIES.items()
}


def agent_tool_entries_for_profile(profile_name: str = "default") -> list[AgentToolEntry]:
    names = tool_names_for_profile(profile_name)
    missing = [name for name in names if name not in AGENT_TOOL_ENTRIES]
    if missing:
        raise ValueError(
            f"agent profile {profile_name!r} references unregistered tools: "
            f"{', '.join(missing)}"
        )
    return [AGENT_TOOL_ENTRIES[name] for name in names]


def agent_tool_metadata_for_profile(profile_name: str = "default") -> list[dict[str, object]]:
    return [entry.metadata() for entry in agent_tool_entries_for_profile(profile_name)]


def agent_tools_for_profile(profile_name: str = "default") -> list[Tool]:
    from finharness.agent_runtime import resolve_agent_tool_entries

    return [
        resolved.entry.tool
        for resolved in resolve_agent_tool_entries(profile_name)
        if resolved.model_visible
    ]


def _static_agent_tools_for_profile(profile_name: str = "default") -> list[Tool]:
    return [entry.tool for entry in agent_tool_entries_for_profile(profile_name)]


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


finance_research_agent = Agent(
    name=AGENT_NAME,
    instructions=(
        f"{AGENT_BASE_INSTRUCTIONS} "
        "Active capability profile: default. "
        "Agent capability profiles select visible tools; they do not grant authority. "
        "Execution is not allowed."
    ),
    tools=_static_agent_tools_for_profile("default"),
)


def tool_names(profile_name: str = "default") -> list[str]:
    return list(tool_names_for_profile(profile_name))


def describe_agent(profile_name: str = "default") -> str:
    from finharness.agent_runtime import agent_runtime_view

    profile = get_agent_profile(profile_name)
    agent = build_finance_research_agent(profile.name)
    runtime_view = agent_runtime_view(profile.name)
    return json.dumps(
        {
            "agent": agent.name,
            "profile": profile.model_dump(mode="json"),
            "tools": [tool.name for tool in agent.tools],
            "tool_entries": agent_tool_metadata_for_profile(profile.name),
            **runtime_view,
        },
        indent=2,
        sort_keys=True,
    )
