"""Shared FastAPI dependencies for the FinHarness local API."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine

from finharness.execution.capabilities import (
    DEFAULT_EXECUTION_CAPABILITIES,
    DENY_ALL_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from finharness.identity import OperatorContext
from finharness.local_operator import require_write_capability
from finharness.project_paths import MARKET_DATA_RECEIPT_ROOT as DEFAULT_MARKET_DATA_RECEIPT_ROOT
from finharness.project_paths import ROOT
from finharness.statecore.store import ensure_state_core_schema, open_state_core

DEFAULT_STATE_CORE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "state-core"


async def get_state_core_engine(request: Request) -> Engine:
    engine = getattr(request.app.state, "state_core_engine", None)
    if engine is None:
        engine = open_state_core()
        # An existing database may predate tables added in later slices; create
        # any missing ones so cockpit reads do not 500 with "no such table".
        ensure_state_core_schema(engine)
        request.app.state.state_core_engine = engine
    return engine


async def get_state_core_receipt_root(request: Request) -> Path:
    return Path(
        getattr(
            request.app.state,
            "state_core_receipt_root",
            DEFAULT_STATE_CORE_RECEIPT_ROOT,
        )
    )


EngineDependency = Annotated[Engine, Depends(get_state_core_engine)]
ReceiptRootDependency = Annotated[Path, Depends(get_state_core_receipt_root)]
WriteCapabilityDependency = Annotated[
    OperatorContext,
    Depends(require_write_capability),
]


async def get_execution_capabilities(request: Request) -> ExecutionCapabilities:
    capabilities = getattr(
        request.app.state,
        "execution_capabilities",
        DEFAULT_EXECUTION_CAPABILITIES,
    )
    if not isinstance(capabilities, ExecutionCapabilities):
        return DENY_ALL_EXECUTION_CAPABILITIES
    return capabilities


ExecutionCapabilitiesDependency = Annotated[
    ExecutionCapabilities,
    Depends(get_execution_capabilities),
]


async def get_market_data_receipt_root(request: Request) -> Path:
    return Path(
        getattr(
            request.app.state,
            "market_data_receipt_root",
            DEFAULT_MARKET_DATA_RECEIPT_ROOT,
        )
    )


MarketDataReceiptRootDependency = Annotated[Path, Depends(get_market_data_receipt_root)]
