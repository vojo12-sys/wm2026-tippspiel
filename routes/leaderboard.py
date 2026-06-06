from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import TopScorer
from standings import compute_pool, compute_standings

router = APIRouter()


@router.get("/leaderboard")
async def leaderboard_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    rows = compute_standings()
    pool = compute_pool(rows)
    with get_session() as s:
        top5 = list(s.scalars(select(TopScorer).order_by(TopScorer.rank).limit(5)).all())

    # Pre-sort for phase tabs (Jinja2 doesn't support lambda in sort filter)
    rows_group = sorted(rows, key=lambda r: r.phase_points.get("group", 0), reverse=True)
    rows_ko    = sorted(rows, key=lambda r: sum(r.phase_points.values()) - r.phase_points.get("group", 0), reverse=True)

    return templates.TemplateResponse(request, "leaderboard.html", {
        "user": user, "active": "leaderboard",
        "rows": rows,
        "rows_group": rows_group,
        "rows_ko": rows_ko,
        "pool": pool,
        "top5": top5,
        "flash": request.session.pop("flash", None),
    })
