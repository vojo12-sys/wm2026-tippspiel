"""
live_preview.py
===============
Berechnet vorläufige Punkte für laufende Spiele (Live-Cache) ohne DB-Write.
Berücksichtigt Scoring-Konfiguration, KO-Bonus und Joker.
"""
from __future__ import annotations

from sqlalchemy import select

from database import get_session
from models import Match, Prediction, User
from results_sync import get_live_scores
from settings import get_scoring


def _sign(x: int) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def calc_live_preview() -> dict[int, dict[int, int]]:
    """
    Gibt {match_id: {user_id: provisional_pts}} für alle laufenden Spiele zurück.
    Leeres Dict wenn kein Spiel live ist.
    """
    live = get_live_scores()
    if not live:
        return {}

    scoring = get_scoring()
    result: dict[int, dict[int, int]] = {}

    with get_session() as s:
        joker_map: dict[int, int | None] = {
            u.id: u.joker_match_id
            for u in s.scalars(select(User)).all()
        }

        for match_id, live_data in live.items():
            m = s.get(Match, match_id)
            if not m:
                continue

            lh: int = live_data["home"]
            la: int = live_data["away"]
            is_ko = m.phase != "group"

            preds = s.scalars(
                select(Prediction).where(Prediction.match_id == match_id)
            ).all()

            match_pts: dict[int, int] = {}
            for p in preds:
                if p.pred_home is None or p.pred_away is None:
                    continue
                ph, pa = p.pred_home, p.pred_away

                pts = 0
                if ph == lh and pa == la:
                    pts = scoring.get("exact", 4)
                elif (ph - pa) == (lh - la):
                    pts = scoring.get("goal_diff", 3)
                elif _sign(ph - pa) == _sign(lh - la):
                    pts = scoring.get("tendency", 2)

                # KO-Bonus nur wenn aktuell klarer Sieger (kein Unentschieden)
                if pts > 0 and is_ko and lh != la:
                    pred_winner = "home" if ph > pa else ("away" if pa > ph else None)
                    live_winner = "home" if lh > la else "away"
                    if pred_winner == live_winner:
                        pts += scoring.get("ko_advance_bonus", 1)

                if joker_map.get(p.user_id) == match_id:
                    pts *= 2

                match_pts[int(p.user_id)] = pts

            result[match_id] = match_pts

    return result
