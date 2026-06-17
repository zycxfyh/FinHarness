"""FastAPI application for the read-only FinHarness state surface."""

from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from finharness.api.routes_proposals import router as proposal_router
from finharness.api.routes_state import router as state_router
from finharness.runtime_log import configure_logging, get_logger
from finharness.statecore.store import StateCoreStoreError

configure_logging()
logger = get_logger(__name__)


def create_app(
    *,
    state_core_engine: Engine | None = None,
    receipt_root: str | None = None,
) -> FastAPI:
    api = FastAPI(
        title="FinHarness State API",
        summary="Read-only cockpit API for state snapshots, receipts, and diffs.",
        version="0.1.0",
    )
    if state_core_engine is not None:
        api.state.state_core_engine = state_core_engine
    if receipt_root is not None:
        api.state.state_core_receipt_root = receipt_root

    @api.middleware("http")
    async def log_request(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        logger.info(
            "state_api_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            execution_allowed=False,
        )
        return response

    @api.exception_handler(StateCoreStoreError)
    async def state_core_error(_request: Request, exc: StateCoreStoreError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "execution_allowed": False,
            },
        )

    api.include_router(state_router)
    api.include_router(proposal_router)
    return api


app = create_app()
