from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import SpecialTip, TopScorer, User

router = APIRouter()


@router.get("/torschuetzen")
async def torschuetzen_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    with get_session() as s:
        scorers = list(s.scalars(
            select(TopScorer).order_by(TopScorer.rank)
        ).all())

        # Wer hat welchen Torschützenkönig getippt?
        # SpecialTip.top_scorer = Freitext (Spielername)
        tips_raw = s.execute(
            select(SpecialTip.user_id, SpecialTip.top_scorer)
        ).all()
        users = {u.id: u.display_name for u in s.scalars(select(User)).all()}

    # {player_name: [display_name, ...]}
    scorer_tips: dict[str, list[str]] = {}
    for uid, name in tips_raw:
        if name:
            scorer_tips.setdefault(name, []).append(users.get(uid, "?"))

    return templates.TemplateResponse(request, "torschuetzen.html", {
        "user": user, "active": "torschuetzen",
        "scorers": scorers,
        "scorer_tips": scorer_tips,
        "flash": request.session.pop("flash", None),
    })
