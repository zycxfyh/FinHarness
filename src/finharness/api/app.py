"""FastAPI application for the read-only FinHarness state surface."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from finharness.api.routes_cockpit import router as cockpit_router
from finharness.api.routes_proposals import router as proposal_router
from finharness.api.routes_review import router as review_router
from finharness.api.routes_state import router as state_router
from finharness.market_data import ROOT
from finharness.runtime_log import configure_logging, get_logger
from finharness.statecore.store import StateCoreStoreError, ensure_state_core_schema

configure_logging()
logger = get_logger(__name__)


def _trace_id_for_request(request: Request) -> str:
    supplied = request.headers.get("x-finharness-trace-id")
    if supplied and supplied.strip():
        return supplied.strip()
    return f"trace_{uuid4().hex}"


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
        ensure_state_core_schema(state_core_engine)
        api.state.state_core_engine = state_core_engine
    if receipt_root is not None:
        api.state.state_core_receipt_root = receipt_root

    @api.middleware("http")
    async def log_request(request: Request, call_next):
        started = perf_counter()
        trace_id = _trace_id_for_request(request)
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-FinHarness-Trace-Id"] = trace_id
        logger.info(
            "state_api_request",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            execution_allowed=False,
        )
        return response

    @api.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "execution_allowed": False,
            "checks": {
                "api": "ok",
            },
            "non_claims": [
                "Health check only.",
                "Not release approval.",
                "Not execution authorization.",
            ],
        }

    @api.exception_handler(StateCoreStoreError)
    async def state_core_error(_request: Request, exc: StateCoreStoreError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "execution_allowed": False,
            },
        )

    api.include_router(cockpit_router)
    api.include_router(state_router)
    api.include_router(proposal_router)
    api.include_router(review_router)
    frontend_dir = ROOT / "frontend"
    if frontend_dir.exists():
        api.mount(
            "/cockpit",
            StaticFiles(directory=frontend_dir, html=True),
            name="cockpit",
        )
    return api


app = create_app()
