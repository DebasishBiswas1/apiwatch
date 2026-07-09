"""
poller.py — the function that pings one endpoint and records the result.

This file has one job: given an endpoint, make an HTTP request to its
URL, measure the outcome, and write a MetricRecord to the database.

Why is this a standalone function and not a method on the model?
  It has side effects (network call, DB write) and external dependencies
  (httpx, SQLAlchemy). Keeping it as a plain async function makes it
  easy to test in isolation — pass in a mock DB session and a mock
  endpoint, assert the right MetricRecord was created.

Why does this file know nothing about scheduling?
  Single responsibility. This file answers "how do I poll one endpoint?"
  The scheduler (Section 4) answers "when do I poll which endpoints?"
  Mixing them would make both harder to change and test independently.
"""
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.endpoint import MonitoredEndpoint
from app.models.metric import MetricRecord


async def poll_endpoint(endpoint_id: uuid.UUID) -> None:
    """
    Poll a single endpoint and write the result as a MetricRecord.

    Takes endpoint_id (not the ORM object) because this function is
    called by the scheduler which runs in a separate context from any
    existing DB session. We open a fresh session here, do our work,
    and close it — completely self-contained.

    Flow:
      1. Open a DB session
      2. Fetch the endpoint (skip if deleted or deactivated since scheduled)
      3. Make the HTTP GET request with a timeout
      4. Record latency and status
      5. Write MetricRecord
      6. Close session
    """
    async with SessionLocal() as db:
        # ── Fetch the endpoint ────────────────────────────────────────────────
        result = await db.execute(
            select(MonitoredEndpoint).where(
                MonitoredEndpoint.id == endpoint_id,
                MonitoredEndpoint.is_active == True,  # noqa: E712
            )
        )
        endpoint = result.scalar_one_or_none()

        if endpoint is None:
            # Endpoint was deleted or deactivated between schedule and run.
            # Nothing to do — just return silently.
            return

        # ── Make the HTTP request ─────────────────────────────────────────────
        # We capture the start time with time.perf_counter() — a high
        # resolution monotonic clock. Do NOT use datetime.now() for measuring
        # elapsed time: wall clock time can go backwards (NTP adjustments,
        # DST changes). perf_counter is guaranteed to only go forward and
        # has sub-millisecond precision.
        status_code = None
        latency_ms = None
        is_healthy = False
        error_detail = None

        start = time.perf_counter()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    str(endpoint.url),
                    timeout=endpoint.timeout_seconds,
                    follow_redirects=True,
                )

            # elapsed time in milliseconds
            latency_ms = (time.perf_counter() - start) * 1000
            status_code = response.status_code

            # Healthy = 2xx status code within the timeout window.
            # 3xx redirects are followed (follow_redirects=True) so
            # we only see the final status code here.
            is_healthy = 200 <= status_code < 300
            if not is_healthy:
                error_detail = f"status_{status_code}"

        except httpx.TimeoutException:
            # Request took longer than endpoint.timeout_seconds.
            # latency_ms and status_code stay None — we never got a response.
            latency_ms = (time.perf_counter() - start) * 1000
            error_detail = "timeout"

        except httpx.ConnectError:
            # DNS resolution failed, connection refused, network unreachable.
            # The server did not respond at all — worse than a timeout.
            error_detail = "connection_refused"

        except httpx.RemoteProtocolError:
            # Server closed the connection without sending a valid HTTP
            # response. Common causes: server crash mid-response, load
            # balancer killing idle connections, misconfigured upstream.
            # Distinct from connection_refused — the TCP connection was
            # established but the HTTP protocol was violated.
            error_detail = "remote_protocol_error"

        except Exception as e:
            # Catch-all for unexpected errors (SSL failures, invalid URL
            # that slipped through validation, etc.).
            # We log and record rather than crash the whole scheduler.
            error_detail = f"error_{type(e).__name__}"

        # ── Write the MetricRecord ────────────────────────────────────────────
        metric = MetricRecord(
            endpoint_id=endpoint.id,
            organization_id=endpoint.organization_id,
            status_code=status_code,
            latency_ms=latency_ms,
            is_healthy=is_healthy,
            error_detail=error_detail,
        )
        db.add(metric)
        await db.commit()


async def poll_all_active_endpoints() -> None:
    """
    Fetch all active endpoints and poll each one.

    This is the function the scheduler calls on its tick — it is the
    entry point for each polling cycle.

    Brute force approach (Phase 1):
      Poll endpoints sequentially one after another.
      Simple, correct, easy to reason about.

    What breaks under load (Phase 2 will fix):
      With 100 endpoints each taking 2s to respond, one cycle takes
      200 seconds — longer than our 60s interval, causing cycles to
      pile up. Phase 2 replaces this with concurrent polling using
      asyncio.gather() and then Celery for true parallelism.
      For now, sequential is fine for development and learning.
    """
    async with SessionLocal() as db:
        result = await db.execute(
            select(MonitoredEndpoint).where(
                MonitoredEndpoint.is_active == True  # noqa: E712
            )
        )
        endpoints = result.scalars().all()

    # Poll each endpoint sequentially.
    # We close the DB session above before polling so we are not holding
    # an open connection during the HTTP requests (which can be slow).
    # Each poll_endpoint() call opens its own fresh session.
    for endpoint in endpoints:
        await poll_endpoint(endpoint.id)