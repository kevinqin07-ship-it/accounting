"""HTML dashboard. Browser-friendly login form sets a cookie that the
existing API auth dependency picks up; the dashboard itself is gated by
read_required."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.security import COOKIE_NAME, _extract_raw_key
from accounting.money import fmt
from accounting.services import auth as auth_svc
from accounting.services import dashboard as dashboard_svc


_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["fmt"] = fmt


router = APIRouter(tags=["dashboard"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    key: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    api_key = auth_svc.validate(session, key)
    if api_key is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid or revoked key. Try again."},
            status_code=401,
        )
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        key,
        httponly=True,
        samesite="lax",
        max_age=int(timedelta(hours=12).total_seconds()),
    )
    return response


@router.get("/logout")
def logout() -> Response:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/dashboard")
def dashboard(
    request: Request, session: Session = Depends(get_session)
) -> Response:
    """Browser-flow auth: unauthenticated requests redirect to /login
    instead of returning JSON 401. Any active key role can view."""
    raw = _extract_raw_key(request)
    principal = auth_svc.validate(session, raw) if raw else None
    if principal is None:
        return RedirectResponse(url="/login", status_code=303)
    snapshot = dashboard_svc.build_snapshot(session)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"snapshot": snapshot, "principal": principal},
    )
