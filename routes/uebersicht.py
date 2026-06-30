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

        # ── Nutzer ──────────────────────────────────────────────────
        users_raw = list(s.scalars(select(User).where(User.is_spectator == False).order_by(User.display_name)).all())
        users = [{"id": int(u.id), "display_name": str(u.display_name), "in_pool": bool(u.in_pool)} for u in users_raw]
        uid_list = [u["id"] for u in users]

        # ── Alle Spiele ──────────────────────────────────────────────
        matches = list(s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all())
        for m in matches:
            _ = m.home_team, m.away_team
        locked_matches = [m for m in matches if m.is_locked or m.is_finished]
        locked_set = {int(m.id) for m in locked_matches}

        # ── Alle Tipps (inkl. noch nicht gesperrter Spiele) ──────────
        preds_raw = list(s.scalars(select(Prediction)).all())

        # pred_map[match_id][user_id] = (ph, pa, pts)
        pred_map: dict[int, dict[int, tuple]] = {}
        for p in preds_raw:
            pred_map.setdefault(int(p.match_id), {})[int(p.user_id)] = (
                int(p.pred_home), int(p.pred_away), int(p.points_awarded or 0)
            )

        # ── Langfrist: Gruppen-Tipps ─────────────────────────────────
        group_pred_map: dict[int, dict[str, tuple]] = {}
        for gp in s.scalars(select(GroupPrediction)).all():
            _ = gp.team_1st, gp.team_2nd
            group_pred_map.setdefault(int(gp.user_id), {})[str(gp.group_letter)] = (
                str(gp.team_1st.name) if gp.team_1st else "—",
                str(gp.team_2nd.name) if gp.team_2nd else "—",
                int(gp.points_awarded or 0),
            )

        # ── Langfrist: Gruppenresultate ──────────────────────────────
        group_results: dict[str, tuple] = {}
        for gr in s.scalars(select(GroupResult)).all():
            t1 = s.get(Team, gr.actual_1st) if gr.actual_1st else None
            t2 = s.get(Team, gr.actual_2nd) if gr.actual_2nd else None
            group_results[str(gr.group_letter)] = (
                str(t1.name) if t1 else None,
                str(t2.name) if t2 else None,
            )

        # ── Langfrist: Sonder-Tipps ──────────────────────────────────
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

        # ── Turnierergebnis ───────────────────────────────────────────
        tr = s.scalar(select(TournamentResult))
        tournament_result = None
        if tr:
            champ = s.get(Team, tr.champion_team_id) if tr.champion_team_id else None
            tournament_result = {
                "champion": str(champ.name) if champ else None,
                "scorer":   tr.top_scorer,
                "goals":    tr.total_goals,
            }

        # ── Joker-Match-Map: {user_id -> match_id} ───────────────────────
        joker_mid_map: dict[int, int] = {
            int(u.id): int(u.joker_match_id)
            for u in users_raw if u.joker_match_id is not None
        }

        # ── Joker-Info ────────────────────────────────────────────────
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
            _result = None
            if jm.result_home is not None and jm.result_away is not None:
                _result = f"{jm.result_home}:{jm.result_away}"
                if jm.went_to_penalties or jm.went_to_extra_time:
                    _result += " n.V."
                if jm.went_to_penalties and jm.penalty_home is not None:
                    _result += f" ({jm.penalty_home}:{jm.penalty_away} n.E.)"
            joker_info.append({
                "user":       str(u_raw.display_name),
                "user_id":    int(u_raw.id),
                "match":      f"{home_name} – {away_name}",
                "phase":      _phase_labels.get(_jphase_key, "Gruppenphase"),
                "pred":       f"{jpred.pred_home}:{jpred.pred_away}" if jpred else None,
                "result":     _result,
                "pts":        int(jpred.points_awarded or 0) if jpred else None,
                "has_result": bool(jm.result_home is not None),
                "is_locked":  jm.is_locked,
            })

    # ── Gruppierung: 4 fixe Abschnitte ───────────────────────────────
    SECTION_ORDER = ["st1", "st2", "st3", "ko"]
    SECTION_LABELS = {
        "st1": "Spieltag 1",
        "st2": "Spieltag 2",
        "st3": "Spieltag 3",
        "ko":  "K.o.-Phase",
    }

    def _round_key(m: Match) -> str:
        if m.phase == "group":
            no = m.match_number or 0
            if no <= 24: return "st1"
            if no <= 48: return "st2"
            return "st3"
        return "ko"

    by_date: dict[str, list[Match]] = {k: [] for k in SECTION_ORDER}
    for m in matches:
        by_date[_round_key(m)].append(m)

    # KO-Phase nach Phase gruppiert (für einklappbare Abschnitte im Tab)
    _KO_PHASE_ORDER = ["round32", "round16", "quarter", "semi", "third_place", "final"]
    _by_ko: dict[str, list] = {}
    for m in by_date["ko"]:
        _by_ko.setdefault(m.phase, []).append(m)
    ko_by_phase = [(ph, PHASES.get(ph, ph), _by_ko[ph]) for ph in _KO_PHASE_ORDER if ph in _by_ko]

    sorted_dates = SECTION_ORDER
    date_labels = SECTION_LABELS

    # ── Punkte pro Abschnitt (Punkte nicht-gesperrter Spiele = 0) ────
    date_pts: dict[str, dict[int, int]] = {}
    for dk in sorted_dates:
        date_pts[dk] = {}
        for uid in uid_list:
            date_pts[dk][uid] = sum(
                pred_map.get(int(m.id), {}).get(uid, (0, 0, 0))[2]
                for m in by_date[dk]
            )

    # ── Gesamtpunkte ─────────────────────────────────────────────────
    match_pts: dict[int, int] = {
        uid: sum(date_pts[dk].get(uid, 0) for dk in sorted_dates)
        for uid in uid_list
    }
    longterm_pts: dict[int, int] = {}
    for uid in uid_list:
        gpts = sum(v[2] for v in group_pred_map.get(uid, {}).values())
        spts = special_map.get(uid, {}).get("pts", 0)
        longterm_pts[uid] = gpts + spts

    groups_with_results = sorted(group_results.keys())

    # ── Live-Vorschau ─────────────────────────────────────────────────
    from live_preview import calc_live_preview
    from results_sync import get_live_scores
    live_pred_pts = calc_live_preview()   # {match_id: {user_id: pts}}
    live_match_ids = set(live_pred_pts.keys())
    live_scores = get_live_scores()       # {match_id: {home, away, minute, status}}

    # Live-Bonus in Abschnitts-Summen einrechnen
    match_id_to_section: dict[int, str] = {}
    for dk in sorted_dates:
        for m in by_date[dk]:
            match_id_to_section[int(m.id)] = dk

    for mid, user_pts_map in live_pred_pts.items():
        dk = match_id_to_section.get(mid)
        if dk is None:
            continue
        for uid, pts in user_pts_map.items():
            if uid in date_pts.get(dk, {}):
                date_pts[dk][uid] += pts

    # match_pts neu summieren (inkl. Live)
    match_pts = {
        uid: sum(date_pts[dk].get(uid, 0) for dk in sorted_dates)
        for uid in uid_list
    }

    _tournament_started = datetime.now(timezone.utc) >= datetime.fromisoformat(TOURNAMENT_START_UTC)
    _any_result = any(m.result_home is not None for m in locked_matches)
    langfrist_visible = _tournament_started or _any_result

    # Aktiver Tab = letzter Abschnitt mit gesperrten Spielen (Standard: st1)
    active_section = "st1"
    for dk in SECTION_ORDER:
        if any(int(m.id) in locked_set for m in by_date[dk]):
            active_section = dk

    return templates.TemplateResponse(request, "uebersicht.html", {
        "user": user, "active": "uebersicht",
        "users": users,
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
        "locked_set": locked_set,
        "active_section": active_section,
        "ko_by_phase": ko_by_phase,
        "live_pred_pts": live_pred_pts,
        "live_match_ids": live_match_ids,
        "live_scores": live_scores,
        "joker_mid_map": joker_mid_map,
    })
