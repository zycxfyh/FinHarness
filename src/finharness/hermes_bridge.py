"""Narrow subprocess bridge to the local hermes-agent CLI.

FinHarness uses hermes-agent only in generator seats (drafting), never as an
evaluator. The bridge is deliberately tiny: one prompt in, one text response
out, strict timeout, least-capability toolset (web_search only — no terminal,
no file tools, so drafts cannot leave side effects), no secrets in the prompt.
Failures raise HermesBridgeError so callers can fall back to deterministic
templates (fail-closed).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_HERMES_BIN = "hermes"
# Generator seats get the least-capability toolset hermes accepts (web_search
# only): no terminal and no file tools, so a draft cannot leave side effects
# in the repo. "none" is not a valid hermes toolset.
DEFAULT_TOOLSETS = "search"


class HermesBridgeError(RuntimeError):
    """Raised when the hermes CLI call fails, times out, or returns garbage."""


def run_hermes_single_query(
    prompt: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    hermes_bin: str = DEFAULT_HERMES_BIN,
    toolsets: str = DEFAULT_TOOLSETS,
) -> str:
    """Run one non-interactive hermes query (`hermes -z`) and return stdout."""
    try:
        completed = subprocess.run(  # noqa: S603 -- local hermes CLI adapter, shell disabled.
            [hermes_bin, "-t", toolsets, "-z", prompt],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HermesBridgeError(f"hermes binary not found: {hermes_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HermesBridgeError(f"hermes query timed out after {timeout_seconds}s") from exc
    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "")[-500:]
        raise HermesBridgeError(
            f"hermes exited {completed.returncode}: {stderr_tail}"
        )
    output = (completed.stdout or "").strip()
    if not output:
        raise HermesBridgeError("hermes returned empty output")
    return output


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first top-level JSON object from model output.

    Tolerates surrounding prose and ```json fences; raises HermesBridgeError
    when no parseable object exists.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    brace_start = text.find("{")
    if brace_start != -1:
        candidates.append(text[brace_start : text.rfind("}") + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise HermesBridgeError("no JSON object found in hermes output")
