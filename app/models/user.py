import uuid

from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    """
    A human user of the system. Always belongs to one Organization.

    Why store hashed_password and not password?
      Passwords must NEVER be stored in plain text. We store the bcrypt
      hash — a one-way transformation. On login we hash the input and
      compare hashes. Even if the database is compromised, raw passwords
      are not exposed. We add bcrypt in Step 1c (auth).

    Why is email unique globally, not just per-org?
      Email is the login credential. If the same email existed in two
      orgs, login would be ambiguous — which org do we authenticate into?
      Global uniqueness keeps login simple and unambiguous.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    # organization_id is the tenant discriminator on this table.
    # ForeignKey references organizations.id — Postgres enforces this:
    # you cannot insert a user with an org that doesn't exist.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,          # indexed because every user query filters on it
    )

    # Email is the login identifier — must be globally unique.
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,          # indexed because login looks up by email
    )

    # bcrypt hash stored here. Never the raw password. Added in Step 1c.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Soft "is this account active?" flag.
    # Deactivating a user sets this to False instead of deleting the row,
    # preserving audit history and foreign key integrity.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="users",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
