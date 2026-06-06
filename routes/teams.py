from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from api_sports import api_key_configured
from data_squads import SQUADS, get_squad
from data_teams import GROUPS
from data_venues import VENUES, by_country
from deps import require_user, templates

router = APIRouter()


@router.get("/teams")
async def teams_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    # squad_map: flag_code -> {gruppe: [spieler]} für alle Teams
    squad_map = {code: get_squad(code) for code in SQUADS}

    return templates.TemplateResponse(request, "teams.html", {
        "user": user,
        "active": "teams",
        "groups": GROUPS,
        "venues": VENUES,
        "venues_by_country": by_country(),
        "squad_map": squad_map,
        "has_photos": api_key_configured(),
        "flash": request.session.pop("flash", None),
    })
