"""
auth.py — Pydantic schemas for auth request bodies and responses.

Why separate from ORM models?
  ORM models are SQLAlchemy classes tied to database tables.
  Schemas are Pydantic classes that define the HTTP API contract.
  They are different concerns and must stay separate:
  - ORM models have hashed_password, internal FKs, SQLAlchemy internals
  - Schemas expose only what the client should send or receive
  - A schema can reshape or rename fields without changing the DB structure

The naming convention:
  XxxRequest  — what the client sends in the request body
  XxxResponse — what we send back to the client
"""
import uuid
from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    """
    Body for POST /auth/register.

    EmailStr: pydantic's built-in email validator. It checks format
    (has @, has domain, etc.) automatically. No regex needed.

    password: we accept the plain-text password here — it is hashed
    immediately in the route handler and never stored or logged.

    min_length=8: basic password strength enforcement at the API level.
    field_validator: lets us add custom validation logic beyond what
    the type annotation alone can express.
    """
    organization_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("organization_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Organization name cannot be blank")
        return v.strip()


class LoginRequest(BaseModel):
    """Body for POST /auth/login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """
    Response for both register and login.

    access_token: the JWT string the client stores and sends in future
    requests as: Authorization: Bearer <access_token>

    token_type: always "bearer" — this is the OAuth2 convention that
    clients and API tools (like Swagger UI) expect.
    """
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """
    Safe user representation — never includes hashed_password.

    model_config with from_attributes=True: tells Pydantic it can
    construct this schema from a SQLAlchemy ORM object (which uses
    attribute access) instead of a plain dict. Without this,
    UserResponse.model_validate(user_orm_object) would fail.
    """
    id: uuid.UUID
    email: str
    organization_id: uuid.UUID
    is_active: bool

    model_config = {"from_attributes": True}
