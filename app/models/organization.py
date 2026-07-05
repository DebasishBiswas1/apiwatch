import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Organization(TimestampMixin, Base):
    """
    The top-level tenant unit. Every user and every monitored endpoint
    belongs to exactly one Organization.

    In our shared-schema multi-tenant model, Organization.id is the
    tenant discriminator — every tenant-owned table has a foreign key
    pointing here, and every query filters on it.

    Why is this the root of the tenant tree?
      A SaaS typically has teams/companies as the billing and access
      control unit, not individual users. Users come and go; the
      Organization persists. This lets us later add team features
      (multiple users per org, roles, invitations) without restructuring
      the schema.
    """

    __tablename__ = "organizations"

    # UUID primary key — random, non-enumerable, globally unique.
    # server_default generates it in the DB; we also set a Python default
    # so the object has an id before it is flushed to the DB.
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    # The organization's display name — shown in the dashboard header.
    # String(255) maps to VARCHAR(255) in Postgres.
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships — SQLAlchemy-level only, no DB column added.
    # "users" lets us write org.users and get a list of User objects.
    # back_populates="organization" means User.organization is wired back.
    # cascade="all, delete-orphan" means deleting an org deletes its users
    # and endpoints automatically, keeping referential integrity.
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    endpoints: Mapped[list["MonitoredEndpoint"]] = relationship(
        "MonitoredEndpoint",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name!r}>"
