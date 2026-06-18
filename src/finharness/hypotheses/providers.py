"""Draft-provider helpers for hypothesis generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from finharness.hypotheses._constants import (
    ALLOWED_DRAFT_CHECK_TYPES,
    HERMES_DRAFT_PROMPT_VERSION,
)
from finharness.interpretation import InterpretationRecord
from finharness.market_data import display_path


def hypothesis_draft_root() -> Path:
    from finharness import hypotheses as hypotheses_package

    return hypotheses_package.HERMES_DRAFT_ROOT


class HypothesisDraftProvider(Protocol):
    """Optional draft provider interface for future LLM integrations."""

    provider_name: str

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        """Return optional draft fields for a hypothesis record."""


class NullHypothesisDraftProvider:
    """Default provider: deterministic layer, no LLM call."""

    provider_name = "none"

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        return {}


def build_hermes_hypothesis_prompt(interpretation: InterpretationRecord) -> str:
    facts = "\n".join(f"- {item}" for item in interpretation.source_facts[:6])
    counter = "\n".join(f"- {item}" for item in interpretation.counterevidence[:4])
    return (
        "You are a research assistant drafting ONE falsifiable market-research "
        "hypothesis for an evidence-governed harness. This is research drafting "
        "only: no trade recommendations, no buy/sell/hold language, no price "
        "targets, no position sizing, no execution instructions. The draft is "
        "checked by deterministic quality gates and never authorizes any action.\n\n"
        f"Symbol: {interpretation.symbol}\n"
        f"Claim under interpretation: {interpretation.claim}\n"
        f"Inference: {interpretation.inference}\n"
        f"Impact paths: {', '.join(interpretation.impact_paths[:4])}\n"
        f"Horizon: {interpretation.horizon}\n"
        f"Source facts:\n{facts or '- none provided'}\n"
        f"Known counterevidence:\n{counter or '- none provided'}\n\n"
        "Respond with ONLY one JSON object, no prose, with exactly these keys:\n"
        "{\n"
        '  "hypothesis": "one falsifiable if-then statement tied to the claim",\n'
        '  "mechanism": "one sentence on the causal transmission path",\n'
        '  "expected_observations": ["2-4 observations that would support it"],\n'
        '  "disconfirming_observations": ["2-4 observations that would falsify it"],\n'
        '  "assumptions": ["2-3 assumptions; at least one must state how event '
        'timing is separated from market reaction"]\n'
        "}"
    )


def sanitize_hermes_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only contract keys with the right shapes; drop everything else.

    The downstream quality gates re-check content (blocked language,
    falsifiability fields), so this only enforces structure, not safety.
    """
    draft: dict[str, Any] = {}
    if isinstance(payload.get("hypothesis"), str) and payload["hypothesis"].strip():
        draft["hypothesis"] = payload["hypothesis"].strip()
    if isinstance(payload.get("mechanism"), str) and payload["mechanism"].strip():
        draft["mechanism"] = payload["mechanism"].strip()
    for key in ("expected_observations", "disconfirming_observations", "assumptions"):
        value = payload.get(key)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                draft[key] = items[:6]
    plan = payload.get("validation_plan")
    if isinstance(plan, list):
        valid = [
            item
            for item in plan
            if isinstance(item, dict)
            and item.get("check_type") in ALLOWED_DRAFT_CHECK_TYPES
        ]
        if valid and len(valid) == len(plan):
            draft["validation_plan"] = valid
    return draft


class HermesHypothesisDraftProvider:
    """Generator-seat LLM drafting via the local hermes-agent CLI.

    Fail-closed contract: any bridge, parsing, or sanitization failure returns
    a draft without content keys, so formulate_hypothesis_record falls back to
    the deterministic template field by field. The raw exchange is persisted
    under data/cache/hermes-drafts/ and referenced via draft_ref.
    """

    provider_name = "hermes-agent"

    def __init__(
        self,
        *,
        hermes_root: str | Path = "/root/projects/hermes-agent",
        timeout_seconds: int = 180,
    ) -> None:
        self.hermes_root = Path(hermes_root)
        self.timeout_seconds = timeout_seconds

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        from finharness.hermes_bridge import (
            HermesBridgeError,
            extract_json_object,
            run_hermes_single_query,
        )

        prompt = build_hermes_hypothesis_prompt(interpretation)
        base: dict[str, Any] = {
            "provider": self.provider_name,
            "prompt_template_version": HERMES_DRAFT_PROMPT_VERSION,
            "source_interpretation_id": interpretation.interpretation_id,
        }
        raw_output: str | None = None
        try:
            raw_output = run_hermes_single_query(
                prompt, timeout_seconds=self.timeout_seconds
            )
            parsed = extract_json_object(raw_output)
            draft = sanitize_hermes_draft(parsed)
            base.update(draft)
            base["enabled"] = True
        except HermesBridgeError as exc:
            base["enabled"] = False
            base["error"] = str(exc)
        base["draft_ref"] = self._persist_draft(
            interpretation=interpretation, prompt=prompt, raw_output=raw_output, draft=base
        )
        return base

    def _persist_draft(
        self,
        *,
        interpretation: InterpretationRecord,
        prompt: str,
        raw_output: str | None,
        draft: dict[str, Any],
    ) -> str | None:
        try:
            draft_root = hypothesis_draft_root()
            draft_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            path = (
                draft_root
                / f"{stamp}-{interpretation.interpretation_id}-{uuid4().hex[:8]}.json"
            )
            path.write_text(
                json.dumps(
                    {
                        "prompt_template_version": HERMES_DRAFT_PROMPT_VERSION,
                        "interpretation_id": interpretation.interpretation_id,
                        "prompt": prompt,
                        "raw_output": raw_output,
                        "draft": {k: v for k, v in draft.items() if k != "draft_ref"},
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return display_path(path)
        except OSError:
            return None
