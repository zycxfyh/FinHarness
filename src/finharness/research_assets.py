"""Research asset library contracts for FinHarness.

The library stores reusable research contracts and references. It does not run
strategies, compute portfolio outputs, claim compliance, or authorize execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.project_paths import ROOT

RESEARCH_DATA_ROOT = ROOT / "data" / "research"
STRATEGY_SPEC_ROOT = RESEARCH_DATA_ROOT / "strategy-specs"
METHOD_SPEC_ROOT = RESEARCH_DATA_ROOT / "method-specs"
REFERENCE_CARD_ROOT = RESEARCH_DATA_ROOT / "reference-cards"

LayerRef = Literal["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"]
AssetStatus = Literal["draft", "active", "deprecated", "reference_only"]
IntegrationStatus = Literal["reference_only", "experiment_only", "paper_adapter", "live_read"]
SourceType = Literal[
    "strategy",
    "math_method",
    "open_source_tool",
    "institutional_standard",
    "broker_or_exchange",
    "provider",
]


class StrategySpec(BaseModel):
    """Reusable strategy contract for research handoff."""

    model_config = ConfigDict(frozen=True)

    id: str
    status: AssetStatus
    used_by_layers: list[LayerRef]
    universe: dict[str, object]
    timeframe: str
    thesis: dict[str, object]
    data_requirements: list[str]
    indicators: list[str] = Field(default_factory=list)
    validation_protocol: dict[str, object]
    risk_contract: dict[str, object]
    execution_constraints: dict[str, object]
    post_trade_review: dict[str, object]
    references: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    no_execution_authority: bool = True


class MathMethodSpec(BaseModel):
    """Mathematical method contract used by evidence layers."""

    model_config = ConfigDict(frozen=True)

    id: str
    domain: str
    status: AssetStatus
    used_by_layers: list[LayerRef]
    purpose: str
    assumptions: list[str]
    formula_or_definition: str
    failure_modes: list[str]
    implementation_boundary: str
    allowed_libraries: list[str] = Field(default_factory=list)
    tests_required: list[str]
    references: list[str] = Field(default_factory=list)
    no_execution_authority: bool = True


class ReferenceCard(BaseModel):
    """External reference card for tools, providers, standards, and venues."""

    model_config = ConfigDict(frozen=True)

    id: str
    source_type: SourceType
    domain: str
    status: AssetStatus
    applies_to_layers: list[LayerRef]
    what_to_learn: list[str]
    do_not_claim: list[str]
    integration_status: IntegrationStatus
    trust_boundary: str
    references: list[str] = Field(default_factory=list)
    no_execution_authority: bool = True


class ResearchAssetCatalog(BaseModel):
    """Loaded research asset inventory."""

    model_config = ConfigDict(frozen=True)

    strategy_specs: list[StrategySpec]
    method_specs: list[MathMethodSpec]
    reference_cards: list[ReferenceCard]

    def summary(self) -> dict[str, object]:
        return {
            "strategy_spec_count": len(self.strategy_specs),
            "method_spec_count": len(self.method_specs),
            "reference_card_count": len(self.reference_cards),
            "strategy_ids": [item.id for item in self.strategy_specs],
            "method_ids": [item.id for item in self.method_specs],
            "reference_ids": [item.id for item in self.reference_cards],
            "execution_allowed": False,
        }


class ResearchAssetSelection(BaseModel):
    """Selected research assets for one orchestrated run."""

    model_config = ConfigDict(frozen=True)

    policy: Literal["cite_only"] = "cite_only"
    strategy_specs: list[StrategySpec] = Field(default_factory=list)
    method_specs: list[MathMethodSpec] = Field(default_factory=list)
    reference_cards: list[ReferenceCard] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    execution_allowed: bool = False

    def summary(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "strategy_ids": [item.id for item in self.strategy_specs],
            "method_ids": [item.id for item in self.method_specs],
            "reference_ids": [item.id for item in self.reference_cards],
            "missing_ids": self.missing_ids,
            "execution_allowed": False,
        }

    def context_for_layer(self, layer: LayerRef) -> dict[str, object]:
        strategies = [
            {
                "id": item.id,
                "status": item.status,
                "timeframe": item.timeframe,
                "references": item.references,
                "no_execution_authority": item.no_execution_authority,
            }
            for item in self.strategy_specs
            if layer in item.used_by_layers
        ]
        methods = [
            {
                "id": item.id,
                "domain": item.domain,
                "status": item.status,
                "allowed_libraries": item.allowed_libraries,
                "no_execution_authority": item.no_execution_authority,
            }
            for item in self.method_specs
            if layer in item.used_by_layers
        ]
        references = [
            {
                "id": item.id,
                "source_type": item.source_type,
                "domain": item.domain,
                "integration_status": item.integration_status,
                "trust_boundary": item.trust_boundary,
                "no_execution_authority": item.no_execution_authority,
            }
            for item in self.reference_cards
            if layer in item.applies_to_layers
        ]
        return {
            "policy": self.policy,
            "layer": layer,
            "strategy_ids": [item["id"] for item in strategies],
            "method_ids": [item["id"] for item in methods],
            "reference_ids": [item["id"] for item in references],
            "strategy_specs": strategies,
            "method_specs": methods,
            "reference_cards": references,
            "missing_ids": self.missing_ids,
            "execution_allowed": False,
        }


def _load_json_files(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    payloads = []
    for path in sorted(root.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payloads.append(json.load(handle))
    return payloads


def load_strategy_specs(root: Path = STRATEGY_SPEC_ROOT) -> list[StrategySpec]:
    return [StrategySpec.model_validate(item) for item in _load_json_files(root)]


def load_method_specs(root: Path = METHOD_SPEC_ROOT) -> list[MathMethodSpec]:
    return [MathMethodSpec.model_validate(item) for item in _load_json_files(root)]


def load_reference_cards(root: Path = REFERENCE_CARD_ROOT) -> list[ReferenceCard]:
    return [ReferenceCard.model_validate(item) for item in _load_json_files(root)]


def load_research_asset_catalog(root: Path = RESEARCH_DATA_ROOT) -> ResearchAssetCatalog:
    return ResearchAssetCatalog(
        strategy_specs=load_strategy_specs(root / "strategy-specs"),
        method_specs=load_method_specs(root / "method-specs"),
        reference_cards=load_reference_cards(root / "reference-cards"),
    )


def _append_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def _select_typed_assets(
    *,
    requested_ids: list[str] | None,
    lookup: dict[str, Any],
    selected_ids: list[str],
    missing_ids: list[str],
) -> None:
    for asset_id in requested_ids or []:
        if asset_id in lookup:
            _append_unique(selected_ids, asset_id)
        else:
            _append_unique(missing_ids, asset_id)


def resolve_research_assets(
    *,
    research_asset_ids: list[str] | None = None,
    strategy_spec_ids: list[str] | None = None,
    method_spec_ids: list[str] | None = None,
    reference_card_ids: list[str] | None = None,
    policy: Literal["cite_only"] = "cite_only",
    root: Path = RESEARCH_DATA_ROOT,
) -> ResearchAssetSelection:
    """Resolve requested asset ids into a cite-only selection.

    This is an external-reference handoff. It never grants execution authority.
    """

    catalog = load_research_asset_catalog(root)
    strategy_by_id = {item.id: item for item in catalog.strategy_specs}
    method_by_id = {item.id: item for item in catalog.method_specs}
    reference_by_id = {item.id: item for item in catalog.reference_cards}
    selected_strategy_ids: list[str] = []
    selected_method_ids: list[str] = []
    selected_reference_ids: list[str] = []
    missing_ids: list[str] = []

    for asset_id in research_asset_ids or []:
        if asset_id in strategy_by_id:
            _append_unique(selected_strategy_ids, asset_id)
        elif asset_id in method_by_id:
            _append_unique(selected_method_ids, asset_id)
        elif asset_id in reference_by_id:
            _append_unique(selected_reference_ids, asset_id)
        else:
            _append_unique(missing_ids, asset_id)

    _select_typed_assets(
        requested_ids=strategy_spec_ids,
        lookup=strategy_by_id,
        selected_ids=selected_strategy_ids,
        missing_ids=missing_ids,
    )
    _select_typed_assets(
        requested_ids=method_spec_ids,
        lookup=method_by_id,
        selected_ids=selected_method_ids,
        missing_ids=missing_ids,
    )
    _select_typed_assets(
        requested_ids=reference_card_ids,
        lookup=reference_by_id,
        selected_ids=selected_reference_ids,
        missing_ids=missing_ids,
    )

    return ResearchAssetSelection(
        policy=policy,
        strategy_specs=[strategy_by_id[item] for item in selected_strategy_ids],
        method_specs=[method_by_id[item] for item in selected_method_ids],
        reference_cards=[reference_by_id[item] for item in selected_reference_ids],
        missing_ids=missing_ids,
        execution_allowed=False,
    )


def compact_research_asset_context(
    context: dict[str, Any] | None,
    layer: LayerRef,
) -> dict[str, object]:
    if not context:
        return {
            "policy": "cite_only",
            "layer": layer,
            "strategy_ids": [],
            "method_ids": [],
            "reference_ids": [],
            "missing_ids": [],
            "execution_allowed": False,
        }
    selection = ResearchAssetSelection.model_validate(context)
    return selection.context_for_layer(layer)
