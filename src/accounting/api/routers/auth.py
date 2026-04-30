from __future__ import annotations

from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import ApiKeyCreate, ApiKeyIssued, ApiKeyOut, LoginIn
from accounting.api.security import COOKIE_NAME, admin_required
from accounting.models import ApiKeyRole
from accounting.services import auth as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_out(api_key) -> ApiKeyOut:
    return ApiKeyOut(
        id=api_key.id,
        name=api_key.name,
        role=api_key.role.value,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
    )


@router.post("/login")
def login(payload: LoginIn, response: Response, session: Session = Depends(get_session)):
    """Validate a key and set it as an HTTP-only session cookie. Used by
    the dashboard so browsers can authenticate without a custom header."""
    api_key = auth_svc.validate(session, payload.key)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    response.set_cookie(
        COOKIE_NAME,
        payload.key,
        httponly=True,
        samesite="lax",
        max_age=int(timedelta(hours=12).total_seconds()),
    )
    return {"role": api_key.role.value, "name": api_key.name}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/keys", response_model=List[ApiKeyOut])
def list_keys(
    include_revoked: bool = False,
    session: Session = Depends(get_session),
    _=Depends(admin_required),
):
    return [_to_out(k) for k in auth_svc.list_keys(session, include_revoked=include_revoked)]


@router.post("/keys", response_model=ApiKeyIssued, status_code=201)
def create_key(
    payload: ApiKeyCreate,
    session: Session = Depends(get_session),
    _=Depends(admin_required),
):
    try:
        role = ApiKeyRole(payload.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role {payload.role!r}; allowed: {[r.value for r in ApiKeyRole]}",
        )
    issued = auth_svc.create_key(session, name=payload.name, role=role)
    base = _to_out(issued.api_key).model_dump()
    return ApiKeyIssued(**base, raw_key=issued.raw_key)


@router.delete("/keys/{key_id}", response_model=ApiKeyOut)
def revoke_key(
    key_id: int,
    session: Session = Depends(get_session),
    _=Depends(admin_required),
):
    return _to_out(auth_svc.revoke(session, key_id))
