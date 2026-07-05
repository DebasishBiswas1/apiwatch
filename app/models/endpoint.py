import uuid

from sqlalchemy import ForeignKey, String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class MonitoredEndpoint(TimestampMixin, Base):
    """
    A URL registered by a tenant for monitoring.

    This is the core business object of APIWatch — everything else
    (metrics, incidents, AI reports) hangs off this model.

    Design decisions:
    - interval_seconds: how often to poll. Default 60s. Tenant-configurable
      later so power users can poll critical endpoints more frequently.
    - is_active: lets users pause monitoring without deleting history.
      Deleting would orphan metric records; pausing preserves them.
    - timeout_seconds: how long the poller waits before declaring a
      connection failure. Separate from an HTTP error — a timeout means
      the server didn't respond at all, which is often worse.
    """

    __tablename__ = "monitored_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant discriminator — every query on this table filters on this.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-readable label — shown in dashboard (e.g. "Orders API")
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # The actual URL to poll (e.g. "https://api.company.com/orders")
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # How often to ping this endpoint, in seconds. Default: every 60s.
    interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )

    # How long to wait for a response before declaring timeout, in seconds.
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    # Pause/resume without deleting. Poller checks this before pinging.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationship back to the owning organization
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="endpoints",
    )

    def __repr__(self) -> str:
        return f"<MonitoredEndpoint id={self.id} name={self.name!r} url={self.url!r}>"
