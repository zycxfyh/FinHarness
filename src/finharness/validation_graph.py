"""LangGraph workflow for sixth-layer validation."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.hypotheses import HypothesisSnapshot
from finharness.hypotheses_graph import run_hypotheses_graph
from finharness.validation import (
    HermesValidationDraftProvider,
    ValidationCheckResult,
    ValidationJob,
    ValidationSourceSpec,
    build_validation_quality,
    build_validation_results,
    create_validation_jobs,
    persist_validation_bundle,
)


class ValidationGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    llm_enabled: bool
    hermes_root: str
    hypothesis_snapshot: dict[str, Any]
    source: dict[str, Any]
    validation_jobs: list[dict[str, Any]]
    source_validity: dict[str, Any]
    mechanism_check: dict[str, Any]
    event_reaction: dict[str, Any]
    benchmark_context: dict[str, Any]
    disconfirmation: dict[str, Any]
    limitations: dict[str, Any]
    validation_results: list[dict[str, Any]]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def source_config_node(state: ValidationGraphState) -> ValidationGraphState:
    llm_enabled = bool(state.get("llm_enabled", False))
    source = ValidationSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesValidationDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        config={
            "universe": state.get("universe"),
            "forms": state.get("forms", ["8-K", "10-Q", "10-K"]),
            "max_records": state.get("max_records", 30),
            "max_hypotheses": state.get("max_hypotheses", 10),
            "symbols": state.get("symbols", []),
        },
    )
    return {"source": source.model_dump(mode="json")}


def load_hypothesis_snapshot_node(state: ValidationGraphState) -> ValidationGraphState:
    if "hypothesis_snapshot" in state:
        return {"hypothesis_snapshot": state["hypothesis_snapshot"]}
    result = run_hypotheses_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
    )
    return {"hypothesis_snapshot": result["snapshot"]}


def create_validation_jobs_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = HypothesisSnapshot.model_validate(state["hypothesis_snapshot"])
    jobs = create_validation_jobs(snapshot)
    return {"validation_jobs": [job.model_dump(mode="json") for job in jobs]}


def source_validity_check_node(state: ValidationGraphState) -> ValidationGraphState:
    return {
        "source_validity": {
            "status": "planned",
            "job_count": len(state["validation_jobs"]),
        }
    }


def mechanism_check_node(state: ValidationGraphState) -> ValidationGraphState:
    return {
        "mechanism_check": {
            "status": "planned",
            "job_count": len(state["validation_jobs"]),
        }
    }


def event_reaction_check_node(state: ValidationGraphState) -> ValidationGraphState:
    return {
        "event_reaction": {
            "status": "planned",
            "note": "MVP checks input availability and records limitations.",
        }
    }


def benchmark_context_check_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = HypothesisSnapshot.model_validate(state["hypothesis_snapshot"])
    universe = {symbol.upper() for symbol in snapshot.universe}
    return {
        "benchmark_context": {
            "status": "checked",
            "has_spy": "SPY" in universe,
            "has_qqq": "QQQ" in universe,
        }
    }


def disconfirmation_check_node(state: ValidationGraphState) -> ValidationGraphState:
    jobs = [ValidationJob.model_validate(job) for job in state["validation_jobs"]]
    missing = [job.validation_job_id for job in jobs if not job.disconfirmation_items]
    return {
        "disconfirmation": {
            "status": "checked",
            "missing": missing,
        }
    }


def limitations_check_node(state: ValidationGraphState) -> ValidationGraphState:
    return {
        "limitations": {
            "status": "recorded",
            "note": "MVP records limitations before empirical metric expansion.",
        }
    }


def validation_results_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = HypothesisSnapshot.model_validate(state["hypothesis_snapshot"])
    jobs = [ValidationJob.model_validate(job) for job in state["validation_jobs"]]
    provider = (
        HermesValidationDraftProvider(
            hermes_root=state.get("hermes_root", "/root/projects/hermes-agent")
        )
        if state.get("llm_enabled", False)
        else None
    )
    results = build_validation_results(
        snapshot=snapshot,
        jobs=jobs,
        draft_provider=provider,
    )
    return {"validation_results": [result.model_dump(mode="json") for result in results]}


def quality_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = HypothesisSnapshot.model_validate(state["hypothesis_snapshot"])
    jobs = [ValidationJob.model_validate(job) for job in state["validation_jobs"]]
    results = [
        ValidationCheckResult.model_validate(result)
        for result in state["validation_results"]
    ]
    quality = build_validation_quality(snapshot=snapshot, jobs=jobs, results=results)
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: ValidationGraphState) -> ValidationGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: ValidationGraphState) -> ValidationGraphState:
    hypothesis_snapshot = HypothesisSnapshot.model_validate(state["hypothesis_snapshot"])
    source = ValidationSourceSpec(**state["source"])
    jobs = [ValidationJob.model_validate(job) for job in state["validation_jobs"]]
    results = [
        ValidationCheckResult.model_validate(result)
        for result in state["validation_results"]
    ]
    bundle = persist_validation_bundle(
        source=source,
        input_hypothesis_snapshot=hypothesis_snapshot,
        jobs=jobs,
        results=results,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: ValidationGraphState) -> ValidationGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "proposal_review",
            "job_count": snapshot["job_count"],
            "result_count": snapshot["result_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "validation evidence",
                "proposal review prompts",
                "human review prompts",
                "hypothesis rejection reasons",
            ],
            "forbidden_outputs": [
                "orders",
                "position sizing",
                "broker instructions",
                "execution permission",
                "trade recommendation",
            ],
        }
    }


def review_hook_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human validation review before proposal promotion",
            "promote_to": ["proposal layer", "docs/reviews/", "docs/lessons/"],
        }
    }


def final_node(state: ValidationGraphState) -> ValidationGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_validation_v1",
            "input_hypothesis_snapshot_id": snapshot["input_hypothesis_snapshot_id"],
            "job_count": snapshot["job_count"],
            "result_count": snapshot["result_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "proposal_handoff": snapshot["proposal_handoff"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
            "llm_enabled": state.get("source", {}).get("llm_enabled", False),
            "hermes_root": state.get("source", {}).get("hermes_root"),
        }
    }


def build_validation_graph():
    graph = StateGraph(ValidationGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_hypothesis_snapshot", load_hypothesis_snapshot_node)
    graph.add_node("create_validation_jobs", create_validation_jobs_node)
    graph.add_node("source_validity_check", source_validity_check_node)
    graph.add_node("mechanism_check", mechanism_check_node)
    graph.add_node("event_reaction_check", event_reaction_check_node)
    graph.add_node("benchmark_context_check", benchmark_context_check_node)
    graph.add_node("disconfirmation_check", disconfirmation_check_node)
    graph.add_node("limitations_check", limitations_check_node)
    graph.add_node("validation_results", validation_results_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_hypothesis_snapshot")
    graph.add_edge("load_hypothesis_snapshot", "create_validation_jobs")
    graph.add_edge("create_validation_jobs", "source_validity_check")
    graph.add_edge("source_validity_check", "mechanism_check")
    graph.add_edge("mechanism_check", "event_reaction_check")
    graph.add_edge("event_reaction_check", "benchmark_context_check")
    graph.add_edge("benchmark_context_check", "disconfirmation_check")
    graph.add_edge("disconfirmation_check", "limitations_check")
    graph.add_edge("limitations_check", "validation_results")
    graph.add_edge("validation_results", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


validation_graph = build_validation_graph()


def run_validation_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    hypothesis_snapshot: dict[str, Any] | None = None,
    llm_enabled: bool = False,
    hermes_root: str = "/root/projects/hermes-agent",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": universe,
        "forms": forms or ["8-K", "10-Q", "10-K"],
        "max_records": max_records,
        "max_hypotheses": max_hypotheses,
        "symbols": symbols or [],
        "llm_enabled": llm_enabled,
        "hermes_root": hermes_root,
    }
    if hypothesis_snapshot is not None:
        payload["hypothesis_snapshot"] = hypothesis_snapshot
    result = validation_graph.invoke(payload)
    return dict(result)
