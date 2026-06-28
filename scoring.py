"""
scoring.py
==========
Die Punkte-Engine. Vollständig konfigurierbar über settings.get_scoring().

Logik Spiel-Tipp (Ergebnis ph:pa, tatsächlich rh:ra):
  exakt           ph==rh und pa==ra
  Tordifferenz    (ph-pa) == (rh-ra), aber nicht exakt  (inkl. richtiges Remis
                  mit falschem Ergebnis, z. B. Tipp 1:1, real 2:2)
  Tendenz         gleicher Sieger (Heim/Auswärts) – Remis ist über die
                  Tordifferenz bereits abgedeckt

Logik Gruppen-Tipp:
  je richtig getroffener 1./2. Platz separate Punkte.

Logik Sonder-Tipps:
  Weltmeister, Torschützenkönig (Name, case-insensitive),
  Gesamttore (innerhalb Toleranz).
"""

from __future__ import annotations

from sqlalchemy import select

from database import get_session
from models import (
    GroupPrediction, GroupResult, Match, Prediction, SpecialTip,
    TournamentResult, User,
)
from settings import get_scoring


# ---------------------------------------------------------------------------
# Einzeltipp-Bewertung (reine Funktionen, leicht testbar)
# ---------------------------------------------------------------------------

def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def score_match_prediction(
    ph: int, pa: int, rh: int, ra: int,
    scoring: dict | None = None,
    **_kwargs,
) -> int:
    """Punkte für einen einzelnen Spiel-Tipp."""
    s = scoring or get_scoring()

    if ph == rh and pa == ra:
        return s["exact"]
    if (ph - pa) == (rh - ra):
        return s["goal_diff"]
    if _sign(ph - pa) == _sign(rh - ra):
        return s["tendency"]
    return 0


# ---------------------------------------------------------------------------
# Gesamt-Neuberechnung (nach Ergebniseintrag aufrufen)
# ---------------------------------------------------------------------------

def recalculate_match(match_id: int) -> None:
    """Bewertet alle Tipps zu EINEM Spiel neu (z. B. direkt nach Ergebniseintrag)."""
    s = get_scoring()
    with get_session() as session:
        match = session.get(Match, match_id)
        if match is None or not match.has_result:
            return
        joker_users = {
            u.id for u in session.scalars(
                select(User).where(User.joker_match_id == match_id)
            ).all()
        }
        preds = session.scalars(
            select(Prediction).where(Prediction.match_id == match_id)
        ).all()
        for p in preds:
            pts = score_match_prediction(
                p.pred_home, p.pred_away, match.result_home, match.result_away,
                scoring=s,
            )
            # Joker verdoppelt die Punkte
            if p.user_id in joker_users:
                pts *= 2
            p.points_awarded = pts


def recalculate_all_matches() -> None:
    """Bewertet alle abgeschlossenen Spiele neu (z. B. nach Punktesystem-Änderung)."""
    with get_session() as session:
        ids = session.scalars(
            select(Match.id).where(Match.is_finished.is_(True))
        ).all()
    for mid in ids:
        recalculate_match(mid)


def recalculate_group_predictions() -> None:
    """Bewertet alle Gruppen-Tipps anhand der tatsächlichen Platzierungen."""
    s = get_scoring()
    with get_session() as session:
        results = {gr.group_letter: gr for gr in session.scalars(select(GroupResult)).all()}
        preds = session.scalars(select(GroupPrediction)).all()
        for gp in preds:
            res = results.get(gp.group_letter)
            pts = 0
            if res:
                if res.actual_1st is not None:
                    if gp.predicted_1st == res.actual_1st:
                        pts += s["group_first"]
                    elif gp.predicted_2nd == res.actual_1st:
                        pts += s["group_partial_credit"]
                if res.actual_2nd is not None:
                    if gp.predicted_2nd == res.actual_2nd:
                        pts += s["group_second"]
                    elif gp.predicted_1st == res.actual_2nd:
                        pts += s["group_partial_credit"]
            gp.points_awarded = pts


def recalculate_special_tips() -> None:
    """Bewertet die Sonder-Tipps (Weltmeister/Torschütze/Gesamttore)."""
    s = get_scoring()
    with get_session() as session:
        actual = session.get(TournamentResult, 1)
        tips = session.scalars(select(SpecialTip)).all()
        for t in tips:
            pts = 0
            if actual:
                if actual.champion_team_id is not None and t.champion_team_id == actual.champion_team_id:
                    pts += s["champion"]
                if actual.top_scorer and t.top_scorer and \
                        t.top_scorer.strip().lower() == actual.top_scorer.strip().lower():
                    pts += s["top_scorer"]
                if actual.total_goals is not None and t.total_goals is not None and \
                        abs(t.total_goals - actual.total_goals) <= s["total_goals_tolerance"]:
                    pts += s["total_goals"]
            t.points_awarded = pts


def update_total_goals() -> None:
    """Summiert Tore aller abgeschlossenen Spiele (90min + Verlängerung, keine Elfmeter)
    und schreibt das Ergebnis in TournamentResult.total_goals."""
    from models import TournamentResult
    with get_session() as session:
        finished = session.scalars(
            select(Match).where(Match.is_finished.is_(True))
        ).all()
        total = sum((m.result_home or 0) + (m.result_away or 0) for m in finished)
        tr = session.get(TournamentResult, 1)
        if tr is None:
            tr = TournamentResult(id=1)
            session.add(tr)
        tr.total_goals = total
    recalculate_special_tips()


def recalculate_everything() -> None:
    """Komplette Neubewertung – nützlich nach einer Punktesystem-Änderung."""
    recalculate_all_matches()
    recalculate_group_predictions()
    update_total_goals()
