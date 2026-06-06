from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from auth import hash_password, verify_password
from database import get_session
from deps import require_user, templates
from models import Match, User
from settings import get_pool
from sqlalchemy import select


def _pool_locked() -> bool:
    """Pott-Anmeldung gesperrt sobald das erste Spiel gesperrt ist."""
    with get_session() as s:
        first = s.scalar(select(Match).order_by(Match.kickoff_utc))
        return first.is_locked if first else False

router = APIRouter()


@router.get("/profil")
async def profil_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    pool = get_pool()
    with get_session() as s:
        u = s.get(User, user["id"])
        in_pool = u.in_pool if u else False
        has_paid = u.has_paid if u else False
    return templates.TemplateResponse(request, "profil.html", {
        "user": user, "active": "profil",
        "in_pool": in_pool,
        "has_paid": has_paid,
        "pool": pool,
        "pool_locked": _pool_locked(),
        "flash": request.session.pop("flash", None),
    })


@router.post("/profil/pool")
async def update_pool(
    request: Request,
    in_pool: bool = Form(False),
    user: dict = Depends(require_user),
):
    if isinstance(user, RedirectResponse):
        return user
    if _pool_locked():
        request.session["flash"] = {"message": "Pott-Anmeldung ist nach Turnierbeginn nicht mehr möglich.", "type": "danger"}
        return RedirectResponse("/profil", status_code=303)
    with get_session() as s:
        u = s.get(User, user["id"])
        if u:
            u.in_pool = in_pool
            if not in_pool:
                u.has_paid = False  # Opt-out setzt auch bezahlt zurück
    msg = "Du nimmst jetzt am Pott teil." if in_pool else "Du hast dich vom Pott abgemeldet."
    request.session["flash"] = {"message": msg, "type": "success"}
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/passwort")
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    new_password2: str = Form(...),
    user: dict = Depends(require_user),
):
    if isinstance(user, RedirectResponse):
        return user
    if new_password != new_password2:
        request.session["flash"] = {"message": "Neue Passwörter stimmen nicht überein.", "type": "danger"}
        return RedirectResponse("/profil", status_code=303)
    if len(new_password) < 6:
        request.session["flash"] = {"message": "Passwort muss mindestens 6 Zeichen haben.", "type": "danger"}
        return RedirectResponse("/profil", status_code=303)
    with get_session() as s:
        u = s.get(User, user["id"])
        if not u or not verify_password(old_password, u.password_hash):
            request.session["flash"] = {"message": "Aktuelles Passwort falsch.", "type": "danger"}
            return RedirectResponse("/profil", status_code=303)
        u.password_hash = hash_password(new_password)
    request.session["flash"] = {"message": "Passwort erfolgreich geändert.", "type": "success"}
    return RedirectResponse("/profil", status_code=303)
