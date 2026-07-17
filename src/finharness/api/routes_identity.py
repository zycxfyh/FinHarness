"""Narrow authenticated browser mutation identity surface."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from finharness.identity import (
    BROWSER_MUTATION_BINDING_HEADER,
    BrowserMutationBindingError,
    BrowserMutationIdentityBinding,
    OperatorContext,
    browser_mutation_identity_binding,
    require_authenticated_operator,
)

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get(
    "/browser-mutation-binding",
    response_model=BrowserMutationIdentityBinding,
)
async def get_browser_mutation_binding(
    response: Response,
    context: Annotated[
        OperatorContext,
        Depends(require_authenticated_operator),
    ],
) -> BrowserMutationIdentityBinding:
    """Return only the current server-derived browser retry binding."""

    try:
        binding = browser_mutation_identity_binding(context)
    except BrowserMutationBindingError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": exc.code,
                "message": "A reusable browser mutation binding is unavailable.",
                "execution_allowed": False,
                "capital_authority": None,
            },
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization, Cookie"
    response.headers[BROWSER_MUTATION_BINDING_HEADER] = binding.binding_id
    return binding
