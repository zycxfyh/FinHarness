"""FastAPI application for the FinHarness governed state surface."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from finharness.api.keyed_mutation_capabilities import (
    KeyedMutationCapabilityError,
    KeyedMutationRouteCapability,
    KeyedMutationRouteMode,
    MatchedApiRoute,
    audit_keyed_mutation_route_capabilities,
    identity_mutation_resolver_contract_maps,
    load_keyed_mutation_route_capabilities,
    match_api_route,
)
from finharness.api.routes_action_intents import router as action_intent_router
from finharness.api.routes_agent_authority_grants import (
    router as agent_authority_grant_router,
)
from finharness.api.routes_capital_mandates import router as capital_mandate_router
from finharness.api.routes_cockpit import router as cockpit_router
from finharness.api.routes_execution import router as execution_router
from finharness.api.routes_identity import router as identity_router
from finharness.api.routes_ips import router as ips_router
from finharness.api.routes_paper_validation import router as paper_validation_router
from finharness.api.routes_proposals import (
    identity_mutation_reconciliation_dispatcher_contracts,
)
from finharness.api.routes_proposals import (
    router as proposal_router,
)
from finharness.api.routes_review import router as review_router
from finharness.api.routes_risk import router as risk_router
from finharness.api.routes_state import router as state_router
from finharness.execution.capabilities import (
    DEFAULT_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
    ExecutionCapabilityDeniedError,
)
from finharness.identity import (
    BROWSER_MUTATION_BINDING_HEADER,
    IDEMPOTENCY_HEADER,
    IDEMPOTENCY_SEMANTIC_HEADERS,
    IDEMPOTENT_REPLAY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    BrowserMutationBindingError,
    IdentityMutationClaim,
    IdentityMutationError,
    IdentityProvider,
    OperatorContext,
    begin_identity_mutation,
    complete_identity_mutation,
    replay_identity_mutation,
    request_body_sha256,
    validate_browser_mutation_binding_header,
    write_identity_receipt,
)
from finharness.local_operator import LocalOperatorContext
from finharness.observability import TRACE_HEADER, start_local_span, trace_context_from_headers
from finharness.project_paths import ROOT
from finharness.readiness import (
    CapitalTruthReadiness,
    OperationalReadiness,
    capital_truth_readiness,
    operational_readiness,
)
from finharness.runtime_log import configure_logging, get_logger
from finharness.statecore.store import (
    StateCoreStoreError,
    ensure_state_core_schema,
    state_core_db_path,
)

configure_logging()
logger = get_logger(__name__)

_OPTIONAL_DATA_IMPORTS = {
    "beancount",
    "beanquery",
    "nautilus_trader",
    "pandera",
    "yfinance",
}

class _IdempotentRequestTooLarge(RuntimeError):
    """Raised before a route when a keyed request exceeds its governed bound."""


class _IdempotentResponseTooLarge(RuntimeError):
    """Raised after a route when its response cannot be journaled safely."""


async def _read_bounded_request_body(request: Request, *, max_bytes: int) -> bytes:
    """Read and cache a keyed request without exceeding the configured bound."""

    declared_length = request.headers.get("content-length")
    if (
        declared_length
        and declared_length.isdecimal()
        and int(declared_length) > max_bytes
    ):
        raise _IdempotentRequestTooLarge

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        chunk_bytes = bytes(chunk)
        total += len(chunk_bytes)
        if total > max_bytes:
            raise _IdempotentRequestTooLarge
        chunks.append(chunk_bytes)

    body = b"".join(chunks)
    # Starlette replays this cached body to the downstream route.
    request._body = body
    return body


def _canonical_request_target(request: Request) -> str:
    """Bind the exact path and raw query string that select mutation semantics."""

    raw_query = request.scope.get("query_string", b"")
    if not isinstance(raw_query, bytes) or not raw_query:
        return request.url.path
    return f"{request.url.path}?{raw_query.decode('latin-1')}"


def _semantic_request_headers(request: Request) -> dict[str, str]:
    """Select only headers whose values can alter the governed mutation."""

    return {
        name: request.headers[name].strip()
        for name in IDEMPOTENCY_SEMANTIC_HEADERS
        if name in request.headers
    }


async def _buffer_response(response: Response, *, max_bytes: int) -> tuple[Response, bytes]:
    """Materialize a bounded API response so it can be safely replayed."""

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        body = bytes(response.body)
        if len(body) > max_bytes:
            raise _IdempotentResponseTooLarge
    else:
        chunks: list[bytes] = []
        total = 0
        async for chunk in body_iterator:
            chunk_bytes = bytes(chunk)
            total += len(chunk_bytes)
            if total > max_bytes:
                raise _IdempotentResponseTooLarge
            chunks.append(chunk_bytes)
        body = b"".join(chunks)

    headers = dict(response.headers)
    headers.pop("content-length", None)
    buffered = Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )
    return buffered, body


def _protocol_response(claim: IdentityMutationClaim) -> Response:
    if claim.disposition == "replay":
        status_code, body, content_type = replay_identity_mutation(claim.payload)
        headers = {IDEMPOTENT_REPLAY_HEADER: "true"}
        if content_type:
            headers["content-type"] = content_type
        return Response(content=body, status_code=status_code, headers=headers)
    code = (
        "idempotency_key_reused_for_different_request"
        if claim.disposition == "conflict"
        else "mutation_outcome_ambiguous"
    )
    message = (
        "The key is already bound to a different request."
        if claim.disposition == "conflict"
        else "A prior attempt may have committed; automatic retry is denied pending reconciliation."
    )
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": code,
                "message": message,
                "identity_receipt_id": claim.receipt_id,
                "execution_allowed": False,
            }
        },
    )


def _typed_capability_contract_denial(
    api: FastAPI,
    capability: KeyedMutationRouteCapability,
    *,
    trace_id: str,
) -> JSONResponse | None:
    if capability.mode is not KeyedMutationRouteMode.TYPED_DOMAIN_RECONCILIATION:
        return None
    contract = api.state.identity_mutation_resolver_contracts_by_route.get(
        (capability.method, capability.canonical_path_template)
    )
    matches = (
        contract is not None
        and contract.capability_id == capability.capability_id
        and contract.resolver_id == capability.resolver_id
    )
    if matches:
        return None
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "keyed_mutation_capability_invalid",
                "message": (
                    "The route capability differs from its "
                    "executable resolver contract."
                ),
                "trace_id": trace_id,
                "method": capability.method,
                "canonical_path_template": capability.canonical_path_template,
                "capability_id": capability.capability_id,
                "execution_allowed": False,
            }
        },
    )


def _browser_mutation_binding_denial(
    request: Request,
    context: OperatorContext,
    *,
    trace_id: str,
) -> JSONResponse | None:
    claimed_binding_id = request.headers.get(BROWSER_MUTATION_BINDING_HEADER)
    if claimed_binding_id is None:
        return None
    try:
        binding = validate_browser_mutation_binding_header(
            context,
            claimed_binding_id,
        )
    except BrowserMutationBindingError as exc:
        return JSONResponse(
            status_code=(
                403
                if exc.code == "browser_mutation_binding_expired"
                else 409
            ),
            content={
                "detail": {
                    "code": exc.code,
                    "message": (
                        "The browser mutation binding does not match "
                        "current server authentication."
                    ),
                    "trace_id": trace_id,
                    "execution_allowed": False,
                    "capital_authority": None,
                }
            },
        )
    request.state.browser_mutation_binding_id = binding.binding_id
    return None


def _match_keyed_mutation_route(
    api: FastAPI,
    request: Request,
    *,
    trace_id: str,
) -> tuple[MatchedApiRoute | None, JSONResponse | None]:
    try:
        return match_api_route(api, request.scope), None
    except KeyedMutationCapabilityError:
        logger.exception(
            "keyed_mutation_route_match_invalid",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            execution_allowed=False,
        )
        return None, JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "keyed_mutation_capability_invalid",
                    "message": "The keyed mutation route could not be resolved safely.",
                    "trace_id": trace_id,
                    "method": request.method,
                    "execution_allowed": False,
                }
            },
        )


def _admit_browser_binding_and_route(
    api: FastAPI,
    request: Request,
    context: OperatorContext,
    *,
    trace_id: str,
) -> tuple[MatchedApiRoute | None, JSONResponse | None]:
    binding_denial = _browser_mutation_binding_denial(
        request,
        context,
        trace_id=trace_id,
    )
    if binding_denial is not None:
        return None, binding_denial
    return _match_keyed_mutation_route(
        api,
        request,
        trace_id=trace_id,
    )


async def _call_with_identity_protocol(
    api: FastAPI,
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    trace_id: str,
) -> tuple[Response, IdentityMutationClaim | None]:
    write_method = request.method not in {"GET", "HEAD", "OPTIONS"}
    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    if not write_method or not idempotency_key:
        return await call_next(request), None
    provider = getattr(api.state, "identity_provider", None)
    context = (
        await provider.authenticate(request) if isinstance(provider, IdentityProvider) else None
    )
    if not isinstance(context, OperatorContext):
        return await call_next(request), None
    request.state.operator_context = context
    matched_route, admission_denial = _admit_browser_binding_and_route(
        api,
        request,
        context,
        trace_id=trace_id,
    )
    if admission_denial is not None:
        return admission_denial, None
    if matched_route is None:
        # Preserve the router's normal 404/405 or mounted-route behavior.
        return await call_next(request), None
    registry = api.state.keyed_mutation_route_capabilities
    capability = registry.by_route(
        matched_route.method,
        matched_route.canonical_path_template,
    )
    if capability is None:
        return (
            JSONResponse(
                status_code=409,
                content={
                    "detail": {
                        "code": "keyed_mutation_route_unregistered",
                        "message": "This route has no keyed-mutation recovery capability.",
                        "trace_id": trace_id,
                        "method": matched_route.method,
                        "canonical_path_template": (
                            matched_route.canonical_path_template
                        ),
                        "execution_allowed": False,
                    }
                },
            ),
            None,
        )
    capability_denial = _typed_capability_contract_denial(
        api,
        capability,
        trace_id=trace_id,
    )
    if capability_denial is not None:
        return capability_denial, None
    if capability.mode is KeyedMutationRouteMode.KEYED_MUTATION_PROHIBITED:
        return (
            JSONResponse(
                status_code=409,
                content={
                    "detail": {
                        "code": "keyed_mutation_prohibited",
                        "message": "This route does not admit keyed mutation.",
                        "trace_id": trace_id,
                        "method": matched_route.method,
                        "canonical_path_template": (
                            matched_route.canonical_path_template
                        ),
                        "capability_id": capability.capability_id,
                        "execution_allowed": False,
                    }
                },
            ),
            None,
        )
    try:
        request_body = await _read_bounded_request_body(
            request,
            max_bytes=capability.max_request_bytes,
        )
    except _IdempotentRequestTooLarge:
        logger.warning(
            "idempotent_request_exceeds_limit",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            limit_bytes=capability.max_request_bytes,
            execution_allowed=False,
        )
        return (
            JSONResponse(
                status_code=413,
                content={
                    "detail": {
                        "code": "idempotent_request_too_large",
                        "message": ("The keyed mutation request exceeds the supported size."),
                        "limit_bytes": capability.max_request_bytes,
                        "trace_id": trace_id,
                        "execution_allowed": False,
                    }
                },
            ),
            None,
        )

    receipt_root = (
        Path(
            getattr(
                api.state,
                "state_core_receipt_root",
                ROOT / "data" / "receipts" / "state-core",
            )
        )
        / "identity"
    )
    try:
        claim = begin_identity_mutation(
            receipt_root,
            context=context,
            method=request.method,
            path=request.url.path,
            request_target=_canonical_request_target(request),
            semantic_headers=_semantic_request_headers(request),
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            body_sha256=request_body_sha256(request_body),
            route_capability=capability.receipt_binding(),
        )
    except IdentityMutationError as exc:
        logger.warning(
            "invalid_idempotency_contract",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            error_message=str(exc),
            execution_allowed=False,
        )
        return (
            JSONResponse(
                status_code=409,
                content={
                    "detail": {
                        "code": "invalid_idempotency_contract",
                        "message": ("The mutation identity receipt could not be validated."),
                        "trace_id": trace_id,
                        "execution_allowed": False,
                    }
                },
            ),
            None,
        )
    if claim.disposition != "execute":
        return _protocol_response(claim), claim

    # Route-owned domain writes bind their canonical effect to this claim.
    request.state.identity_mutation_claim = claim
    response = await call_next(request)
    try:
        response, body = await _buffer_response(
            response,
            max_bytes=capability.max_response_bytes,
        )
    except _IdempotentResponseTooLarge:
        logger.error(
            "idempotent_response_exceeds_limit",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            identity_receipt_id=claim.receipt_id,
            limit_bytes=capability.max_response_bytes,
            mutation_outcome_ambiguous=True,
            execution_allowed=False,
        )
        return (
            JSONResponse(
                status_code=503,
                content={
                    "detail": {
                        "code": "idempotent_response_too_large",
                        "message": (
                            "The mutation response exceeded the journal size limit; "
                            "the mutation outcome requires reconciliation."
                        ),
                        "identity_receipt_id": claim.receipt_id,
                        "limit_bytes": capability.max_response_bytes,
                        "trace_id": trace_id,
                        "execution_allowed": False,
                    }
                },
            ),
            claim,
        )

    completed = complete_identity_mutation(
        claim,
        trace_id=trace_id,
        status_code=response.status_code,
        response_body=body,
        content_type=response.headers.get("content-type"),
    )
    replay_claim = IdentityMutationClaim("replay", claim.receipt_id, claim.receipt_path, completed)
    return response, replay_claim


def _bind_identity_receipt_header(
    api: FastAPI,
    request: Request,
    response: Response,
    claim: IdentityMutationClaim | None,
    *,
    trace_id: str,
) -> None:
    if claim is not None:
        response.headers[IDENTITY_RECEIPT_HEADER] = claim.receipt_id
        return
    context = getattr(request.state, "operator_context", None)
    if (
        not isinstance(context, OperatorContext)
        or request.method in {"GET", "HEAD", "OPTIONS"}
        or response.status_code >= 400
    ):
        return
    root = (
        Path(
            getattr(
                api.state,
                "state_core_receipt_root",
                ROOT / "data" / "receipts" / "state-core",
            )
        )
        / "identity"
    )
    receipt_path = write_identity_receipt(
        root,
        context=context,
        method=request.method,
        path=request.url.path,
        trace_id=trace_id,
        status_code=response.status_code,
    )
    response.headers[IDENTITY_RECEIPT_HEADER] = receipt_path.stem


def _bind_browser_mutation_response_header(
    request: Request,
    response: Response,
) -> None:
    binding_id = getattr(request.state, "browser_mutation_binding_id", None)
    if isinstance(binding_id, str):
        response.headers[BROWSER_MUTATION_BINDING_HEADER] = binding_id


def _load_optional_data_routers():
    """Load data routes only when their owned dependency group is installed."""
    try:
        from finharness.api.routes_data_catalog import router as data_catalog_router
        from finharness.api.routes_data_quality import router as data_quality_router
    except ModuleNotFoundError as exc:
        if exc.name not in _OPTIONAL_DATA_IMPORTS:
            raise
        return (), exc.name
    return (data_catalog_router, data_quality_router), None


def _register_readiness_routes(api: FastAPI) -> None:
    @api.get("/ready", tags=["health"], response_model=OperationalReadiness)
    async def ready() -> JSONResponse:
        result = operational_readiness(
            engine=getattr(api.state, "state_core_engine", None),
            db_path=api.state.state_core_path,
            receipt_root=Path(
                getattr(
                    api.state,
                    "state_core_receipt_root",
                    ROOT / "data" / "receipts" / "state-core",
                )
            ),
        )
        return JSONResponse(
            status_code={"ready": 200}.get(result.status, 503),
            content=result.model_dump(mode="json"),
        )

    @api.get("/ready/truth", tags=["health"], response_model=CapitalTruthReadiness)
    async def truth_ready() -> JSONResponse:
        result = capital_truth_readiness(
            engine=getattr(api.state, "state_core_engine", None),
            db_path=api.state.state_core_path,
            receipt_root=Path(
                getattr(
                    api.state,
                    "state_core_receipt_root",
                    ROOT / "data" / "receipts" / "state-core",
                )
            ),
        )
        return JSONResponse(
            status_code={"usable": 200}.get(result.status, 503),
            content=result.model_dump(mode="json"),
        )


def create_app(
    *,
    state_core_engine: Engine | None = None,
    state_core_path: str | None = None,
    receipt_root: str | None = None,
    market_data_receipt_root: str | None = None,
    local_operator_context: LocalOperatorContext | None = None,
    identity_provider: IdentityProvider | None = None,
    execution_capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> FastAPI:
    data_routers, missing_data_dependency = _load_optional_data_routers()
    api = FastAPI(
        title="FinHarness State API",
        summary="Governed cockpit API -- read + explicit local writes.",
        version="0.1.0",
    )
    if state_core_engine is not None:
        ensure_state_core_schema(state_core_engine)
        api.state.state_core_engine = state_core_engine
    api.state.state_core_path = state_core_db_path(state_core_path)
    if receipt_root is not None:
        api.state.state_core_receipt_root = receipt_root
    if market_data_receipt_root is not None:
        api.state.market_data_receipt_root = market_data_receipt_root
    api.state.local_operator_context = local_operator_context
    api.state.identity_provider = identity_provider or (
        local_operator_context.identity_provider()
        if isinstance(local_operator_context, LocalOperatorContext)
        else None
    )
    api.state.execution_capabilities = execution_capabilities
    api.state.keyed_mutation_route_capabilities = (
        load_keyed_mutation_route_capabilities()
    )
    resolver_contracts = identity_mutation_reconciliation_dispatcher_contracts()
    resolver_contracts_by_route, _resolver_contracts_by_id = (
        identity_mutation_resolver_contract_maps(resolver_contracts)
    )
    api.state.identity_mutation_resolver_contracts = resolver_contracts
    api.state.identity_mutation_resolver_contracts_by_route = (
        resolver_contracts_by_route
    )
    api.state.data_surface_available = missing_data_dependency is None
    api.state.data_surface_missing_dependency = missing_data_dependency

    @api.middleware("http")
    async def log_request(request: Request, call_next):
        started = perf_counter()
        trace_context = trace_context_from_headers(request.headers)
        trace_id = trace_context.trace_id
        request.state.trace_id = trace_id
        mutation_claim: IdentityMutationClaim | None = None
        with start_local_span(
            "finharness.api.request",
            trace_id=trace_id,
            attributes={
                "http.request.method": request.method,
                "url.path": request.url.path,
                "finharness.trace_id_supplied": trace_context.accepted_supplied,
            },
        ) as span:
            response, mutation_claim = await _call_with_identity_protocol(
                api, request, call_next, trace_id=trace_id
            )
            span.set_attribute("http.response.status_code", response.status_code)
        _bind_identity_receipt_header(api, request, response, mutation_claim, trace_id=trace_id)
        _bind_browser_mutation_response_header(request, response)
        response.headers[TRACE_HEADER] = trace_id
        logger.info(
            "state_api_request",
            trace_id=trace_id,
            trace_id_supplied=trace_context.accepted_supplied,
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
                "data_surface": (
                    "available" if api.state.data_surface_available else "optional-not-installed"
                ),
            },
            "non_claims": [
                "Liveness signal only.",
                "Not dependency readiness.",
                "Not capital truth readiness.",
                "Not release approval.",
                "Not execution authorization.",
            ],
        }

    _register_readiness_routes(api)

    @api.exception_handler(StateCoreStoreError)
    async def state_core_error(_request: Request, exc: StateCoreStoreError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "execution_allowed": False,
            },
        )

    @api.exception_handler(OSError)
    async def local_persistence_error(_request: Request, exc: OSError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "local_persistence_failure",
                    "message": str(exc),
                },
                "execution_allowed": False,
            },
        )

    @api.exception_handler(ExecutionCapabilityDeniedError)
    async def execution_capability_denied(
        _request: Request,
        exc: ExecutionCapabilityDeniedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "code": "execution_capability_denied",
                    "capability": exc.capability,
                    "message": str(exc),
                }
            },
        )

    api.include_router(cockpit_router)
    api.include_router(identity_router)
    api.include_router(state_router)
    api.include_router(proposal_router)
    api.include_router(review_router)
    api.include_router(risk_router)
    api.include_router(action_intent_router)
    api.include_router(paper_validation_router)
    api.include_router(agent_authority_grant_router)
    api.include_router(capital_mandate_router)
    api.include_router(ips_router)
    for data_router in data_routers:
        api.include_router(data_router)
    api.include_router(execution_router)
    api.state.keyed_mutation_capability_audit = (
        audit_keyed_mutation_route_capabilities(
            api,
            api.state.keyed_mutation_route_capabilities,
            dispatcher_contracts=resolver_contracts,
        )
    )
    frontend_dir = ROOT / "frontend"
    if frontend_dir.exists():
        api.mount(
            "/cockpit",
            StaticFiles(directory=frontend_dir, html=True),
            name="cockpit",
        )
    return api


app = create_app()
