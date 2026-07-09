import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MetricRecord(Base):
    """
    One row per poll attempt on one endpoint.

    This is a time-series append-only table — rows are never updated,
    only inserted. Every poll adds a new row regardless of outcome.

    Why not use TimestampMixin here?
      TimestampMixin adds created_at AND updated_at. MetricRecords
      are never updated after creation — they are immutable facts
      about what happened at a point in time. We only need polled_at,
      which we define explicitly with a more descriptive name.

    Why Float for latency_ms and not Integer?
      Latency is measured in milliseconds but httpx gives us a float
      (e.g. 123.47ms). Storing as Float preserves precision for
      percentile calculations later. Integer would lose sub-ms detail.
    """

    __tablename__ = "metric_records"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    # Which endpoint was polled — FK to monitored_endpoints
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitored_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which tenant owns this metric — denormalized for query performance.
    # We could join through endpoint to get org_id, but storing it directly
    # lets dashboard queries filter on org_id without a JOIN.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When the poll was executed — the primary time axis for all charts.
    # Indexed because every dashboard query orders or filters by time.
    polled_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # HTTP status code returned (200, 404, 503, etc.)
    # None if the request timed out or connection was refused entirely.
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Round-trip time in milliseconds from request sent to response received.
    # None if the request timed out before any response arrived.
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # True if status 2xx AND latency within timeout. False otherwise.
    # Denormalized for fast dashboard uptime % calculation —
    # COUNT(is_healthy=True) / COUNT(*) without re-evaluating conditions.
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Human-readable failure reason when is_healthy=False.
    # e.g. "timeout", "connection_refused", "status_503"
    # Null when is_healthy=True.
    error_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship back to the endpoint for ORM convenience
    endpoint: Mapped["MonitoredEndpoint"] = relationship(
        "MonitoredEndpoint",
    )

    def __repr__(self) -> str:
        return (
            f"<MetricRecord endpoint={self.endpoint_id} "
            f"status={self.status_code} healthy={self.is_healthy}>"
        )