from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import Match, Prediction
from standings import compute_standings

router = APIRouter()

_MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


@router.get("/home")
async def home_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    from config import DISPLAY_TIMEZONE
    from results_sync import get_live_scores

    now = datetime.now(timezone.utc)
    lock_threshold = now + timedelta(minutes=10)

    with get_session() as s:
        upcoming_raw = list(s.scalars(
            select(Match)
            .where(Match.kickoff_utc > now, Match.is_finished == False)
            .order_by(Match.kickoff_utc)
            .limit(5)
        ).all())
        for m in upcoming_raw:
            _ = m.home_team, m.away_team  # Eager-load

        open_tips = 0
        if not user.get("is_spectator"):
            open_match_ids = [
                m.id for m in upcoming_raw
                if m.kickoff_utc.replace(tzinfo=timezone.utc) > lock_threshold
            ]
            if open_match_ids:
                tipped_ids = set(
                    row[0] for row in s.execute(
                        select(Prediction.match_id)
                        .where(
                            Prediction.user_id == user["id"],
                            Prediction.match_id.in_(open_match_ids),
                        )
                    ).all()
                )
                open_tips = len(open_match_ids) - len(tipped_ids)

    standings = compute_standings()
    top5 = standings[:5]
    user_rank = None
    user_points = 0
    for r in standings:
        if r.user_id == user["id"]:
            user_rank = r.rank
            user_points = r.total_points
            break

    live = get_live_scores()

    upcoming = []
    for m in upcoming_raw:
        koff = m.kickoff_utc
        if koff.tzinfo is None:
            koff = koff.replace(tzinfo=timezone.utc)
        local_dt = koff.astimezone(DISPLAY_TIMEZONE)
        home = m.home_team.name if m.home_team else (m.home_placeholder or "TBD")
        away = m.away_team.name if m.away_team else (m.away_placeholder or "TBD")
        upcoming.append({
            "id": m.id,
            "home": home,
            "away": away,
            "home_flag": m.home_team.flag_code if m.home_team else None,
            "away_flag": m.away_team.flag_code if m.away_team else None,
            "date_de": f"{local_dt.day}. {_MONTHS_DE[local_dt.month - 1]}",
            "time_de": local_dt.strftime("%H:%M"),
            "kickoff_iso": koff.isoformat(),
            "live": live.get(str(m.id)),
        })

    return templates.TemplateResponse(request, "home.html", {
        "user": user,
        "active": "home",
        "upcoming": upcoming,
        "top5": top5,
        "user_rank": user_rank,
        "user_points": user_points,
        "open_tips": open_tips,
        "flash": request.session.pop("flash", None),
    })
