from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE, TOURNAMENT_START_UTC
from data_players import dropdown_options, option_to_name
from data_teams import GROUPS
from database import get_session
from deps import require_user, templates
from models import GroupPrediction, SpecialTip, Team

router = APIRouter()


def _deadline() -> datetime:
    return datetime.fromisoformat(TOURNAMENT_START_UTC)


def _is_locked() -> bool:
    return datetime.now(timezone.utc) >= _deadline()


def _all_teams() -> list[Team]:
    with get_session() as s:
        teams = s.scalars(select(Team).order_by(Team.name)).all()
        return list(teams)


def _teams_by_group() -> dict[str, list[Team]]:
    out: dict[str, list[Team]] = {}
    with get_session() as s:
        for t in s.scalars(select(Team).order_by(Team.group_letter, Team.name)).all():
            out.setdefault(t.group_letter, []).append(t)
    return out


@router.get("/langfrist")
async def langfrist_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    locked = _is_locked()
    dl = _deadline().astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y · %H:%M Uhr")
    user_id = user["id"]
    with get_session() as s:
        special = s.scalar(select(SpecialTip).where(SpecialTip.user_id == user_id))
        if special and special.champion_team:
            _ = special.champion_team
        gpreds = {
            gp.group_letter: (gp.predicted_1st, gp.predicted_2nd)
            for gp in s.scalars(select(GroupPrediction).where(GroupPrediction.user_id == user_id)).all()
        }
    return templates.TemplateResponse(request, "langfrist.html", {
        "user": user, "active": "langfrist",
        "locked": locked, "deadline": dl,
        "special": special, "gpreds": gpreds,
        "teams": _all_teams(),
        "teams_by_group": _teams_by_group(),
        "groups": sorted(GROUPS.keys()),
        "scorer_opts": dropdown_options(),
        "flash": request.session.pop("flash", None),
    })


@router.post("/langfrist")
async def langfrist_post(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    if _is_locked():
        return RedirectResponse("/langfrist", status_code=303)
    form = await request.form()
    user_id = user["id"]
    try:
        champ = int(form.get("champion") or 0) or None
    except (ValueError, TypeError):
        champ = None
    scorer_opt = form.get("scorer", "")
    scorer = option_to_name(scorer_opt) if scorer_opt else None
    try:
        total = int(form.get("total_goals") or 0)
    except (ValueError, TypeError):
        total = 0
    with get_session() as s:
        sp = s.scalar(select(SpecialTip).where(SpecialTip.user_id == user_id))
        if not sp:
            sp = SpecialTip(user_id=user_id)
            s.add(sp)
        sp.champion_team_id = champ
        sp.top_scorer = scorer
        sp.total_goals = total
        for letter in GROUPS.keys():
            try:
                first = int(form.get(f"g1_{letter}") or 0) or None
                second = int(form.get(f"g2_{letter}") or 0) or None
            except (ValueError, TypeError):
                first = second = None
            gp = s.scalar(select(GroupPrediction).where(
                GroupPrediction.user_id == user_id,
                GroupPrediction.group_letter == letter,
            ))
            if not gp:
                gp = GroupPrediction(user_id=user_id, group_letter=letter)
                s.add(gp)
            gp.predicted_1st = first
            gp.predicted_2nd = second
    request.session["flash"] = {"message": "Langfrist-Tipps gespeichert.", "type": "success"}
    return RedirectResponse("/langfrist", status_code=303)
