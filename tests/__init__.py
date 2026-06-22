"""Test bootstrap: hermetic, offline, isolated from operator state.

Two global guards run once at test import:

1. Trading-state isolation: the store closes the Loop 3 feedback edge, so
   risk-gate and post-trade graph runs read/write a durable file by default.
   Tests must never touch the operator's real state or couple through it.

2. Offline hermes bridge: the hypothesis provider calls the hermes CLI when
   llm_enabled=True. Unit tests must not hit the network, so the bridge is
   forced to fail; the provider then falls back to its deterministic template
   (identical to the old stub behavior). Tests that want to exercise real LLM
   consumption patch run_hermes_single_query explicitly within their own scope.
"""

from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

if not os.environ.get("FINHARNESS_TRADING_STATE_PATH"):
    _state_dir = Path(tempfile.mkdtemp(prefix="finharness-test-state-"))
    os.environ["FINHARNESS_TRADING_STATE_PATH"] = str(_state_dir / "trading-state.json")


def _offline_hermes(*_args, **_kwargs):
    from finharness.hermes_bridge import HermesBridgeError

    raise HermesBridgeError("hermes bridge disabled in tests (offline)")


_hermes_guard = patch(
    "finharness.hermes_bridge.run_hermes_single_query", side_effect=_offline_hermes
)
_hermes_guard.start()
atexit.register(_hermes_guard.stop)
