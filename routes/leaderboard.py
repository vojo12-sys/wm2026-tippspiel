from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import Match, Prediction, TopScorer, User
from live_preview import calc_live_preview
from settings import get_scoring
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
        joker_bonus_map: dict[int, int] = {}
        joker_phase_key_map: dict[int, str] = {}
        joker_match_map: dict[int, str] = {}
        joker_phase_map: dict[int, str] = {}
        joker_result_map: dict[int, str] = {}
        joker_pred_map: dict[int, str] = {}
        _phase_label = {
            "group": "Gruppenphase", "round32": "Sechzehntelfinale",
            "round16": "Achtelfinale", "quarter": "Viertelfinale",
            "semi": "Halbfinale", "third_place": "Pl. 3", "final": "Finale",
        }
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
                uid = int(u.id)
                home = jm.home_team.name if jm.home_team else (jm.home_placeholder or "?")
                away = jm.away_team.name if jm.away_team else (jm.away_placeholder or "?")
                full_pts = int(jpred.points_awarded or 0)
                joker_pts_map[uid] = full_pts
                joker_bonus_map[uid] = full_pts // 2
                joker_phase_key_map[uid] = _phase_key(jm.phase, jm.match_number)
                joker_match_map[uid] = f"{home} – {away}"
                joker_phase_map[uid] = _phase_label.get(jm.phase, jm.phase)
                pen = " n.E." if jm.went_to_penalties else ""
                joker_result_map[uid] = f"{jm.result_home}:{jm.result_away}{pen}"
                joker_pred_map[uid] = f"{jpred.pred_home}:{jpred.pred_away}"

    # ── Max. mögliche Punkte pro Nutzer (Gruppe=exact, KO=exact+bonus) ──
    scoring_cfg = get_scoring()
    exact_pts = scoring_cfg.get("exact", 4)
    ko_bonus = scoring_cfg.get("ko_advance_bonus", 1)

    user_max_pts: dict[int, int] = {}
    for uid, ph, pa, rh, ra, phase, mn in phase_pred_rows:
        uid = int(uid)
        max_game = exact_pts if phase == "group" else (exact_pts + ko_bonus)
        user_max_pts[uid] = user_max_pts.get(uid, 0) + max_game

    # ── Statistiken pro Nutzer aufbauen ──────────────────────────
    tipped_count: dict[int, int] = {}

    for uid, mid, pts in preds_stats:
        uid = int(uid)
        tipped_count[uid] = tipped_count.get(uid, 0) + 1

    stats: dict[int, dict] = {}
    for r in rows:
        uid = r.user_id
        tc = tipped_count.get(uid, 0)
        total_match_pts = sum(r.phase_points.values()) - joker_bonus_map.get(uid, 0)
        max_pts = user_max_pts.get(uid, 0)
        rating = round(total_match_pts / max_pts, 2) if max_pts > 0 else 0.0
        stats[uid] = {
            "rating": rating,
            "tipped_count": tc,
            "joker_pts": joker_pts_map.get(uid),
            "joker_match": joker_match_map.get(uid),
            "joker_phase": joker_phase_map.get(uid),
            "joker_result": joker_result_map.get(uid),
            "joker_pred": joker_pred_map.get(uid),
        }

    rows_trefferquote = sorted(rows, key=lambda r: stats[r.user_id]["rating"], reverse=True)

    def _base(r, key: str) -> int:
        """Phase-Punkte ohne Joker-Bonus."""
        bonus = joker_bonus_map.get(r.user_id, 0) if joker_phase_key_map.get(r.user_id) == key else 0
        return r.phase_points.get(key, 0) - bonus

    def _grp_base(r) -> int:
        grp_keys = ("st1", "st2", "st3")
        raw = r.phase_points.get("st1", 0) + r.phase_points.get("st2", 0) + r.phase_points.get("st3", 0)
        bonus = joker_bonus_map.get(r.user_id, 0) if joker_phase_key_map.get(r.user_id) in grp_keys else 0
        return raw - bonus

    def _ko_base(r) -> int:
        ko_raw = sum(r.phase_points.values()) - r.phase_points.get("st1", 0) - r.phase_points.get("st2", 0) - r.phase_points.get("st3", 0)
        grp_keys = ("st1", "st2", "st3")
        bonus = joker_bonus_map.get(r.user_id, 0) if joker_phase_key_map.get(r.user_id) not in grp_keys and joker_phase_key_map.get(r.user_id) is not None else 0
        return ko_raw - bonus

    rows_group = sorted(rows, key=_grp_base, reverse=True)
    rows_ko    = sorted(rows, key=_ko_base, reverse=True)
    rows_st1   = sorted(rows, key=lambda r: _base(r, "st1"), reverse=True)
    rows_st2   = sorted(rows, key=lambda r: _base(r, "st2"), reverse=True)
    rows_st3   = sorted(rows, key=lambda r: _base(r, "st3"), reverse=True)

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
        "joker_bonus_map": joker_bonus_map,
        "joker_phase_key_map": joker_phase_key_map,
        "phase_counts": phase_counts,
        "pool": pool,
        "top5": top5,
        "flash": request.session.pop("flash", None),
    })
