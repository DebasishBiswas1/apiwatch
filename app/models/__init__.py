# Import all models here so Alembic can discover them via Base.metadata
# when it runs autogenerate. If a model is not imported here (directly
# or transitively), Alembic will not see its table and will not generate
# a migration for it.
from app.models.organization import Organization
from app.models.user import User
from app.models.endpoint import MonitoredEndpoint
from app.models.metric import MetricRecord

__all__ = ["Organization", "User", "MonitoredEndpoint", "MetricRecord"]
