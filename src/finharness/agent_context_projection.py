"""Profile-aware Capital context budget and projection for Agent teams.

Hermes treats context as a runtime budget, not an unbounded transcript. This
module applies that pattern to FinHarness L5: each Agent profile gets a stable
projection policy over Capital OS context packs, and runtime dispatch can turn
raw read models into role-appropriate office briefs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import Engine

from finharness.agent_capabilities import get_agent_profile
from finharness.agent_context import (
    CAPITAL_ADMISSION_SUMMARY_KEYS,
    AgentContextPack,
    build_capital_summary_context,
    build_current_ips_context,
    build_ips_check_context,
    build_open_proposals_context,
    build_planning_policy_context,
    unavailable_context_pack,
)
from finharness.statecore.store import StateCoreStoreError, open_state_core

AGENT_CONTEXT_PROJECTION_NON_CLAIMS = (
    "Agent context projections are budgeted read models, not source-of-truth storage.",
    "Projection priority expands usable Agent context; it does not approve actions.",
    "Not execution authorization.",
    "Not investment advice.",
)

CONTEXT_PACK_TOP_LEVEL_ALLOWLIST = frozenset(
    {
        "name",
        "available",
        "summary",
        "source_refs",
        "receipt_ref",
        "receipt_refs",
        "context_pack_refs",
        "data_gaps",
        "non_claims",
        "execution_allowed",
    }
)


@dataclass(frozen=True)
class AgentContextPackProjectionSpec:
    """Budget rule for one context pack within a profile."""

    pack_name: str
    priority: int
    max_chars: int
    max_items: int
    max_source_refs: int
    summary_keys: tuple[str, ...] = ()

    def model(self) -> dict[str, object]:
        return {
            "pack_name": self.pack_name,
            "priority": self.priority,
            "max_chars": self.max_chars,
            "max_items": self.max_items,
            "max_source_refs": self.max_source_refs,
            "summary_keys": list(self.summary_keys),
        }


@dataclass(frozen=True)
class AgentContextProjectionProfile:
    """Projection policy for one Agent profile."""

    profile_name: str
    total_max_chars: int
    pack_specs: tuple[AgentContextPackProjectionSpec, ...]
    non_claims: tuple[str, ...] = AGENT_CONTEXT_PROJECTION_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False

    def __post_init__(self) -> None:
        get_agent_profile(self.profile_name)
        if self.execution_allowed:
            raise ValueError("agent context projection profiles never grant execution authority")
        if self.authority_transition:
            raise ValueError("agent context projection profiles never grant authority transitions")

    def spec_for(self, pack_name: str) -> AgentContextPackProjectionSpec:
        for spec in self.pack_specs:
            if spec.pack_name == pack_name:
                return spec
        return AgentContextPackProjectionSpec(
            pack_name=pack_name,
            priority=100,
            max_chars=4_000,
            max_items=6,
            max_source_refs=8,
        )

    def model(self) -> dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "total_max_chars": self.total_max_chars,
            "pack_specs": [spec.model() for spec in self.pack_specs],
            "non_claims": list(self.non_claims),
            "execution_allowed": False,
            "authority_transition": False,
        }


DEFAULT_CAPITAL_SUMMARY_KEYS = (
    "as_of_date",
    "base_currency",
    "asset_valuation_admitted",
    "net_worth_admitted",
    "per_currency_totals",
    "liability_per_currency_totals",
    "asset_valuation_blockers",
    "net_worth_blockers",
    "net_worth",
    "cash_runway_months",
    "monthly_net_cashflow",
    "holding_count",
    "top_holding",
    "top_holding_weight",
    "top5_weight",
    "concentration_flagged",
    "insurance_review_gaps",
    "tax_review_gaps",
)

REVIEW_CAPITAL_SUMMARY_KEYS = (
    *DEFAULT_CAPITAL_SUMMARY_KEYS,
    "total_assets",
    "total_liabilities",
    "cash_total",
    "cash_total_verified",
    "interest_bearing_debt_total",
    "weighted_avg_interest_rate",
    "holdings",
    "upcoming_obligations",
)

CURRENT_IPS_KEYS = (
    "ips_id",
    "status",
    "base_currency",
    "created_at_utc",
    "receipt_ref",
    "thresholds",
    "allowed_asset_classes",
    "restricted_actions",
    "review_cadence",
)

IPS_CHECK_KEYS = ("ips_id", "as_of_date", "violations", "blocked", "results")
OPEN_PROPOSALS_KEYS = ("open_count", "returned_count", "items")


CONTEXT_PROJECTION_PROFILES: dict[str, AgentContextProjectionProfile] = {
    "default": AgentContextProjectionProfile(
        profile_name="default",
        total_max_chars=18_000,
        pack_specs=(
            AgentContextPackProjectionSpec(
                pack_name="capital_summary",
                priority=10,
                max_chars=6_000,
                max_items=8,
                max_source_refs=10,
                summary_keys=DEFAULT_CAPITAL_SUMMARY_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="current_ips",
                priority=20,
                max_chars=4_000,
                max_items=8,
                max_source_refs=8,
                summary_keys=CURRENT_IPS_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="ips_check",
                priority=30,
                max_chars=5_000,
                max_items=10,
                max_source_refs=8,
                summary_keys=IPS_CHECK_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="open_proposals",
                priority=40,
                max_chars=5_000,
                max_items=5,
                max_source_refs=8,
                summary_keys=OPEN_PROPOSALS_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="proposal_timeline",
                priority=50,
                max_chars=6_000,
                max_items=8,
                max_source_refs=8,
            ),
            AgentContextPackProjectionSpec(
                pack_name="planning_policy",
                priority=60,
                max_chars=4_000,
                max_items=10,
                max_source_refs=8,
            ),
        ),
    ),
    "review-draft": AgentContextProjectionProfile(
        profile_name="review-draft",
        total_max_chars=28_000,
        pack_specs=(
            AgentContextPackProjectionSpec(
                pack_name="capital_summary",
                priority=10,
                max_chars=8_000,
                max_items=12,
                max_source_refs=16,
                summary_keys=REVIEW_CAPITAL_SUMMARY_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="current_ips",
                priority=20,
                max_chars=5_000,
                max_items=10,
                max_source_refs=12,
                summary_keys=CURRENT_IPS_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="ips_check",
                priority=30,
                max_chars=7_000,
                max_items=16,
                max_source_refs=12,
                summary_keys=IPS_CHECK_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="open_proposals",
                priority=35,
                max_chars=9_000,
                max_items=10,
                max_source_refs=16,
                summary_keys=OPEN_PROPOSALS_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="proposal_timeline",
                priority=40,
                max_chars=10_000,
                max_items=20,
                max_source_refs=16,
            ),
            AgentContextPackProjectionSpec(
                pack_name="planning_policy",
                priority=45,
                max_chars=5_000,
                max_items=15,
                max_source_refs=12,
            ),
        ),
    ),
    "simulation": AgentContextProjectionProfile(
        profile_name="simulation",
        total_max_chars=24_000,
        pack_specs=(
            AgentContextPackProjectionSpec(
                pack_name="capital_summary",
                priority=10,
                max_chars=8_000,
                max_items=12,
                max_source_refs=14,
                summary_keys=REVIEW_CAPITAL_SUMMARY_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="current_ips",
                priority=20,
                max_chars=5_000,
                max_items=10,
                max_source_refs=10,
                summary_keys=CURRENT_IPS_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="ips_check",
                priority=30,
                max_chars=7_000,
                max_items=14,
                max_source_refs=10,
                summary_keys=IPS_CHECK_KEYS,
            ),
            AgentContextPackProjectionSpec(
                pack_name="open_proposals",
                priority=50,
                max_chars=5_000,
                max_items=5,
                max_source_refs=8,
                summary_keys=OPEN_PROPOSALS_KEYS,
            ),
        ),
    ),
}


def get_context_projection_profile(
    profile_name: str = "default",
) -> AgentContextProjectionProfile:
    get_agent_profile(profile_name)
    return CONTEXT_PROJECTION_PROFILES.get(
        profile_name,
        CONTEXT_PROJECTION_PROFILES["default"],
    )


def context_projection_view(profile_name: str = "default") -> dict[str, object]:
    """Return the runtime projection policy for diagnostics and review."""
    return get_context_projection_profile(profile_name).model()


def project_agent_context_result(
    *,
    profile_name: str,
    tool_name: str,
    result: dict[str, object],
) -> dict[str, object]:
    """Project a single context-pack result if the payload is projection-aware."""
    if not _is_context_pack_payload(result):
        return result
    return project_context_pack_payload(
        profile_name=profile_name,
        tool_name=tool_name,
        payload=result,
    )


def project_context_pack_payload(
    *,
    profile_name: str,
    payload: dict[str, object],
    tool_name: str | None = None,
) -> dict[str, object]:
    """Return a profile-budgeted projection of one context pack payload."""
    profile = get_context_projection_profile(profile_name)
    pack_name = str(payload.get("name") or "unknown")
    spec = profile.spec_for(pack_name)
    original_chars = _json_chars(payload)
    raw_summary = payload.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    selected_summary, dropped_keys = _select_summary(summary, spec.summary_keys)
    source_refs = list(_refs(_field_values(payload, "source_refs")))
    projected_source_refs = source_refs[: spec.max_source_refs]
    data_gaps = list(_refs(_field_values(payload, "data_gaps")))
    projected_data_gaps = data_gaps[: spec.max_items]
    context_pack_refs = list(_refs(_field_values(payload, "context_pack_refs")))
    receipt_refs = list(_refs(_field_values(payload, "receipt_refs")))
    receipt_ref = next(iter(_refs(_field_values(payload, "receipt_ref"))), None)
    dropped_top_level_keys = sorted(
        str(key) for key in payload if key not in CONTEXT_PACK_TOP_LEVEL_ALLOWLIST
    )
    if dropped_keys:
        projected_data_gaps.append(
            f"context projection omitted summary keys: {', '.join(dropped_keys)}"
        )
    if dropped_top_level_keys:
        projected_data_gaps.append(
            "context projection omitted top-level keys: "
            f"{', '.join(dropped_top_level_keys)}"
        )
    if len(source_refs) > spec.max_source_refs:
        projected_data_gaps.append(
            f"context projection truncated source refs to {spec.max_source_refs}"
        )
    if len(data_gaps) > spec.max_items:
        projected_data_gaps.append(
            f"context projection truncated data gaps to {spec.max_items}"
        )
    raw_available = payload.get("available", True)
    projected = {
        "name": pack_name,
        "available": raw_available if isinstance(raw_available, bool) else True,
        "summary": _bounded_summary(selected_summary, max_items=spec.max_items),
        "source_refs": projected_source_refs,
        "data_gaps": projected_data_gaps,
        "non_claims": list(
            _refs([*AGENT_CONTEXT_PROJECTION_NON_CLAIMS, *_field_values(payload, "non_claims")])
        ),
        "execution_allowed": False,
    }
    if context_pack_refs:
        projected["context_pack_refs"] = context_pack_refs
    if receipt_refs:
        projected["receipt_refs"] = receipt_refs
    if receipt_ref is not None:
        projected["receipt_ref"] = receipt_ref
    projected = _fit_pack_to_budget(
        projected=projected,
        profile_name=profile_name,
        tool_name=tool_name,
        spec=spec,
        original_chars=original_chars,
        dropped_keys=dropped_keys,
        dropped_top_level_keys=dropped_top_level_keys,
        original_source_ref_count=len(source_refs),
        source_refs_truncated=len(source_refs) > len(projected_source_refs),
    )
    return projected


def build_capital_context_projection_payload(
    *,
    profile_name: str = "default",
    open_proposals_limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Build a profile-budgeted Capital OS office brief for the Agent team."""
    profile = get_context_projection_profile(profile_name)
    owned_engine = engine is None
    try:
        active_engine = engine or open_state_core()
    except StateCoreStoreError as exc:
        unavailable = unavailable_context_pack("capital_context_projection", str(exc))
        return _projection_bundle(
            profile=profile,
            packs=[unavailable.model_dump(mode="json")],
            original_pack_count=0,
            data_gaps=[str(exc)],
        )
    try:
        packs = [
            _pack_payload(build_capital_summary_context(active_engine)),
            _pack_payload(build_current_ips_context(active_engine)),
            _pack_payload(build_ips_check_context(active_engine)),
            _pack_payload(
                build_open_proposals_context(
                    active_engine,
                    limit=max(1, min(int(open_proposals_limit), 20)),
                )
            ),
            _pack_payload(build_planning_policy_context()),
        ]
    finally:
        if owned_engine:
            active_engine.dispose()
    projected = [
        project_context_pack_payload(
            profile_name=profile.profile_name,
            tool_name="get_capital_context_projection",
            payload=pack,
        )
        for pack in packs
    ]
    return _projection_bundle(
        profile=profile,
        packs=projected,
        original_pack_count=len(packs),
        data_gaps=[],
    )


def _projection_bundle(
    *,
    profile: AgentContextProjectionProfile,
    packs: list[dict[str, object]],
    original_pack_count: int,
    data_gaps: list[str],
) -> dict[str, object]:
    ordered = sorted(
        packs,
        key=_pack_priority,
    )
    included: list[dict[str, object]] = []
    bundle_gaps = list(data_gaps)
    for pack in ordered:
        candidate = {
            "name": "capital_context_projection",
            "available": True,
            "profile_name": profile.profile_name,
            "packs": [*included, pack],
            "projection": _bundle_projection(profile, original_pack_count, False),
            "source_refs": list(_refs(_pack_refs([*included, pack], "source_refs"))),
            "context_pack_refs": list(_refs(_pack_refs([*included, pack], "context_pack_refs"))),
            "data_gaps": bundle_gaps,
            "non_claims": list(profile.non_claims),
            "execution_allowed": False,
        }
        if _json_chars(candidate) <= profile.total_max_chars:
            included.append(pack)
        else:
            bundle_gaps.append(
                f"context projection omitted pack {pack.get('name')} to stay under "
                f"{profile.total_max_chars} chars"
            )
    out = {
        "name": "capital_context_projection",
        "available": True,
        "profile_name": profile.profile_name,
        "packs": included,
        "projection": _bundle_projection(profile, original_pack_count, bool(bundle_gaps)),
        "source_refs": list(_refs(_pack_refs(included, "source_refs"))),
        "context_pack_refs": list(_refs(_pack_refs(included, "context_pack_refs"))),
        "data_gaps": list(_refs(bundle_gaps)),
        "non_claims": list(profile.non_claims),
        "execution_allowed": False,
    }
    return out


def _bundle_projection(
    profile: AgentContextProjectionProfile,
    original_pack_count: int,
    truncated: bool,
) -> dict[str, object]:
    return {
        "profile_name": profile.profile_name,
        "projection_kind": "capital_context_bundle",
        "total_max_chars": profile.total_max_chars,
        "original_pack_count": original_pack_count,
        "truncated": truncated,
        "execution_allowed": False,
        "authority_transition": False,
    }


def _fit_pack_to_budget(
    *,
    projected: dict[str, object],
    profile_name: str,
    tool_name: str | None,
    spec: AgentContextPackProjectionSpec,
    original_chars: int,
    dropped_keys: list[str],
    dropped_top_level_keys: list[str],
    original_source_ref_count: int,
    source_refs_truncated: bool,
) -> dict[str, object]:
    out = dict(projected)
    out["context_pack_refs"] = [f"context_pack://{spec.pack_name}"]
    projection = _pack_projection(
        profile_name=profile_name,
        tool_name=tool_name,
        spec=spec,
        original_chars=original_chars,
        projected_chars=0,
        dropped_keys=dropped_keys,
        dropped_top_level_keys=dropped_top_level_keys,
        original_source_ref_count=original_source_ref_count,
        source_refs_truncated=source_refs_truncated,
        truncated=False,
    )
    out["projection"] = projection
    projection["projected_chars"] = _json_chars(out)
    if _json_chars(out) <= spec.max_chars:
        return out

    compact = dict(out)
    compact["summary"] = _bounded_summary(
        compact.get("summary", {}),
        max_items=max(1, spec.max_items // 2),
        max_string_chars=240,
    )
    compact["data_gaps"] = [
        *_field_values(compact, "data_gaps"),
        f"context projection compacted {spec.pack_name} to fit {spec.max_chars} chars",
    ]
    compact_projection = _pack_projection(
        profile_name=profile_name,
        tool_name=tool_name,
        spec=spec,
        original_chars=original_chars,
        projected_chars=0,
        dropped_keys=dropped_keys,
        dropped_top_level_keys=dropped_top_level_keys,
        original_source_ref_count=original_source_ref_count,
        source_refs_truncated=source_refs_truncated,
        truncated=True,
    )
    compact["projection"] = compact_projection
    compact_projection["projected_chars"] = _json_chars(compact)
    if _json_chars(compact) <= spec.max_chars:
        return compact

    marker = dict(compact)
    marker["summary"] = _summary_compact_marker(
        pack_name=spec.pack_name,
        summary=compact.get("summary", {}),
    )
    source_refs = _field_values(compact, "source_refs")
    marker["source_refs"] = source_refs[:1]
    marker["data_gaps"] = [
        *_field_values(compact, "data_gaps"),
        f"context projection replaced {spec.pack_name} summary with compact marker",
    ]
    marker_projection = _pack_projection(
        profile_name=profile_name,
        tool_name=tool_name,
        spec=spec,
        original_chars=original_chars,
        projected_chars=0,
        dropped_keys=dropped_keys,
        dropped_top_level_keys=dropped_top_level_keys,
        original_source_ref_count=original_source_ref_count,
        source_refs_truncated=source_refs_truncated or len(source_refs) > 1,
        truncated=True,
    )
    marker["projection"] = marker_projection
    marker_projection["projected_chars"] = _json_chars(marker)
    return marker


def _pack_priority(pack: dict[str, object]) -> int:
    projection = pack.get("projection")
    if isinstance(projection, dict):
        return int(projection.get("priority", 100))
    return 100


def _pack_projection(
    *,
    profile_name: str,
    tool_name: str | None,
    spec: AgentContextPackProjectionSpec,
    original_chars: int,
    projected_chars: int,
    dropped_keys: list[str],
    dropped_top_level_keys: list[str],
    original_source_ref_count: int,
    source_refs_truncated: bool,
    truncated: bool,
) -> dict[str, object]:
    return {
        "profile_name": profile_name,
        "tool_name": tool_name,
        "projection_kind": "context_pack",
        "pack_name": spec.pack_name,
        "context_pack_ref": f"context_pack://{spec.pack_name}",
        "priority": spec.priority,
        "max_chars": spec.max_chars,
        "max_items": spec.max_items,
        "max_source_refs": spec.max_source_refs,
        "summary_keys": list(spec.summary_keys),
        "dropped_summary_keys": dropped_keys,
        "dropped_top_level_keys": dropped_top_level_keys,
        "original_source_ref_count": original_source_ref_count,
        "source_refs_truncated": source_refs_truncated,
        "original_chars": original_chars,
        "projected_chars": projected_chars,
        "truncated": truncated,
        "execution_allowed": False,
        "authority_transition": False,
    }


def _is_context_pack_payload(result: dict[str, object]) -> bool:
    return (
        isinstance(result.get("summary"), dict)
        and isinstance(result.get("name"), str)
        and str(result["name"]) in _known_context_pack_names()
    )


def _known_context_pack_names() -> frozenset[str]:
    return frozenset(
        spec.pack_name
        for profile in CONTEXT_PROJECTION_PROFILES.values()
        for spec in profile.pack_specs
    )


def _pack_payload(pack: AgentContextPack) -> dict[str, object]:
    return pack.model_dump(mode="json")


def _select_summary(
    summary: dict[str, Any],
    keys: tuple[str, ...],
) -> tuple[dict[str, Any], list[str]]:
    if not keys:
        return dict(summary), []
    selected = {key: summary[key] for key in keys if key in summary}
    dropped = [key for key in summary if key not in selected]
    return selected, dropped


def _bounded_value(
    value: Any,
    *,
    max_items: int,
    max_string_chars: int = 500,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _bounded_value(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for key, child in list(value.items())[:max_items]
        }
    if isinstance(value, (list, tuple)):
        return [
            _bounded_value(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for child in list(value)[:max_items]
        ]
    if isinstance(value, str) and len(value) > max_string_chars:
        return value[: max_string_chars - 15].rstrip() + "... [truncated]"
    return value


def _bounded_summary(
    value: object,
    *,
    max_items: int,
    max_string_chars: int = 500,
) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    return {
        str(key): _bounded_value(
            child,
            max_items=max_items,
            max_string_chars=max_string_chars,
        )
        for key, child in summary.items()
    }


def _summary_compact_marker(
    *,
    pack_name: str,
    summary: object,
) -> dict[str, Any]:
    marker: dict[str, Any] = {"compacted": True}
    if pack_name == "capital_summary" and isinstance(summary, dict):
        marker.update(
            {
                key: summary[key]
                for key in CAPITAL_ADMISSION_SUMMARY_KEYS
                if key in summary
            }
        )
    return marker


def _field_values(result: dict[str, object], key: str) -> list[str]:
    value = result.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _pack_refs(packs: Iterable[dict[str, object]], key: str) -> list[str]:
    return [ref for pack in packs for ref in _field_values(pack, key)]


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def _json_chars(value: object) -> int:
    return len(json.dumps(value, sort_keys=True, default=str))
