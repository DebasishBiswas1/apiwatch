from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """
    Adds created_at and updated_at to any model that inherits from it.

    Why a mixin and not copy-paste?
      Copy-pasting these two columns onto every model means if you ever
      need to change the default (e.g. switch to UTC timezone-aware),
      you change it in one place here, not in every model file.

    Why server_default=func.now() instead of default=datetime.utcnow?
      func.now() tells the DATABASE to set the timestamp at insert time.
      datetime.utcnow is a Python default — it runs when the Python object
      is created, not when the row is inserted. If there's any delay between
      object creation and DB insert (which async code can have), the Python
      default is stale. The database clock is always authoritative.

    Why onupdate=func.now() on updated_at?
      SQLAlchemy fires this automatically on every UPDATE statement for this
      row. You never manually set updated_at — it just happens.
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
