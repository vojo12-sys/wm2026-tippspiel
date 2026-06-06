from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE, PHASES
from database import get_session
from deps import require_user, templates
from models import Match, Prediction, User

router = APIRouter()


@router.get("/stats")
async def stats_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    user_id = user["id"]

    with get_session() as s:
        # Alle abgeschlossenen Spiele mit Tipp des Users
        finished = s.execute(
            select(Match).where(Match.is_finished == True).order_by(Match.kickoff_utc)
        ).scalars().all()
        for m in finished:
            _ = m.home_team, m.away_team

        preds_map: dict[int, Prediction] = {
            p.match_id: p for p in s.scalars(
                select(Prediction).where(Prediction.user_id == user_id)
            ).all()
        }

        # Alle User für Vergleich (Durchschnitt)
        all_preds = list(s.scalars(select(Prediction)).all())
        u = s.get(User, user_id)
        joker_match_id = u.joker_match_id if u else None

    # ── Basis-Statistiken ──────────────────────────────────────────────────
    total_finished = len(finished)
    tipped = sum(1 for m in finished if m.id in preds_map)

    exact = goal_diff = tendency = wrong = joker_used = 0
    best_match = None
    best_pts = -1
    phase_pts: dict[str, int] = defaultdict(int)
    cumulative: list[dict] = []   # für Formkurve: [{date, cum_pts, user_pts}]

    # Durchschnitt aller Tipper pro Spiel
    match_avg: dict[int, float] = {}
    match_all_pts: dict[int, list[int]] = defaultdict(list)
    for p in all_preds:
        match_all_pts[p.match_id].append(p.points_awarded or 0)
    for mid, pts_list in match_all_pts.items():
        match_avg[mid] = sum(pts_list) / len(pts_list) if pts_list else 0

    cum = 0
    for m in finished:
        p = preds_map.get(m.id)
        pts = p.points_awarded if p else 0
        is_joker = m.id == joker_match_id

        if p:
            if pts >= 8 or (is_joker and pts >= 4):
                joker_used = pts if is_joker else joker_used
            base_pts = pts // 2 if is_joker and pts > 0 else pts
            if base_pts == 4:
                exact += 1
            elif base_pts == 3:
                goal_diff += 1
            elif base_pts >= 2:
                tendency += 1
            else:
                wrong += 1

            phase_pts[m.phase] += pts
            if pts > best_pts:
                best_pts = pts
                best_match = m

        cum += pts or 0
        local_date = m.kickoff_utc
        if local_date and local_date.tzinfo is None:
            local_date = local_date.replace(tzinfo=timezone.utc)
        date_str = local_date.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m") if local_date else "?"
        cumulative.append({"date": date_str, "pts": cum})

    tipped_finished = exact + goal_diff + tendency + wrong
    total_pts = cum

    # Formkurve + Vergleichstabelle für alle Nutzer
    all_users_cum: dict[str, list[int]] = {}
    all_users_stats: list[dict] = []
    with get_session() as s:
        all_users = list(s.scalars(select(User).order_by(User.display_name)).all())
        for u2 in all_users:
            u2_preds = {p.match_id: p for p in
                        s.scalars(select(Prediction).where(Prediction.user_id == u2.id)).all()}
            u2_joker = u2.joker_match_id
            c = 0
            pts_list = []
            u2_exact = u2_goal_diff = u2_tendency = u2_wrong = u2_tipped = 0
            for m in finished:
                p2 = u2_preds.get(m.id)
                pts2 = p2.points_awarded if p2 else 0
                c += pts2 or 0
                pts_list.append(c)
                if p2:
                    u2_tipped += 1
                    base = pts2 // 2 if (u2_joker and m.id == u2_joker and pts2 > 0) else pts2
                    if base >= 4:
                        u2_exact += 1
                    elif base == 3:
                        u2_goal_diff += 1
                    elif base >= 2:
                        u2_tendency += 1
                    else:
                        u2_wrong += 1
            all_users_cum[u2.display_name] = pts_list
            all_users_stats.append({
                "name": u2.display_name,
                "pts": c,
                "exact": u2_exact,
                "goal_diff": u2_goal_diff,
                "tendency": u2_tendency,
                "wrong": u2_wrong,
                "tipped": u2_tipped,
                "is_me": u2.id == user_id,
            })
    all_users_stats.sort(key=lambda x: -x["pts"])

    date_labels = [e["date"] for e in cumulative]

    return templates.TemplateResponse(request, "stats.html", {
        "user": user, "active": "stats",
        "flash": request.session.pop("flash", None),
        "total_finished": total_finished,
        "tipped": tipped,
        "tipped_finished": tipped_finished,
        "exact": exact, "goal_diff": goal_diff, "tendency": tendency, "wrong": wrong,
        "total_pts": total_pts,
        "best_match": best_match,
        "best_pts": best_pts,
        "phase_pts": dict(phase_pts),
        "phase_labels": PHASES,
        "joker_match_id": joker_match_id,
        "date_labels": date_labels,
        "all_users_cum": all_users_cum,
        "all_users_stats": all_users_stats,
        "current_user_name": user["display_name"],
    })
