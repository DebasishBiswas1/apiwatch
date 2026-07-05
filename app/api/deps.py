"""
deps.py — shared FastAPI dependencies.

A dependency is a function FastAPI calls automatically before your route
handler runs. It resolves something the route needs — the DB session,
the current user, the current tenant — and injects it as a parameter.

Why centralise dependencies here?
  Every auth-protected route needs get_current_user. If each route
  implemented its own JWT parsing, you would have the same logic in
  dozens of places. Centralising means: fix a bug once, update logic
  once, test once.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# OAuth2PasswordBearer does two things:
#   1. Tells FastAPI/Swagger UI that this API uses Bearer token auth,
#      so the "Authorize" button appears in /docs automatically.
#   2. Extracts the token from the "Authorization: Bearer <token>" header
#      and passes it as a string to the dependency that declares it.
# tokenUrl is where clients get a token — used only by Swagger UI.
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the currently authenticated user from the JWT in the request.

    FastAPI resolves the two Depends() parameters automatically:
      - bearer_scheme extracts the Bearer token from the header
      - get_db opens a fresh async session for this request

    Flow:
      1. Extract token from Authorization header (bearer_scheme)
      2. Decode and verify JWT signature + expiry (decode_access_token)
      3. Read user_id from token payload
      4. Look up User in database
      5. Verify user is active
      6. Return User — route handler receives it as a parameter

    Any failure raises HTTP 401, which FastAPI converts to a JSON error
    response automatically. The route handler never runs on failure.

    credentials_exception: we define it once and reuse it in multiple
    places below rather than constructing it each time. The
    WWW-Authenticate header is the HTTP standard for telling clients
    what auth scheme to use — required for proper 401 responses.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1: decode the JWT
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        # Covers: invalid signature, expired token, malformed token
        raise credentials_exception

    # Step 2: look up the user in the database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        # Token was valid but the user was deleted after it was issued
        raise credentials_exception

    # Step 3: check the account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user
