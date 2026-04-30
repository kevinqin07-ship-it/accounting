"""Authentication and role-gating dependencies for the FastAPI app."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.models import ApiKey, ApiKeyRole
from accounting.services import auth as auth_svc


COOKIE_NAME = "accounting_api_key"


def _extract_raw_key(request: Request) -> Optional[str]:
    """Pull a raw key from the Authorization header or the session cookie."""
    header = request.headers.get("authorization")
    if header:
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    return None


def get_principal(
    request: Request, session: Session = Depends(get_session)
) -> ApiKey:
    raw = _extract_raw_key(request)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    api_key = auth_svc.validate(session, raw)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return api_key


def _require_any(*allowed: ApiKeyRole):
    def _dep(principal: ApiKey = Depends(get_principal)) -> ApiKey:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {principal.role.value} not authorized",
            )
        return principal

    return _dep


# Three convenience dependencies. Read endpoints take any role; write
# endpoints require bookkeeper or admin; sensitive operations (period
# close, key management, sending emails) require admin.
read_required = _require_any(
    ApiKeyRole.READONLY, ApiKeyRole.BOOKKEEPER, ApiKeyRole.ADMIN
)
write_required = _require_any(ApiKeyRole.BOOKKEEPER, ApiKeyRole.ADMIN)
admin_required = _require_any(ApiKeyRole.ADMIN)
