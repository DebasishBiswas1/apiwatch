"""
auth.py — registration and login routes.

These are the only two routes in the entire application that do NOT
require authentication — they are where authentication is established.
Every other route will declare Depends(get_current_user).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

# APIRouter is FastAPI's way of grouping related routes.
# prefix="/auth" means all routes here are under /api/v1/auth/...
# tags=["auth"] groups them together in /docs Swagger UI.
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # ── Step 1: check email uniqueness ────────────────────────────────────────
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # ── Step 2: create and flush Organization first ───────────────────────────
    # We must flush here so Postgres assigns and returns the UUID for
    # organization.id before we reference it in the User constructor.
    # Without this flush, organization.id is still None at User creation time.
    organization = Organization(name=body.organization_name)
    db.add(organization)
    await db.flush()   # ← this line is the fix

    # ── Step 3: create User — organization.id is now populated ───────────────
    user = User(
        organization_id=organization.id,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # ── Step 4: issue JWT ─────────────────────────────────────────────────────
    token = create_access_token({
        "user_id": str(user.id),
        "org_id": str(user.organization_id),
    })

    await db.commit()
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate an existing user and issue a JWT.

    Security note on timing: we always run verify_password even when
    the user is not found (using a dummy hash). This ensures the
    response time is the same whether the email exists or not,
    preventing timing attacks that could enumerate valid emails.
    """
    # ── Look up user by email ─────────────────────────────────────────────────
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # ── Verify password ───────────────────────────────────────────────────────
    # We use a single generic error for both "user not found" and
    # "wrong password". Never reveal which one failed — that would
    # let attackers enumerate valid email addresses.
    DUMMY_HASH = "$2b$12$notarealhashjustpaddingtomakeitlookright123456"
    password_to_check = user.hashed_password if user else DUMMY_HASH

    if not verify_password(body.password, password_to_check) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_access_token({
        "user_id": str(user.id),
        "org_id": str(user.organization_id),
    })

    return TokenResponse(access_token=token)
