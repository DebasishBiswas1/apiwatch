"""
endpoints.py — CRUD routes for monitored endpoints.

Every route here requires authentication via Depends(get_current_user).
Every database operation goes through endpoints_repo which enforces
tenant scoping. The route handlers themselves are intentionally thin —
they handle HTTP concerns only: parse input, call repo, return output.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1 import endpoints_repo
from app.db.session import get_db
from app.models.user import User
from app.schemas.endpoint import (
    EndpointCreateRequest,
    EndpointUpdateRequest,
    EndpointResponse,
)

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


# ── Shared helper ─────────────────────────────────────────────────────────────

async def get_endpoint_or_404(
    endpoint_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> endpoints_repo.MonitoredEndpoint:
    """
    Fetch an endpoint by ID scoped to the current tenant.
    Raises 404 if not found OR if it belongs to another tenant.

    Why a helper instead of repeating this in every route?
      GET, PATCH, and DELETE all need the same "fetch or 404" logic.
      Centralising it means the security behaviour is consistent and
      tested in one place. If we later add soft-delete awareness or
      audit logging to this lookup, we change it once here.
    """
    endpoint = await endpoints_repo.get_endpoint_by_id(
        db=db,
        endpoint_id=endpoint_id,
        organization_id=current_user.organization_id,
    )
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )
    return endpoint


# ── POST /api/v1/endpoints ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=EndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    body: EndpointCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EndpointResponse:
    """
    Register a new URL for monitoring.

    FastAPI resolves the two Depends() before calling this function:
      - get_db: opens a fresh AsyncSession for this request
      - get_current_user: verifies JWT, returns the User object
        If the JWT is missing or invalid, FastAPI returns 401
        before this function is ever called.

    current_user.organization_id is the tenant discriminator.
    We never read org_id from the request body — always from the
    verified token. The client cannot forge their tenant identity.
    """
    endpoint = await endpoints_repo.create_endpoint(
        db=db,
        organization_id=current_user.organization_id,
        data=body,
    )
    return EndpointResponse.model_validate(endpoint)


# ── GET /api/v1/endpoints ─────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[EndpointResponse],
)
async def list_endpoints(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EndpointResponse]:
    """
    List all monitored endpoints for the current tenant.

    Returns an empty list [] if the tenant has no endpoints yet.
    Never returns endpoints from other tenants — the repo query
    filters on organization_id from the verified JWT.

    response_model=list[EndpointResponse]: FastAPI validates and
    serialises each item in the list through EndpointResponse,
    stripping any ORM fields not in the schema.
    """
    endpoints = await endpoints_repo.list_endpoints(
        db=db,
        organization_id=current_user.organization_id,
    )
    return [EndpointResponse.model_validate(e) for e in endpoints]


# ── GET /api/v1/endpoints/{endpoint_id} ──────────────────────────────────────

@router.get(
    "/{endpoint_id}",
    response_model=EndpointResponse,
)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EndpointResponse:
    """
    Get a single endpoint by ID.

    endpoint_id: uuid.UUID in the function signature tells FastAPI
    to parse and validate the path parameter as a UUID automatically.
    A non-UUID value in the URL (e.g. /endpoints/not-a-uuid) returns
    422 Unprocessable Entity before this function runs.

    get_endpoint_or_404 handles both "does not exist" and "belongs
    to another tenant" with the same 404 — no information leaked.
    """
    endpoint = await get_endpoint_or_404(endpoint_id, db, current_user)
    return EndpointResponse.model_validate(endpoint)


# ── PATCH /api/v1/endpoints/{endpoint_id} ────────────────────────────────────

@router.patch(
    "/{endpoint_id}",
    response_model=EndpointResponse,
)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    body: EndpointUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EndpointResponse:
    """
    Partially update an endpoint's configuration.

    PATCH semantics: only fields present in the request body are
    updated. Fields not sent remain unchanged.

    Examples:
      {"is_active": false}           → pause monitoring only
      {"interval_seconds": 30}       → increase poll frequency only
      {"name": "Orders API v2"}      → rename only

    The fetch happens first (with tenant scope) so we can confirm
    the endpoint exists and belongs to this tenant before updating.
    Updating a non-existent or cross-tenant endpoint → 404.
    """
    endpoint = await get_endpoint_or_404(endpoint_id, db, current_user)
    updated = await endpoints_repo.update_endpoint(
        db=db,
        endpoint=endpoint,
        data=body,
    )
    return EndpointResponse.model_validate(updated)


# ── DELETE /api/v1/endpoints/{endpoint_id} ────────────────────────────────────

@router.delete(
    "/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a monitored endpoint permanently.

    status_code=204: HTTP 204 No Content is the correct response for
    a successful DELETE. The resource is gone — there is nothing to
    return. FastAPI enforces this: returning anything from a 204 route
    is silently discarded.

    return None: explicit None return makes it clear this route
    intentionally returns no body, not that we forgot to return something.
    """
    endpoint = await get_endpoint_or_404(endpoint_id, db, current_user)
    await endpoints_repo.delete_endpoint(db=db, endpoint=endpoint)
    return None