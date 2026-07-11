"""Transparent deterministic concentration scenarios for DecisionCase review.

This is deliberately not an optimizer.  It compares three operator-legible
paths using exact Decimal arithmetic and refuses to manufacture precision from
missing or unreconciled capital state.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from finharness.delegated_review import DecisionCase, Scenario, create_scenario

TaxStatus = Literal["known", "placeholder", "not_computable"]
ScenarioSetStatus = Literal["complete", "partial", "blocked"]


class ConcentrationScenarioInputs(BaseModel):
    model_config = ConfigDict(frozen=True)

    capital_state_ref: str
    valued_at_utc: str
    base_currency: str
    position_symbol: str
    position_value: Decimal | None
    other_position_values: tuple[Decimal, ...] | None
    cash: Decimal | None
    total_assets: Decimal | None
    monthly_expenses: Decimal | None
    future_cashflow: Decimal | None
    reduction_amount: Decimal | None
    estimated_cost: Decimal | None
    single_stock_shock: Decimal | None
    market_shock: Decimal | None
    tax_status: TaxStatus
    uncertainty: Decimal | None
    source_refs: tuple[str, ...]

    @field_validator("capital_state_ref", "valued_at_utc", "base_currency", "position_symbol")
    @classmethod
    def require_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("concentration scenario identity fields must be non-blank")
        return value

    @field_validator(
        "position_value",
        "cash",
        "total_assets",
        "monthly_expenses",
        "future_cashflow",
        "reduction_amount",
        "estimated_cost",
    )
    @classmethod
    def require_non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("concentration scenario monetary inputs must be non-negative")
        return value

    @field_validator("other_position_values")
    @classmethod
    def require_non_negative_positions(
        cls, value: tuple[Decimal, ...] | None
    ) -> tuple[Decimal, ...] | None:
        if value is not None and any(item < 0 for item in value):
            raise ValueError("other position values must be non-negative")
        return value

    @field_validator("single_stock_shock", "market_shock")
    @classmethod
    def bound_shock(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not Decimal("-1") <= value <= Decimal("1"):
            raise ValueError("shock assumptions must be between -1 and 1")
        return value

    @field_validator("uncertainty")
    @classmethod
    def bound_uncertainty(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not Decimal("0") <= value <= Decimal("1"):
            raise ValueError("uncertainty must be between 0 and 1")
        return value


class ConcentrationScenarioSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_case_id: str
    decision_case_version_id: str
    proposal_version_id: str
    capital_state_ref: str
    status: ScenarioSetStatus
    scenarios: tuple[Scenario, ...] = ()
    data_gaps: tuple[str, ...] = ()
    calculation_version: str = "concentration-scenario-v0"
    execution_allowed: bool = False
    authority_transition: bool = False

    @model_validator(mode="after")
    def keep_effect_boundary_closed(self) -> ConcentrationScenarioSet:
        if self.execution_allowed or self.authority_transition:
            raise ValueError("scenario set is evidence, not effect authority")
        if self.status == "blocked" and self.scenarios:
            raise ValueError("blocked scenario set cannot carry computed scenarios")
        if self.status != "blocked" and len(self.scenarios) != 3:
            raise ValueError("ready concentration set requires exactly three scenarios")
        return self


_REQUIRED_INPUTS: tuple[str, ...] = (
    "position_value",
    "other_position_values",
    "cash",
    "total_assets",
    "monthly_expenses",
    "future_cashflow",
    "reduction_amount",
    "estimated_cost",
    "single_stock_shock",
    "market_shock",
    "uncertainty",
)


def _missing_inputs(inputs: ConcentrationScenarioInputs) -> list[str]:
    return [name for name in _REQUIRED_INPUTS if getattr(inputs, name) is None]


def _blocked(
    decision_case: DecisionCase,
    inputs: ConcentrationScenarioInputs,
    *gaps: str,
) -> ConcentrationScenarioSet:
    return ConcentrationScenarioSet(
        decision_case_id=decision_case.decision_case_id,
        decision_case_version_id=decision_case.case_version_id,
        proposal_version_id=decision_case.proposal_version.proposal_version_id,
        capital_state_ref=inputs.capital_state_ref,
        status="blocked",
        data_gaps=tuple(gaps),
    )


def _metrics(
    *,
    position_value: Decimal,
    other_position_values: tuple[Decimal, ...],
    cash: Decimal,
    total_assets: Decimal,
    monthly_expenses: Decimal,
    estimated_cost: Decimal,
    single_stock_shock: Decimal,
    market_shock: Decimal,
    tax_status: TaxStatus,
) -> dict[str, str]:
    weight = position_value / total_assets
    component_values = (position_value, *other_position_values, cash)
    hhi = sum(((value / total_assets) ** 2 for value in component_values), Decimal("0"))
    return {
        "position_value": str(position_value),
        "position_weight": str(weight),
        "cash": str(cash),
        "total_assets": str(total_assets),
        "hhi": str(hhi),
        "single_stock_shock_contribution": str(position_value * single_stock_shock),
        "simple_market_shock": str(total_assets * market_shock),
        "cash_runway_months": str(cash / monthly_expenses),
        "estimated_cost": str(estimated_cost),
        "tax_status": tax_status,
    }


def _create_bound_scenario(
    *,
    decision_case: DecisionCase,
    inputs: ConcentrationScenarioInputs,
    kind: Literal["do_nothing", "future_cashflow_dilution", "operator_sized_reduction"],
    assumptions: dict[str, str],
    metrics: dict[str, str],
    uncertainty: Decimal,
    notional_implication: Decimal,
    tax_gaps: tuple[str, ...],
    created_at_utc: str,
) -> Scenario:
    return create_scenario(
        decision_case=decision_case,
        kind=kind,
        assumptions=assumptions,
        metrics=metrics,
        uncertainty=float(uncertainty),
        notional_implication=float(notional_implication),
        calculation_version="concentration-scenario-v0",
        source_refs=(inputs.capital_state_ref, *inputs.source_refs),
        data_gaps=tax_gaps,
        created_at_utc=created_at_utc,
    )


def build_concentration_scenario_set(
    *,
    decision_case: DecisionCase,
    inputs: ConcentrationScenarioInputs,
    created_at_utc: str,
) -> ConcentrationScenarioSet:
    """Build do-nothing, cashflow dilution, and operator reduction scenarios."""
    missing = _missing_inputs(inputs)
    if missing:
        return _blocked(
            decision_case,
            inputs,
            *(f"missing:{name}" for name in missing),
        )
    position_value = cast(Decimal, inputs.position_value)
    other_position_values = cast(tuple[Decimal, ...], inputs.other_position_values)
    cash = cast(Decimal, inputs.cash)
    total_assets = cast(Decimal, inputs.total_assets)
    monthly_expenses = cast(Decimal, inputs.monthly_expenses)
    future_cashflow = cast(Decimal, inputs.future_cashflow)
    reduction_amount = cast(Decimal, inputs.reduction_amount)
    estimated_cost = cast(Decimal, inputs.estimated_cost)
    single_stock_shock = cast(Decimal, inputs.single_stock_shock)
    market_shock = cast(Decimal, inputs.market_shock)
    uncertainty = cast(Decimal, inputs.uncertainty)

    if total_assets <= 0:
        return _blocked(decision_case, inputs, "invalid:total_assets_not_positive")
    if monthly_expenses <= 0:
        return _blocked(decision_case, inputs, "invalid:monthly_expenses_not_positive")
    components = position_value + sum(other_position_values, Decimal("0")) + cash
    if components != total_assets:
        return _blocked(decision_case, inputs, "unreconciled:asset_components")
    if reduction_amount > position_value:
        return _blocked(decision_case, inputs, "invalid:reduction_exceeds_position")
    if estimated_cost > cash + reduction_amount:
        return _blocked(decision_case, inputs, "invalid:cost_exceeds_post_sale_cash")

    tax_gaps = (
        ()
        if inputs.tax_status == "known"
        else (f"tax:{inputs.tax_status}",)
    )
    do_nothing = _create_bound_scenario(
        decision_case=decision_case,
        inputs=inputs,
        kind="do_nothing",
        assumptions={"path": "no capital change"},
        metrics=_metrics(
            position_value=position_value,
            other_position_values=other_position_values,
            cash=cash,
            total_assets=total_assets,
            monthly_expenses=monthly_expenses,
            estimated_cost=Decimal("0"),
            single_stock_shock=single_stock_shock,
            market_shock=market_shock,
            tax_status=inputs.tax_status,
        ),
        uncertainty=uncertainty,
        notional_implication=Decimal("0"),
        tax_gaps=tax_gaps,
        created_at_utc=created_at_utc,
    )
    diluted_total = total_assets + future_cashflow
    cashflow = _create_bound_scenario(
        decision_case=decision_case,
        inputs=inputs,
        kind="future_cashflow_dilution",
        assumptions={"future_cashflow": str(future_cashflow)},
        metrics=_metrics(
            position_value=position_value,
            other_position_values=other_position_values,
            cash=cash + future_cashflow,
            total_assets=diluted_total,
            monthly_expenses=monthly_expenses,
            estimated_cost=Decimal("0"),
            single_stock_shock=single_stock_shock,
            market_shock=market_shock,
            tax_status=inputs.tax_status,
        ),
        uncertainty=uncertainty,
        notional_implication=Decimal("0"),
        tax_gaps=tax_gaps,
        created_at_utc=created_at_utc,
    )
    reduced_position = position_value - reduction_amount
    reduced_cash = cash + reduction_amount - estimated_cost
    reduction = _create_bound_scenario(
        decision_case=decision_case,
        inputs=inputs,
        kind="operator_sized_reduction",
        assumptions={
            "reduction_amount": str(reduction_amount),
            "estimated_cost": str(estimated_cost),
        },
        metrics=_metrics(
            position_value=reduced_position,
            other_position_values=other_position_values,
            cash=reduced_cash,
            total_assets=total_assets - estimated_cost,
            monthly_expenses=monthly_expenses,
            estimated_cost=estimated_cost,
            single_stock_shock=single_stock_shock,
            market_shock=market_shock,
            tax_status=inputs.tax_status,
        ),
        uncertainty=uncertainty,
        notional_implication=reduction_amount,
        tax_gaps=tax_gaps,
        created_at_utc=created_at_utc,
    )
    return ConcentrationScenarioSet(
        decision_case_id=decision_case.decision_case_id,
        decision_case_version_id=decision_case.case_version_id,
        proposal_version_id=decision_case.proposal_version.proposal_version_id,
        capital_state_ref=inputs.capital_state_ref,
        status="complete" if not tax_gaps else "partial",
        scenarios=(do_nothing, cashflow, reduction),
        data_gaps=tax_gaps,
    )
