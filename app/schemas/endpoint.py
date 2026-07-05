import uuid
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class EndpointCreateRequest(BaseModel):
    """
    Body for POST /api/v1/endpoints.

    HttpUrl: Pydantic's built-in URL validator. It checks that the
    value is a valid URL with a scheme (http/https) and a host.
    Rejects "not-a-url", "ftp://wrong-scheme", etc. automatically.

    We convert it to str immediately in the validator because HttpUrl
    is a Pydantic special type — SQLAlchemy cannot store it directly,
    but it can store a plain str.
    """
    name: str
    url: HttpUrl
    interval_seconds: int = 60
    timeout_seconds: int = 10

    @field_validator("url", mode="before")
    @classmethod
    def url_to_str(cls, v):
        return str(v)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()

    @field_validator("interval_seconds")
    @classmethod
    def interval_positive(cls, v: int) -> int:
        if v < 10:
            raise ValueError("Interval must be at least 10 seconds")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_positive(cls, v: int) -> int:
        if v < 1 or v > 60:
            raise ValueError("Timeout must be between 1 and 60 seconds")
        return v


class EndpointUpdateRequest(BaseModel):
    """
    Body for PATCH /api/v1/endpoints/{id}.

    Every field is Optional with a None default.
    The route handler only updates fields that are not None.
    This lets the client send just the field they want to change.

    Example: {"is_active": false} pauses monitoring without
    touching the URL, name, or interval.
    """
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    interval_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("url", mode="before")
    @classmethod
    def url_to_str(cls, v):
        return str(v) if v is not None else v


class EndpointResponse(BaseModel):
    """
    What we return to the client for any endpoint operation.

    Includes id, timestamps, and org context — everything the
    client needs to display and manage the endpoint.

    from_attributes=True: allows constructing this from a
    SQLAlchemy ORM object directly (attribute access instead of dict).
    """
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    url: str
    interval_seconds: int
    timeout_seconds: int
    is_active: bool

    model_config = {"from_attributes": True}