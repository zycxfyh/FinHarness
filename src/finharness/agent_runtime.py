"""Hermes-style runtime resolution and dispatch for FinHarness Agent tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from finharness.agent_capabilities import get_agent_profile, tool_names_for_profile
from finharness.agent_context_projection import (
    context_projection_view,
    project_agent_context_result,
)
from finharness.agent_evidence import (
    AgentEvidenceEnvelope,
    build_agent_evidence_envelope,
    evidence_provider_metadata_for_ids,
)
from finharness.agent_tools import (
    AGENT_TOOL_ENTRIES,
    AgentToolAvailability,
    AgentToolEntry,
    AgentToolSideEffect,
)
from finharness.statecore.store import StateCoreStoreError

AgentToolRuntimeErrorCode = Literal[
    "PROFILE_NOT_ALLOWED",
    "TOOL_UNREGISTERED",
    "TOOL_UNAVAILABLE",
    "SCHEMA_VALIDATION_FAILED",
    "RESULT_TOO_LARGE",
    "STATECORE_UNAVAILABLE",
    "RECEIPT_WRITE_FAILED",
    "EXECUTION_UNSUPPORTED",
    "HANDLER_FAILED",
]


@dataclass(frozen=True)
class AgentToolRuntimeError:
    code: AgentToolRuntimeErrorCode
    message: str
    recoverable: bool
    reason: str | None = None
    execution_allowed: bool = False
    authority_transition: bool = False

    def model(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "reason": self.reason,
            "execution_allowed": False,
            "authority_transition": False,
        }


@dataclass(frozen=True)
class AgentToolRuntimeResult:
    ok: bool
    tool_name: str
    side_effect: AgentToolSideEffect | None
    result: dict[str, object] | None = None
    evidence: AgentEvidenceEnvelope | None = None
    error: AgentToolRuntimeError | None = None
    truncated: bool = False
    original_result_chars: int | None = None
    execution_allowed: bool = False
    authority_transition: bool = False

    def model(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "side_effect": self.side_effect,
            "result": self.result,
            "evidence": self.evidence.model() if self.evidence else None,
            "error": self.error.model() if self.error else None,
            "truncated": self.truncated,
            "original_result_chars": self.original_result_chars,
            "execution_allowed": False,
            "authority_transition": False,
        }


@dataclass(frozen=True)
class ResolvedAgentToolEntry:
    entry: AgentToolEntry
    availability: AgentToolAvailability
    model_visible: bool
    hidden_reason: str | None = None
    degraded: bool = False

    def model(self) -> dict[str, object]:
        return {
            "name": self.entry.name,
            "capability": self.entry.capability.value,
            "toolset": self.entry.toolset,
            "side_effect": self.entry.side_effect,
            "evidence_provider_ids": list(self.entry.evidence_provider_ids),
            "evidence_providers": evidence_provider_metadata_for_ids(
                self.entry.evidence_provider_ids
            ),
            "availability": self.availability.model(),
            "model_visible": self.model_visible,
            "hidden_reason": self.hidden_reason,
            "degraded": self.degraded,
            "requires_human_review": self.entry.requires_human_review,
            "execution_allowed": False,
            "authority_transition": False,
        }


PROFILE_BOUND_TOOL_NAMES = frozenset(
    {
        "get_capital_context_projection",
        "draft_governed_proposal_from_context",
    }
)


def resolve_agent_tool_entries(profile_name: str = "default") -> list[ResolvedAgentToolEntry]:
    profile = get_agent_profile(profile_name)
    resolved: list[ResolvedAgentToolEntry] = []
    for name in profile.tool_names:
        entry = AGENT_TOOL_ENTRIES.get(name)
        if entry is None:
            raise ValueError(
                f"agent profile {profile.name!r} references unregistered tools: {name}"
            )
        availability = entry.check_fn()
        if availability.available:
            resolved.append(
                ResolvedAgentToolEntry(
                    entry=entry,
                    availability=availability,
                    model_visible=True,
                )
            )
            continue
        if entry.unavailable_policy == "diagnostic_stub":
            resolved.append(
                ResolvedAgentToolEntry(
                    entry=entry,
                    availability=availability,
                    model_visible=True,
                    hidden_reason=availability.reason,
                    degraded=True,
                )
            )
        else:
            resolved.append(
                ResolvedAgentToolEntry(
                    entry=entry,
                    availability=availability,
                    model_visible=False,
                    hidden_reason=availability.reason,
                    degraded=False,
                )
            )
    return resolved


def agent_runtime_view(profile_name: str = "default") -> dict[str, object]:
    resolved = resolve_agent_tool_entries(profile_name)
    visible = [item for item in resolved if item.model_visible]
    hidden = [item for item in resolved if not item.model_visible]
    unavailable = [item for item in resolved if not item.availability.available]
    return {
        "resolved_tools": [item.model() for item in visible],
        "hidden_tools": [item.model() for item in hidden],
        "unavailable_tools": [item.model() for item in unavailable],
        "runtime_rules": {
            "availability_affects_model_visibility": True,
            "diagnostic_stub_tools_remain_model_visible": True,
            "dispatch_results_are_structured": True,
            "context_projection_is_profile_budgeted": True,
            "execution_allowed": False,
            "authority_transition": False,
        },
        "context_projection": context_projection_view(profile_name),
    }


def dispatch_agent_tool(
    *,
    profile_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> AgentToolRuntimeResult:
    entry = AGENT_TOOL_ENTRIES.get(tool_name)
    if entry is None:
        return _error_result(
            tool_name=tool_name,
            side_effect=None,
            code="TOOL_UNREGISTERED",
            message=f"agent tool is not registered: {tool_name}",
            recoverable=False,
        )

    try:
        profile_tool_names = set(tool_names_for_profile(profile_name))
    except ValueError as exc:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="PROFILE_NOT_ALLOWED",
            message=str(exc),
            recoverable=False,
        )
    if tool_name not in profile_tool_names:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="PROFILE_NOT_ALLOWED",
            message=f"agent profile {profile_name!r} cannot dispatch tool {tool_name!r}",
            recoverable=False,
        )

    availability = entry.check_fn()
    if not availability.available:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="TOOL_UNAVAILABLE",
            message=f"agent tool is unavailable: {tool_name}",
            recoverable=entry.unavailable_policy != "fail_closed",
            reason=availability.reason,
        )

    missing = _missing_required_arguments(entry, arguments)
    if missing:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="SCHEMA_VALIDATION_FAILED",
            message=f"missing required arguments: {', '.join(missing)}",
            recoverable=True,
        )

    runtime_arguments = dict(arguments)
    if tool_name in PROFILE_BOUND_TOOL_NAMES:
        requested_profile = runtime_arguments.pop("profile_name", None)
        if requested_profile is not None and str(requested_profile) != profile_name:
            return _error_result(
                tool_name=tool_name,
                side_effect=entry.side_effect,
                code="PROFILE_NOT_ALLOWED",
                message=(
                    "agent tool profile is selected by the active runtime "
                    f"profile {profile_name!r}, not by tool arguments"
                ),
                recoverable=False,
            )
        runtime_arguments["profile_name"] = profile_name

    try:
        result = entry.dispatch_handler(runtime_arguments)
    except StateCoreStoreError as exc:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="STATECORE_UNAVAILABLE",
            message="state-core is unavailable for this Agent tool",
            recoverable=True,
            reason=str(exc),
        )
    except ValueError as exc:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            recoverable=True,
        )
    except OSError as exc:
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="HANDLER_FAILED",
            message="agent tool handler failed",
            recoverable=True,
            reason=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive normalization.
        return _error_result(
            tool_name=tool_name,
            side_effect=entry.side_effect,
            code="HANDLER_FAILED",
            message="agent tool handler failed",
            recoverable=False,
            reason=str(exc),
        )

    return _success_result(profile_name=profile_name, entry=entry, result=result)


def _missing_required_arguments(
    entry: AgentToolEntry,
    arguments: dict[str, Any],
) -> list[str]:
    schema = entry.tool.params_json_schema
    required = schema.get("required", [])
    if not isinstance(required, list):
        return []
    return [
        str(name)
        for name in required
        if str(name) not in arguments or arguments[str(name)] is None
    ]


def _success_result(
    *,
    profile_name: str,
    entry: AgentToolEntry,
    result: dict[str, object],
) -> AgentToolRuntimeResult:
    result = project_agent_context_result(
        profile_name=profile_name,
        tool_name=entry.name,
        result=result,
    )
    evidence = build_agent_evidence_envelope(
        provider_ids=entry.evidence_provider_ids,
        result=result,
    )
    encoded = json.dumps(result, sort_keys=True, default=str)
    if len(encoded) <= entry.max_result_chars:
        return AgentToolRuntimeResult(
            ok=True,
            tool_name=entry.name,
            side_effect=entry.side_effect,
            result=result,
            evidence=evidence,
            truncated=False,
            execution_allowed=False,
            authority_transition=False,
        )
    preview = encoded[: entry.max_result_chars]
    return AgentToolRuntimeResult(
        ok=True,
        tool_name=entry.name,
        side_effect=entry.side_effect,
        result={
            "preview": preview,
            "truncated": True,
            "original_result_chars": len(encoded),
        },
        evidence=evidence,
        error=AgentToolRuntimeError(
            code="RESULT_TOO_LARGE",
            message="agent tool result exceeded its runtime result budget",
            recoverable=True,
        ),
        truncated=True,
        original_result_chars=len(encoded),
        execution_allowed=False,
        authority_transition=False,
    )


def _error_result(
    *,
    tool_name: str,
    side_effect: AgentToolSideEffect | None,
    code: AgentToolRuntimeErrorCode,
    message: str,
    recoverable: bool,
    reason: str | None = None,
) -> AgentToolRuntimeResult:
    return AgentToolRuntimeResult(
        ok=False,
        tool_name=tool_name,
        side_effect=side_effect,
        result=None,
        error=AgentToolRuntimeError(
            code=code,
            message=message,
            recoverable=recoverable,
            reason=reason,
            execution_allowed=False,
            authority_transition=False,
        ),
        execution_allowed=False,
        authority_transition=False,
    )
