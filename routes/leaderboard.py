from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import Match, Prediction, TopScorer, User
from live_preview import calc_live_preview
from standings import compute_pool, compute_standings

router = APIRouter()


@router.get("/leaderboard")
async def leaderboard_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    rows = compute_standings()
    pool = compute_pool(rows)  # Pool immer auf Basis offizieller Punkte

    # ── Live-Vorschau: Punkte für laufende Spiele einrechnen ─────────
    live_preview = calc_live_preview()
    live_user_pts: dict[int, int] = {}
    for match_pts_map in live_preview.values():
        for uid, pts in match_pts_map.items():
            live_user_pts[uid] = live_user_pts.get(uid, 0) + pts
    has_live = bool(live_preview)

    if has_live:
        import copy
        rows = copy.deepcopy(rows)
        for r in rows:
            r.total_points += live_user_pts.get(r.user_id, 0)
        rows.sort(key=lambda r: (-r.total_points, r.display_name.lower()))
        last_pts, last_rank = None, 0
        for i, r in enumerate(rows, 1):
            if r.total_points != last_pts:
                last_rank = i
                last_pts = r.total_points
            r.rank = last_rank

    with get_session() as s:
        top5 = list(s.scalars(select(TopScorer).order_by(TopScorer.rank).limit(5)).all())

        # ── Trefferquote: alle abgeschlossenen Spiele ────────────
        all_finished_ids = [int(r[0]) for r in s.execute(
            select(Match.id).where(Match.result_home.is_not(None))
        ).all()]

        preds_stats = list(s.execute(
            select(Prediction.user_id, Prediction.match_id, Prediction.points_awarded)
            .where(Prediction.match_id.in_(all_finished_ids))
        ).all()) if all_finished_ids else []

        # ── Exakt/Tordiff/Tendenz pro Phase ──────────────────────
        phase_pred_rows = list(s.execute(
            select(Prediction.user_id,
                   Prediction.pred_home, Prediction.pred_away,
                   Match.result_home, Match.result_away,
                   Match.phase, Match.match_number)
            .join(Match, Prediction.match_id == Match.id)
            .where(Match.is_finished.is_(True))
        ).all())

        def _phase_key(phase: str, mn: int | None) -> str:
            if phase == "group":
                n = mn or 0
                if n <= 24: return "st1"
                if n <= 48: return "st2"
                return "st3"
            return phase

        def _sign(x: int) -> int:
            return 1 if x > 0 else (-1 if x < 0 else 0)

        # phase_counts[uid][phase_key] = {"e": exact, "d": diff, "t": tendency}
        phase_counts: dict[int, dict[str, dict[str, int]]] = {}
        for uid, ph, pa, rh, ra, phase, mn in phase_pred_rows:
            uid = int(uid)
            key = _phase_key(phase, mn)
            c = phase_counts.setdefault(uid, {}).setdefault(key, {"e": 0, "d": 0, "t": 0})
            if ph is None or pa is None or rh is None or ra is None:
                continue
            if ph == rh and pa == ra:
                c["e"] += 1
            elif (ph - pa) == (rh - ra):
                c["d"] += 1
            elif _sign(ph - pa) == _sign(rh - ra):
                c["t"] += 1

        # ── Joker-Rendite ─────────────────────────────────────────
        users_raw = list(s.scalars(select(User)).all())
        joker_pts_map: dict[int, int] = {}
        joker_match_map: dict[int, str] = {}
        for u in users_raw:
            if not u.joker_match_id:
                continue
            jm = s.get(Match, u.joker_match_id)
            if not jm or jm.result_home is None:
                continue
            _ = jm.home_team, jm.away_team
            jpred = s.scalar(
                select(Prediction).where(
                    Prediction.user_id == u.id,
                    Prediction.match_id == u.joker_match_id,
                )
            )
            if jpred:
                joker_pts_map[int(u.id)] = int(jpred.points_awarded or 0)
                home = jm.home_team.name if jm.home_team else (jm.home_placeholder or "?")
                away = jm.away_team.name if jm.away_team else (jm.away_placeholder or "?")
                joker_match_map[int(u.id)] = f"{home} – {away}"

    # ── Statistiken pro Nutzer aufbauen ──────────────────────────
    tipped_count: dict[int, int] = {}

    for uid, mid, pts in preds_stats:
        uid = int(uid)
        tipped_count[uid] = tipped_count.get(uid, 0) + 1

    stats: dict[int, dict] = {}
    for r in rows:
        uid = r.user_id
        tc = tipped_count.get(uid, 0)
        total_match_pts = sum(r.phase_points.values())
        tq = round(total_match_pts / tc, 1) if tc > 0 else 0.0
        stats[uid] = {
            "trefferquote": tq,
            "tipped_count": tc,
            "joker_pts": joker_pts_map.get(uid),
            "joker_match": joker_match_map.get(uid),
        }

    rows_trefferquote = sorted(rows, key=lambda r: stats[r.user_id]["trefferquote"], reverse=True)

    def _grp(r):
        return r.phase_points.get("st1", 0) + r.phase_points.get("st2", 0) + r.phase_points.get("st3", 0)

    rows_group = sorted(rows, key=_grp, reverse=True)
    rows_ko    = sorted(rows, key=lambda r: sum(r.phase_points.values()) - _grp(r), reverse=True)
    rows_st1   = sorted(rows, key=lambda r: r.phase_points.get("st1", 0), reverse=True)
    rows_st2   = sorted(rows, key=lambda r: r.phase_points.get("st2", 0), reverse=True)
    rows_st3   = sorted(rows, key=lambda r: r.phase_points.get("st3", 0), reverse=True)

    return templates.TemplateResponse(request, "leaderboard.html", {
        "user": user, "active": "leaderboard",
        "rows": rows,
        "has_live": has_live,
        "live_user_pts": live_user_pts,
        "rows_group": rows_group,
        "rows_ko": rows_ko,
        "rows_st1": rows_st1,
        "rows_st2": rows_st2,
        "rows_st3": rows_st3,
        "rows_trefferquote": rows_trefferquote,
        "stats": stats,
        "phase_counts": phase_counts,
        "pool": pool,
        "top5": top5,
        "flash": request.session.pop("flash", None),
    })
