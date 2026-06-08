from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE, PHASES, TOURNAMENT_START_UTC
from database import get_session
from deps import require_user, templates
from models import GroupPrediction, GroupResult, Match, Prediction, SpecialTip, Team, TournamentResult, User

router = APIRouter()


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m. %H:%M")


@router.get("/uebersicht")
async def uebersicht_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    with get_session() as s:

        # ── Nutzer (als plain dicts) ──────────────────────────────
        users_raw = list(s.scalars(select(User).order_by(User.display_name)).all())
        users = [{"id": int(u.id), "display_name": str(u.display_name), "in_pool": bool(u.in_pool)} for u in users_raw]
        uid_list = [u["id"] for u in users]

        # ── Gesperrte Spiele ─────────────────────────────────────
        matches = list(s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all())
        for m in matches:
            _ = m.home_team, m.away_team
        locked_matches = [m for m in matches if m.is_locked or m.is_finished]
        locked_ids = [int(m.id) for m in locked_matches]

        # ── Spiel-Tipps ──────────────────────────────────────────
        preds_raw = s.execute(
            select(Prediction).where(Prediction.match_id.in_(locked_ids))
        ).scalars().all() if locked_ids else []

        # pred_map[match_id][user_id] = (ph, pa, pts)
        pred_map: dict[int, dict[int, tuple]] = {}
        for p in preds_raw:
            pred_map.setdefault(int(p.match_id), {})[int(p.user_id)] = (
                int(p.pred_home), int(p.pred_away), int(p.points_awarded or 0)
            )

        # ── Langfrist: Gruppen-Tipps ─────────────────────────────
        group_pred_map: dict[int, dict[str, tuple]] = {}
        for gp in s.scalars(select(GroupPrediction)).all():
            _ = gp.team_1st, gp.team_2nd
            group_pred_map.setdefault(int(gp.user_id), {})[str(gp.group_letter)] = (
                str(gp.team_1st.name) if gp.team_1st else "—",
                str(gp.team_2nd.name) if gp.team_2nd else "—",
                int(gp.points_awarded or 0),
            )

        # ── Langfrist: Gruppenresultate ──────────────────────────
        group_results: dict[str, tuple] = {}
        for gr in s.scalars(select(GroupResult)).all():
            t1 = s.get(Team, gr.actual_1st) if gr.actual_1st else None
            t2 = s.get(Team, gr.actual_2nd) if gr.actual_2nd else None
            group_results[str(gr.group_letter)] = (
                str(t1.name) if t1 else None,
                str(t2.name) if t2 else None,
            )

        # ── Langfrist: Sonder-Tipps ──────────────────────────────
        # special_map[user_id] = {champion, scorer, goals, pts}
        from settings import get_scoring as _gs_sc
        _sc = _gs_sc()
        special_map: dict[int, dict] = {}
        for sp in s.scalars(select(SpecialTip)).all():
            _ = sp.champion_team
            special_map[int(sp.user_id)] = {
                "champion":    str(sp.champion_team.name) if sp.champion_team else "—",
                "scorer":      str(sp.top_scorer) if sp.top_scorer else "—",
                "goals":       sp.total_goals,
                "pts":         int(sp.points_awarded or 0),
                "champion_id": sp.champion_team_id,
                "scorer_raw":  sp.top_scorer,
                "goals_raw":   sp.total_goals,
                "champion_pts_val": _sc.get("champion", 15),
                "scorer_pts_val":   _sc.get("top_scorer", 10),
                "goals_pts_val":    _sc.get("total_goals", 5),
                "goals_tol":        _sc.get("total_goals_tolerance", 5),
            }

        # ── Turnierergebnis ───────────────────────────────────────
        tr = s.scalar(select(TournamentResult))
        tournament_result = None
        if tr:
            champ = s.get(Team, tr.champion_team_id) if tr.champion_team_id else None
            tournament_result = {
                "champion": str(champ.name) if champ else None,
                "scorer":   tr.top_scorer,
                "goals":    tr.total_goals,
            }

        # ── Joker-Info ────────────────────────────────────────────
        joker_info = []
        for u_raw in users_raw:
            if u_raw.joker_match_id is None:
                continue
            jm = s.get(Match, u_raw.joker_match_id)
            if not jm:
                continue
            _ = jm.home_team, jm.away_team
            home_name = str(jm.home_team.name) if jm.home_team else str(jm.home_placeholder or "TBD")
            away_name = str(jm.away_team.name) if jm.away_team else str(jm.away_placeholder or "TBD")
            jpred = s.scalar(
                select(Prediction).where(
                    Prediction.user_id == u_raw.id,
                    Prediction.match_id == jm.id,
                )
            )
            _phase_labels = {
                "st1": "Spieltag 1", "st2": "Spieltag 2", "st3": "Spieltag 3",
                "round32": "Sechzehntelfinale", "round16": "Achtelfinale",
                "quarter": "Viertelfinale", "semi": "Halbfinale",
                "third_place": "Spiel um Platz 3", "final": "Finale",
            }
            if jm.phase == "group":
                _mn = jm.match_number or 0
                _jphase_key = "st1" if _mn <= 24 else "st2" if _mn <= 48 else "st3"
            else:
                _jphase_key = jm.phase
            joker_info.append({
                "user":       str(u_raw.display_name),
                "user_id":    int(u_raw.id),
                "match":      f"{home_name} – {away_name}",
                "phase":      _phase_labels.get(_jphase_key, "Gruppenphase"),
                "pred":       f"{jpred.pred_home}:{jpred.pred_away}" if jpred else None,
                "pts":        int(jpred.points_awarded or 0) if jpred else None,
                "has_result": bool(jm.result_home is not None),
                "is_locked":  jm.is_locked,
            })

    # ── Nach Turnierphase/Spieltag gruppieren ────────────────────
    ROUND_ORDER = ["st1", "st2", "st3", "round32", "round16", "quarter", "semi", "third_place", "final"]
    ROUND_LABELS = {
        "st1":         "Spieltag 1",
        "st2":         "Spieltag 2",
        "st3":         "Spieltag 3",
        "round32":     "Sechzehntelfinale",
        "round16":     "Achtelfinale",
        "quarter":     "Viertelfinale",
        "semi":        "Halbfinale",
        "third_place": "Spiel um Platz 3",
        "final":       "Finale",
    }

    def _round_key(m: Match) -> str:
        if m.phase == "group":
            no = m.match_number or 0
            if no <= 24:  return "st1"
            if no <= 48:  return "st2"
            return "st3"
        return m.phase or "?"

    by_date: dict[str, list[Match]] = {}
    date_labels: dict[str, str] = {}
    for m in locked_matches:
        dk = _round_key(m)
        by_date.setdefault(dk, []).append(m)
        date_labels[dk] = ROUND_LABELS.get(dk, dk)
    sorted_dates = [k for k in ROUND_ORDER if k in by_date]

    # ── Punkte pro Spieltag pro Nutzer ───────────────────────────
    # date_pts[date_key][user_id] = punkte an diesem tag
    date_pts: dict[str, dict[int, int]] = {}
    for dk in sorted_dates:
        date_pts[dk] = {}
        for uid in uid_list:
            total = 0
            for m in by_date[dk]:
                tip = pred_map.get(int(m.id), {}).get(uid)
                if tip:
                    total += tip[2]
            date_pts[dk][uid] = total

    # ── Gesamtpunkte pro Nutzer ───────────────────────────────────
    match_pts:    dict[int, int] = {uid: sum(date_pts[dk].get(uid, 0) for dk in sorted_dates) for uid in uid_list}
    longterm_pts: dict[int, int] = {}
    for uid in uid_list:
        gpts = sum(v[2] for v in group_pred_map.get(uid, {}).values())
        spts = special_map.get(uid, {}).get("pts", 0)
        longterm_pts[uid] = gpts + spts

    groups_with_results = sorted(group_results.keys())

    _tournament_started = datetime.now(timezone.utc) >= datetime.fromisoformat(TOURNAMENT_START_UTC)
    _any_result = any(m.result_home is not None for m in locked_matches)
    langfrist_visible = _tournament_started or _any_result

    # ── by_phase für Kompatibilität ───────────────────────────────
    by_phase: dict[str, list[Match]] = {}
    for m in locked_matches:
        by_phase.setdefault(m.phase, []).append(m)

    return templates.TemplateResponse(request, "uebersicht.html", {
        "user": user, "active": "uebersicht",
        "users": users,
        "by_phase": by_phase,
        "by_date": by_date,
        "date_labels": date_labels,
        "sorted_dates": sorted_dates,
        "date_pts": date_pts,
        "match_pts": match_pts,
        "longterm_pts": longterm_pts,
        "pred_map": pred_map,
        "phases": PHASES,
        "fmt": _fmt,
        "group_pred_map": group_pred_map,
        "group_results": group_results,
        "groups_with_results": groups_with_results,
        "special_map": special_map,
        "tournament_result": tournament_result,
        "langfrist_visible": langfrist_visible,
        "flash": request.session.pop("flash", None),
        "joker_info": joker_info,
    })
