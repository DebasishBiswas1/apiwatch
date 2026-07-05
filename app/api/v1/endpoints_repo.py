"""
endpoints_repo.py — all database operations for MonitoredEndpoint.

Why a separate repo file instead of writing queries inside routes?
  1. Routes should only handle HTTP concerns (parse input, return output).
     Database logic mixed into routes makes both harder to read and test.
  2. Every function here takes organization_id as a required parameter.
     This makes tenant scoping impossible to forget — the filter is
     built into the function signature, not an afterthought inside a route.
  3. When we add caching in Phase 2, we add it here in one place,
     not in every route that queries endpoints.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import MonitoredEndpoint
from app.schemas.endpoint import EndpointCreateRequest, EndpointUpdateRequest


async def create_endpoint(
    db: AsyncSession,
    organization_id: uuid.UUID,
    data: EndpointCreateRequest,
) -> MonitoredEndpoint:
    """
    Insert a new MonitoredEndpoint row for the given tenant.

    We pass organization_id explicitly rather than reading it from
    data — the client never sends their own org_id in the request body.
    We always take it from the verified JWT via get_current_user.
    This prevents a client from creating an endpoint under a different
    tenant's org_id by forging the request body.
    """
    endpoint = MonitoredEndpoint(
        organization_id=organization_id,
        name=data.name,
        url=str(data.url),
        interval_seconds=data.interval_seconds,
        timeout_seconds=data.timeout_seconds,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


async def get_endpoint_by_id(
    db: AsyncSession,
    endpoint_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> MonitoredEndpoint | None:
    """
    Fetch one endpoint by ID, scoped to the tenant.

    The WHERE clause has TWO conditions: id AND organization_id.
    This means:
      - If the endpoint exists and belongs to this tenant → returns it
      - If the endpoint does not exist → returns None
      - If the endpoint exists but belongs to ANOTHER tenant → returns None

    The third case is the critical one. We never return a 404 that says
    "this endpoint exists but is not yours" — that would confirm the UUID
    exists and leak information about other tenants. Returning None for
    both cases means the route returns the same 404 either way. The
    attacker learns nothing.
    """
    result = await db.execute(
        select(MonitoredEndpoint).where(
            MonitoredEndpoint.id == endpoint_id,
            MonitoredEndpoint.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def list_endpoints(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> list[MonitoredEndpoint]:
    """
    List all endpoints for a tenant, ordered by creation time.

    order_by(created_at) means newest endpoints appear last —
    consistent ordering prevents pages shuffling between requests.
    We will add pagination (limit/offset) in Phase 2 when lists
    can grow large enough to matter.
    """
    result = await db.execute(
        select(MonitoredEndpoint)
        .where(MonitoredEndpoint.organization_id == organization_id)
        .order_by(MonitoredEndpoint.created_at)
    )
    return list(result.scalars().all())


async def update_endpoint(
    db: AsyncSession,
    endpoint: MonitoredEndpoint,
    data: EndpointUpdateRequest,
) -> MonitoredEndpoint:
    """
    Apply a partial update to an existing endpoint.

    data.model_dump(exclude_none=True) converts the Pydantic schema
    to a dict, dropping every field that is None — those were not
    sent by the client and should not be changed.

    Example: client sends {"is_active": false}
    model_dump(exclude_none=True) → {"is_active": False}
    We only set is_active on the ORM object. name, url, interval
    are untouched.

    setattr(endpoint, field, value) sets the attribute dynamically
    by name — equivalent to endpoint.is_active = False but works
    for any field without a chain of if/elif statements.
    """
    updates = data.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(endpoint, field, str(value) if field == "url" else value)

    await db.commit()
    await db.refresh(endpoint)
    return endpoint


async def delete_endpoint(
    db: AsyncSession,
    endpoint: MonitoredEndpoint,
) -> None:
    """
    Hard delete the endpoint row.

    Why hard delete here but soft delete (is_active=False) for users?
      Users have audit trails and JWT tokens that reference their ID.
      Endpoints have no such external references yet — metrics and
      incidents do not exist until Step 1e/1f. Once we add those,
      we will revisit this decision and likely switch to soft delete
      to preserve history. For now, hard delete is the simplest
      correct thing.

    await db.delete() marks the object for deletion.
    await db.commit() executes the DELETE statement.
    """
    await db.delete(endpoint)
    await db.commit()