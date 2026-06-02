"""LangGraph workflow for FinHarness cognitive engineering."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parents[2]


class CognitiveGraphState(TypedDict, total=False):
    topic: str
    raw_thought: str
    layer: str
    source: str
    root: str
    stamp: str
    date: str
    slug: str
    idea: dict[str, Any]
    note: dict[str, Any]
    proposal: dict[str, Any]
    implementation: dict[str, Any]
    review: dict[str, Any]
    lesson: dict[str, Any]
    receipt_path: str
    final: dict[str, Any]


def _root(state: CognitiveGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def _stamp(state: CognitiveGraphState) -> str:
    return state.get("stamp") or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _date_from_stamp(stamp: str) -> str:
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"


def _slug(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return normalized[:72] or "cognitive-flow"


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return str(path)


def _title(state: CognitiveGraphState) -> str:
    return state.get("topic") or "Untitled Cognitive Flow"


def capture_idea_node(state: CognitiveGraphState) -> CognitiveGraphState:
    stamp = _stamp(state)
    date = state.get("date") or _date_from_stamp(stamp)
    slug = state.get("slug") or _slug(_title(state))
    root = _root(state)
    topic = _title(state)
    raw_thought = state.get("raw_thought") or topic
    layer = state.get("layer") or "cognitive-engineering"
    source = state.get("source") or "langgraph_cognitive_flow"
    path = root / "ideas" / f"{date}-{slug}.md"
    content = f"""# Idea: {topic}

idea_id: {date}-{slug}
date: {date}
source: {source}
layer: {layer}
status: captured

## Raw Thought

{raw_thought}

## Hypothesis

This idea may improve FinHarness if it becomes a structured workflow that can be
tested, reviewed, and evolved.

## Why It Might Matter

It may reduce future cognitive cost by preserving the intent before action.

## Testable Experiment

Run the idea through the cognitive LangGraph flow and check whether it produces
a usable note, proposal, review, lesson, and receipt.

## Success Signal

The next implementation step can be started from the generated proposal without
needing to reconstruct the conversation.

## Risk Or Failure Mode

The artifacts may become ceremony if they do not change future action.

## Links

- Proposal: docs/proposals/{date}-{slug}.md
- Review: docs/reviews/{date}-{slug}.md
- Lesson: docs/lessons/{date}-{slug}.md
"""
    return {
        "stamp": stamp,
        "date": date,
        "slug": slug,
        "idea": {
            "path": _write(path, content),
            "topic": topic,
            "raw_thought": raw_thought,
            "layer": layer,
            "status": "captured",
        },
    }


def synthesize_note_node(state: CognitiveGraphState) -> CognitiveGraphState:
    root = _root(state)
    date = state["date"]
    slug = state["slug"]
    topic = _title(state)
    path = root / "docs" / "notes" / f"{date}-{slug}-workflow-note.md"
    content = f"""# Workflow Note: {topic}

Date: {date}
Source idea: {state["idea"]["path"]}

## Summary

This note captures the context needed to move the idea from raw thought into a
reviewable project workflow.

## Project Pattern

```text
idea
-> note
-> proposal
-> implementation
-> review
-> lesson
-> AGENTS.md / module docs / ADR when needed
```

## Interpretation

The useful part is not the document count. The useful part is making intent,
evidence, action, and review explicit enough that future work can continue from
project state instead of chat memory.

## Immediate Use

Use the generated proposal as the next action boundary. Use the generated
review and lesson as placeholders that must be updated after the action.
"""
    return {
        "note": {
            "path": _write(path, content),
            "status": "synthesized",
        }
    }


def draft_proposal_node(state: CognitiveGraphState) -> CognitiveGraphState:
    root = _root(state)
    date = state["date"]
    slug = state["slug"]
    topic = _title(state)
    path = root / "docs" / "proposals" / f"{date}-{slug}.md"
    content = f"""# Proposal: {topic}

Date: {date}
Status: draft
Related idea: {state["idea"]["path"]}
Related note: {state["note"]["path"]}
Related module:
Related ADR:

## Problem

FinHarness needs a repeatable way to turn important thoughts into project state
that can guide implementation and review.

## User / Workflow

The users are the future human operator, future AI agent, and any workflow that
needs to understand why a project action exists.

## Goals

```text
capture intent
produce a before-action proposal
preserve a review slot
distill a future lesson
write a receipt
```

## Non-Goals

```text
replace code implementation
pretend untested ideas are validated
create documentation ceremony
authorize financial execution
```

## Evidence

- Idea: {state["idea"]["path"]}
- Note: {state["note"]["path"]}
- Project rule: AGENTS.md

## Design

Run the idea through a LangGraph workflow with explicit nodes for capture,
synthesis, proposal, implementation placeholder, review, lesson, and receipt.

## Inputs / Outputs

Typed inputs:

```text
topic
raw_thought
layer
source
```

Typed outputs:

```text
idea path
note path
proposal path
implementation plan
review path
lesson path
receipt path
```

## Quality / Lineage / Receipt

The receipt records all artifact paths and the workflow version. The proposal
keeps links back to the idea and note.

## Risks

```text
too many documents for small thoughts
generated placeholders never updated
proposal accepted without implementation evidence
```

## Success Signal

A future implementation can start from this proposal and later update the review
and lesson with real evidence.

## Review Plan

After the next implementation action, update the review with actual outcome,
evidence, surprises, and actions.
"""
    return {
        "proposal": {
            "path": _write(path, content),
            "status": "draft",
        }
    }


def implementation_plan_node(state: CognitiveGraphState) -> CognitiveGraphState:
    return {
        "implementation": {
            "status": "planned",
            "next_action": "Use the proposal to choose the smallest vertical slice.",
            "permission_boundary": "This graph writes project knowledge artifacts only.",
        }
    }


def review_node(state: CognitiveGraphState) -> CognitiveGraphState:
    root = _root(state)
    date = state["date"]
    slug = state["slug"]
    topic = _title(state)
    path = root / "docs" / "reviews" / f"{date}-{slug}.md"
    content = f"""# Review: {topic}

Date: {date}
Status: open
Related proposal: {state["proposal"]["path"]}
Related receipt:
Related module:

## Summary

Initial cognitive workflow artifacts were generated. This review should be
updated after the next implementation action.

## Expected

The generated proposal should make the next action clearer.

## Actual

Pending implementation evidence.

## Evidence

- Idea: {state["idea"]["path"]}
- Note: {state["note"]["path"]}
- Proposal: {state["proposal"]["path"]}

## Classification

process issue

## Root Causes / Conditions

Pending real-world review.

## Lessons

Pending.

## Actions

Update this review after implementation and promote durable findings into a
lesson, module doc, ADR, test, or AGENTS.md.
"""
    return {
        "review": {
            "path": _write(path, content),
            "status": "open",
        }
    }


def lesson_node(state: CognitiveGraphState) -> CognitiveGraphState:
    root = _root(state)
    date = state["date"]
    slug = state["slug"]
    topic = _title(state)
    path = root / "docs" / "lessons" / f"{date}-{slug}.md"
    content = f"""# Lesson: {topic}

Date: {date}
Status: draft
Source reviews:
- {state["review"]["path"]}
Source ideas:
- {state["idea"]["path"]}
Affected modules:
- cognitive-engineering

## Lesson

Important project thoughts should move through an explicit workflow before they
become durable project rules or implementation commitments.

## Why It Matters

This prevents chat memory from masquerading as project knowledge.

## Evidence

Pending evidence from implementation and review.

## Rule / Heuristic

Use the smallest durable artifact that changes future action.

## Where It Should Live

AGENTS.md | module doc | ADR | checklist | test | code
"""
    return {
        "lesson": {
            "path": _write(path, content),
            "status": "draft",
        }
    }


def receipt_node(state: CognitiveGraphState) -> CognitiveGraphState:
    root = _root(state)
    stamp = state["stamp"]
    slug = state["slug"]
    path = root / "data" / "receipts" / "cognitive-graph" / f"{stamp}-{slug}.json"
    receipt = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "workflow": "langgraph_cognitive_engineering_v1",
        "topic": _title(state),
        "layer": state.get("layer") or "cognitive-engineering",
        "artifacts": {
            "idea": state["idea"]["path"],
            "note": state["note"]["path"],
            "proposal": state["proposal"]["path"],
            "review": state["review"]["path"],
            "lesson": state["lesson"]["path"],
        },
        "implementation": state["implementation"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"receipt_path": str(path)}


def final_node(state: CognitiveGraphState) -> CognitiveGraphState:
    return {
        "final": {
            "workflow": "langgraph_cognitive_engineering_v1",
            "topic": _title(state),
            "idea_path": state["idea"]["path"],
            "note_path": state["note"]["path"],
            "proposal_path": state["proposal"]["path"],
            "review_path": state["review"]["path"],
            "lesson_path": state["lesson"]["path"],
            "receipt_path": state["receipt_path"],
            "next_action": state["implementation"]["next_action"],
        }
    }


def build_cognitive_graph():
    graph = StateGraph(CognitiveGraphState)
    graph.add_node("capture_idea", capture_idea_node)
    graph.add_node("synthesize_note", synthesize_note_node)
    graph.add_node("draft_proposal", draft_proposal_node)
    graph.add_node("implementation_plan", implementation_plan_node)
    graph.add_node("review", review_node)
    graph.add_node("lesson", lesson_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "capture_idea")
    graph.add_edge("capture_idea", "synthesize_note")
    graph.add_edge("synthesize_note", "draft_proposal")
    graph.add_edge("draft_proposal", "implementation_plan")
    graph.add_edge("implementation_plan", "review")
    graph.add_edge("review", "lesson")
    graph.add_edge("lesson", "receipt")
    graph.add_edge("receipt", "final")
    graph.add_edge("final", END)
    return graph.compile()


cognitive_graph = build_cognitive_graph()


def run_cognitive_project_flow(
    *,
    topic: str,
    raw_thought: str | None = None,
    layer: str = "cognitive-engineering",
    source: str = "manual",
    root: Path | str = ROOT,
) -> dict[str, Any]:
    result = cognitive_graph.invoke(
        {
            "topic": topic,
            "raw_thought": raw_thought or topic,
            "layer": layer,
            "source": source,
            "root": str(root),
        }
    )
    return dict(result)
