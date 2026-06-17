from __future__ import annotations

import unicodedata
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from sqlalchemy import func

from database import get_session
from deps import require_user, templates
from models import Match, SpecialTip, TopScorer, User

router = APIRouter()


def _normalize(name: str) -> str:
    """Akzente entfernen + Kleinschreibung für Namensvergleich."""
    return unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode().lower()


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

        total_goals = s.scalar(
            select(func.coalesce(func.sum(Match.result_home + Match.result_away), 0))
            .where(Match.is_finished.is_(True))
        ) or 0

    # {normalized_name: [display_name, ...]}
    scorer_tips_normalized: dict[str, list[str]] = {}
    for uid, name in tips_raw:
        if name:
            scorer_tips_normalized.setdefault(_normalize(name), []).append(users.get(uid, "?"))

    # Für das Template: {api_player_name: [display_name, ...]} über normalisierten Key
    scorer_tips: dict[str, list[str]] = {}
    for sc in scorers:
        key = _normalize(sc.player_name)
        if key in scorer_tips_normalized:
            scorer_tips[sc.player_name] = scorer_tips_normalized[key]

    return templates.TemplateResponse(request, "torschuetzen.html", {
        "user": user, "active": "torschuetzen",
        "scorers": scorers,
        "scorer_tips": scorer_tips,
        "total_goals": total_goals,
        "flash": request.session.pop("flash", None),
    })
