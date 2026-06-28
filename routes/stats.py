from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE, PHASES
from database import get_session
from deps import require_non_spectator, require_user, templates
from models import Match, Prediction, PredictionHistory, User

router = APIRouter()


@router.get("/stats")
async def stats_get(request: Request, user: dict = Depends(require_non_spectator)):
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
        show_behavior_stats = u.show_behavior_stats if u else True

        # History für diesen User laden (prediction_id → erste Einträge = Baseline)
        user_pred_ids = [p.id for p in preds_map.values()]
        all_history: list[PredictionHistory] = []
        if user_pred_ids:
            all_history = list(s.scalars(
                select(PredictionHistory)
                .where(PredictionHistory.prediction_id.in_(user_pred_ids))
                .order_by(PredictionHistory.saved_at)
            ).all())
        # Gruppieren: pred_id → [history_entries]
        hist_by_pred: dict[int, list[PredictionHistory]] = {}
        for h in all_history:
            hist_by_pred.setdefault(h.prediction_id, []).append(h)

    # ── Basis-Statistiken ──────────────────────────────────────────────────
    total_finished = len(finished)
    tipped = sum(1 for m in finished if m.id in preds_map)

    exact = goal_diff = tendency = wrong = joker_used = 0
    best_match = None
    best_pts = -1
    phase_pts: dict[str, int] = defaultdict(int)
    cumulative: list[dict] = []   # für Formkurve: [{date, cum_pts, user_pts}]

    # Durchschnitt aller Tipper pro Spiel + Schwierigkeitsgrad
    match_avg: dict[int, float] = {}
    match_all_pts: dict[int, list[int]] = defaultdict(list)
    for p in all_preds:
        match_all_pts[p.match_id].append(p.points_awarded or 0)
    for mid, pts_list in match_all_pts.items():
        match_avg[mid] = sum(pts_list) / len(pts_list) if pts_list else 0

    # Schwerste / Leichteste Spiele (Trefferquote aller Teilnehmer)
    match_difficulty = []
    for m in finished:
        pts_list = match_all_pts.get(m.id, [])
        if len(pts_list) < 2:
            continue
        scored = sum(1 for pts in pts_list if pts > 0)
        rate = round(scored / len(pts_list) * 100)
        home = m.home_team.name if m.home_team else (m.home_placeholder or "?")
        away = m.away_team.name if m.away_team else (m.away_placeholder or "?")
        match_difficulty.append({
            "label": f"{home} vs. {away}",
            "rate": rate,
            "result": f"{m.result_home}:{m.result_away}" if m.has_result else None,
        })
    match_difficulty.sort(key=lambda x: x["rate"])
    hardest_matches = match_difficulty[:10]
    easiest_matches = list(reversed(match_difficulty[-10:]))

    cum = 0
    for m in finished:
        p = preds_map.get(m.id)
        pts = p.points_awarded if p else 0
        is_joker = m.id == joker_match_id

        if p:
            if pts >= 8 or (is_joker and pts >= 4):
                joker_used = pts if is_joker else joker_used
            ph, pa, rh, ra = p.pred_home, p.pred_away, m.result_home, m.result_away
            if ph is not None and pa is not None and rh is not None and ra is not None:
                if ph == rh and pa == ra:
                    exact += 1
                elif (ph - pa) == (rh - ra):
                    goal_diff += 1
                elif (1 if ph > pa else -1 if ph < pa else 0) == (1 if rh > ra else -1 if rh < ra else 0):
                    tendency += 1
                else:
                    wrong += 1
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

    # ── Treffersträhne (immer berechnen) ─────────────────────────────────
    streak = max_streak = 0
    streak_pts = max_streak_pts = 0
    for m in finished:
        p = preds_map.get(m.id)
        pts = p.points_awarded or 0 if p else 0
        if p and pts > 0:
            streak += 1
            streak_pts += pts
            if streak > max_streak:
                max_streak = streak
                max_streak_pts = streak_pts
        else:
            streak = 0
            streak_pts = 0
    current_streak = streak
    current_streak_pts = streak_pts

    # ── Verhaltens-Statistiken (nur wenn aktiviert) ───────────────────────
    time_blocks = peak_block = None
    corr_pts: list[int] = []
    uncorr_pts: list[int] = []
    corr_avg = uncorr_avg = None
    early_pts_list: list[int] = []
    late_pts_list:  list[int] = []
    avg_lead_h = early_avg = late_avg = None
    hist_gained: list[int] = []
    hist_lost:   list[int] = []
    hist_neutral: int = 0
    hist_direct:  int = 0
    hist_net: int = 0
    hist_gained_details: list[dict] = []
    hist_lost_details:   list[dict] = []

    if show_behavior_stats:
        hour_counts = [0] * 24
        for m in finished:
            p = preds_map.get(m.id)
            if p and p.created_at:
                dt = p.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                hour_counts[dt.astimezone(DISPLAY_TIMEZONE).hour] += 1

        time_blocks = {
            "Morgens": sum(hour_counts[h] for h in range(6, 12)),
            "Mittags": sum(hour_counts[h] for h in range(12, 18)),
            "Abends":  sum(hour_counts[h] for h in range(18, 22)),
            "Nachts":  sum(hour_counts[h] for h in list(range(22, 24)) + list(range(0, 6))),
        }
        _block_labels = {
            "Morgens": "Morgens (6–11 Uhr)",
            "Mittags": "Mittags (12–17 Uhr)",
            "Abends":  "Abends (18–21 Uhr)",
            "Nachts":  "Nachts (22–5 Uhr)",
        }
        _peak_key = max(time_blocks, key=time_blocks.get) if any(time_blocks.values()) else None
        peak_block = _block_labels.get(_peak_key) if _peak_key else None

        # Scoring-Hilfsfunktion
        from settings import get_scoring as _get_scoring
        _cfg = _get_scoring()
        _exact = _cfg.get("exact", 4)
        _gdiff = _cfg.get("goal_diff", 2)
        _tend  = _cfg.get("tendency", 1)

        def _calc(ph: int, pa: int, rh: int, ra: int, phase: str) -> int:
            if ph == rh and pa == ra:
                return _exact
            elif (ph - pa) == (rh - ra):
                return _gdiff
            else:
                def _sgn(x): return 1 if x > 0 else (-1 if x < 0 else 0)
                if _sgn(ph - pa) == _sgn(rh - ra) and _sgn(ph - pa) != 0:
                    return _tend
                return 0

        # History-basierte Korrektur-Auswertung
        for m in finished:
            p = preds_map.get(m.id)
            if p is None or not m.has_result:
                continue
            entries = hist_by_pred.get(p.id, [])
            if len(entries) <= 1:
                # Nur Baseline = nie korrigiert (oder kein History-Eintrag)
                hist_direct += 1
                uncorr_pts.append(p.points_awarded or 0)
                continue
            # Korrigiert: erstes Entry = Baseline/Original
            orig = entries[0]
            orig_pts = _calc(orig.pred_home, orig.pred_away,
                             m.result_home, m.result_away, m.phase)
            actual_pts = p.points_awarded or 0
            diff = actual_pts - orig_pts
            home_name = m.home_team.name if m.home_team else (m.home_placeholder or "TBD")
            away_name = m.away_team.name if m.away_team else (m.away_placeholder or "TBD")
            detail = {
                "home": home_name,
                "away": away_name,
                "orig": f"{orig.pred_home}:{orig.pred_away}",
                "final": f"{p.pred_home}:{p.pred_away}",
                "result": f"{m.result_home}:{m.result_away}",
                "diff": diff,
            }
            if diff > 0:
                hist_gained.append(diff)
                hist_gained_details.append(detail)
            elif diff < 0:
                hist_lost.append(diff)
                hist_lost_details.append(detail)
            else:
                hist_neutral += 1
            corr_pts.append(actual_pts)

        corr_avg   = round(sum(corr_pts)   / len(corr_pts),   2) if corr_pts   else None
        uncorr_avg = round(sum(uncorr_pts) / len(uncorr_pts), 2) if uncorr_pts else None
        hist_net = sum(hist_gained) + sum(hist_lost)

        lead_hours_list: list[float] = []
        for m in finished:
            p = preds_map.get(m.id)
            if p and m.kickoff_utc and p.created_at:
                koff    = m.kickoff_utc if m.kickoff_utc.tzinfo else m.kickoff_utc.replace(tzinfo=timezone.utc)
                created = p.created_at  if p.created_at.tzinfo  else p.created_at.replace(tzinfo=timezone.utc)
                hours   = (koff - created).total_seconds() / 3600
                if 0 < hours < 8760:
                    lead_hours_list.append(hours)
                    (early_pts_list if hours > 24 else late_pts_list).append(p.points_awarded or 0)

        avg_lead_h = round(sum(lead_hours_list) / len(lead_hours_list), 1) if lead_hours_list else None
        early_avg  = round(sum(early_pts_list)  / len(early_pts_list),  2) if early_pts_list  else None
        late_avg   = round(sum(late_pts_list)   / len(late_pts_list),   2) if late_pts_list   else None

    # ── Joker-Info (Paarung, Phase, Ergebnis, Punkte) ────────────────────
    joker_info = None
    if joker_match_id:
        jm = next((m for m in finished if m.id == joker_match_id), None)
        if jm:
            jp = preds_map.get(joker_match_id)
            joker_info = {
                "home": jm.home_team.name if jm.home_team else (jm.home_placeholder or "TBD"),
                "away": jm.away_team.name if jm.away_team else (jm.away_placeholder or "TBD"),
                "phase": PHASES.get(jm.phase, jm.phase),
                "match_number": jm.match_number,
                "result": f"{jm.result_home}:{jm.result_away}" if jm.has_result else None,
                "pts": jp.points_awarded if jp else 0,
                "is_finished": True,
            }
        else:
            # Joker gesetzt, Spiel noch nicht beendet → aus DB nachladen
            from models import Match as _Match
            with get_session() as sj:
                jm2 = sj.get(_Match, joker_match_id)
                if jm2:
                    _ = jm2.home_team, jm2.away_team
                    joker_info = {
                        "home": jm2.home_team.name if jm2.home_team else (jm2.home_placeholder or "TBD"),
                        "away": jm2.away_team.name if jm2.away_team else (jm2.away_placeholder or "TBD"),
                        "phase": PHASES.get(jm2.phase, jm2.phase),
                        "match_number": jm2.match_number,
                        "result": None,
                        "pts": None,
                        "is_finished": False,
                    }

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
                    ph2, pa2, rh2, ra2 = p2.pred_home, p2.pred_away, m.result_home, m.result_away
                    if ph2 is not None and pa2 is not None and rh2 is not None and ra2 is not None:
                        if ph2 == rh2 and pa2 == ra2:
                            u2_exact += 1
                        elif (ph2 - pa2) == (rh2 - ra2):
                            u2_goal_diff += 1
                        elif (1 if ph2 > pa2 else -1 if ph2 < pa2 else 0) == (1 if rh2 > ra2 else -1 if rh2 < ra2 else 0):
                            u2_tendency += 1
                        else:
                            u2_wrong += 1
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
        # Neue Stats
        "time_blocks": time_blocks,
        "peak_block": peak_block,
        "joker_info": joker_info,
        "show_behavior_stats": show_behavior_stats,
        "corr_count": len(corr_pts),
        "uncorr_count": len(uncorr_pts),
        "corr_avg": corr_avg,
        "uncorr_avg": uncorr_avg,
        "early_count": len(early_pts_list),
        "late_count": len(late_pts_list),
        "early_avg": early_avg,
        "late_avg": late_avg,
        "avg_lead_h": avg_lead_h,
        "max_streak": max_streak,
        "max_streak_pts": max_streak_pts,
        "current_streak": current_streak,
        "current_streak_pts": current_streak_pts,
        "hist_gained_count": len(hist_gained),
        "hist_gained_pts": sum(hist_gained),
        "hist_lost_count": len(hist_lost),
        "hist_lost_pts": sum(hist_lost),
        "hist_neutral": hist_neutral,
        "hist_direct": hist_direct,
        "hist_net": hist_net,
        "hist_gained_details": hist_gained_details,
        "hist_lost_details": hist_lost_details,
        "hardest_matches": hardest_matches,
        "easiest_matches": easiest_matches,
    })
