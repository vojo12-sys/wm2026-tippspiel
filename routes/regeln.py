from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from deps import require_user, templates
from settings import get_pool, get_rules, get_scoring

router = APIRouter()


@router.get("/regeln")
async def regeln_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    scoring = get_scoring()
    pool = get_pool()
    raw = get_rules()
    # Platzhalter mit aktuellen Werten befüllen
    try:
        text = raw.format(**scoring, buy_in=pool.get("buy_in", 20), currency=pool.get("currency", "EUR"))
    except (KeyError, ValueError):
        text = raw  # falls unbekannte Platzhalter → unverändert anzeigen

    return templates.TemplateResponse(request, "regeln.html", {
        "user": user,
        "active": "",
        "rules_text": text,
        "scoring": scoring,
        "pool": pool,
        "flash": None,
    })
