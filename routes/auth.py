from __future__ import annotations

import time
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth import authenticate, create_user
from deps import templates

router = APIRouter()

# ── Login Rate-Limiting (in-memory, per IP) ──────────────────────────────────
_MAX_ATTEMPTS  = 5     # Fehlversuche im Fenster
_WINDOW_SECS   = 600   # 10 Minuten
_LOCKOUT_SECS  = 900   # 15 Minuten Sperre

_login_attempts: dict[str, dict] = {}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    e = _login_attempts.get(ip)
    if not e:
        return False
    if now < e.get("lockout_until", 0):
        return True
    if now - e["window_start"] > _WINDOW_SECS:
        del _login_attempts[ip]
    return False


def _record_failure(ip: str) -> None:
    now = time.time()
    e = _login_attempts.setdefault(ip, {"count": 0, "window_start": now, "lockout_until": 0})
    if now - e["window_start"] > _WINDOW_SECS:
        e["count"] = 0
        e["window_start"] = now
    e["count"] += 1
    if e["count"] >= _MAX_ATTEMPTS:
        e["lockout_until"] = now + _LOCKOUT_SECS


def _reset_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)

# ─────────────────────────────────────────────────────────────────────────────


def _flash(request: Request, message: str, type: str = "danger") -> None:
    request.session["flash"] = {"message": message, "type": type}


def _get_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


_MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]


@router.get("/")
async def index(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/home", status_code=302)

    from datetime import datetime, timezone as _tz
    from sqlalchemy import select as _sel
    from database import get_session as _gs
    from models import Match as _Match
    from config import DISPLAY_TIMEZONE

    next_match = None
    with _gs() as s:
        now = datetime.now(_tz.utc)
        m = s.scalar(
            _sel(_Match)
            .where(_Match.kickoff_utc > now, _Match.is_finished == False)
            .order_by(_Match.kickoff_utc)
            .limit(1)
        )
        if m:
            home = m.home_team.name if m.home_team else (m.home_placeholder or "TBD")
            away = m.away_team.name if m.away_team else (m.away_placeholder or "TBD")
            koff = m.kickoff_utc
            if koff.tzinfo is None:
                koff = koff.replace(tzinfo=_tz.utc)
            local_dt = koff.astimezone(DISPLAY_TIMEZONE)
            date_de = f"{local_dt.day}. {_MONTHS_DE[local_dt.month - 1]} {local_dt.year}"
            next_match = {
                "home": home,
                "away": away,
                "kickoff_iso": koff.isoformat(),
                "date_de": date_de,
                "time_de": local_dt.strftime("%H:%M Uhr"),
            }

    return templates.TemplateResponse(request, "landing.html", {"next_match": next_match})


@router.get("/login")
async def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/home", status_code=302)
    return templates.TemplateResponse(request, "login.html", {
        "flash": _get_flash(request), "user": None,
    })


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ip = _client_ip(request)
    if _is_rate_limited(ip):
        _flash(request, "Zu viele Fehlversuche. Bitte 15 Minuten warten.")
        return RedirectResponse("/login", status_code=303)
    u = authenticate(username.strip(), password)
    if not u:
        _record_failure(ip)
        _flash(request, "Benutzername oder Passwort falsch.")
        return RedirectResponse("/login", status_code=303)
    _reset_attempts(ip)
    request.session["user"] = {
        "id": u.id,
        "display_name": u.display_name,
        "is_admin": u.is_admin,
        "is_spectator": u.is_spectator,
    }
    return RedirectResponse("/home", status_code=303)


@router.get("/register")
async def register_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/home", status_code=302)
    return templates.TemplateResponse(request, "register.html", {
        "flash": _get_flash(request), "user": None,
    })


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    is_spectator: str = Form(default=""),
):
    if password != password2:
        _flash(request, "Passwörter stimmen nicht überein.")
        return RedirectResponse("/register", status_code=303)
    if len(password) < 6:
        _flash(request, "Passwort muss mindestens 6 Zeichen lang sein.")
        return RedirectResponse("/register", status_code=303)
    uname  = username.strip()
    dname  = display_name.strip() or uname
    spec   = bool(is_spectator)
    try:
        create_user(uname, dname, password, is_spectator=spec)
    except ValueError as e:
        _flash(request, str(e))
        return RedirectResponse("/register", status_code=303)

    try:
        from email_service import send_registration_notification
        send_registration_notification(uname, dname, is_spectator=spec)
    except Exception:
        pass  # E-Mail-Fehler darf Registrierung nicht blockieren

    _flash(request, "Konto erstellt – bitte einloggen.", "success")
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
