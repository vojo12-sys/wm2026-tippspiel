"""
standings.py
============
Berechnet die Rangliste (alle Teilnehmer) und die Kasse/Topf-Auszahlung
(nur Einzahler).

Wichtig – das mit Wolfgang abgestimmte Modell:
  * Alle Teilnehmer stehen in der sportlichen Gesamtwertung (Punkte zählen
    für jeden, egal ob er Geld gesetzt hat).
  * Der Topf wird NUR unter den Einzahlern (in_pool & has_paid) aufgeteilt,
    nach deren Reihenfolge innerhalb der Zahler-Gruppe.
  * Ein Nicht-Zahler kann die Gesamtwertung gewinnen – das Geld geht dann an
    den bestplatzierten Zahler. Wird im Dashboard transparent angezeigt.
  * Auszahlungsschlüssel skaliert automatisch mit der Zahl der Einzahler.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from database import get_session
from models import GroupPrediction, Prediction, SpecialTip, User
from settings import get_pool


# ---------------------------------------------------------------------------
# Rangliste
# ---------------------------------------------------------------------------

@dataclass
class Standing:
    user_id: int
    display_name: str
    in_pool: bool
    has_paid: bool
    total_points: int = 0
    phase_points: dict[str, int] = field(default_factory=dict)  # phase-key -> Punkte
    longterm_points: int = 0   # Gruppen- + Sonder-Tipps
    rank: int = 0
    exact_count: int = 0
    goal_diff_count: int = 0
    tendency_count: int = 0


def compute_standings() -> list[Standing]:
    """Liefert die Gesamtrangliste, absteigend nach Punkten."""
    with get_session() as session:
        users = session.scalars(select(User).where(User.is_spectator == False)).all()

        # Spiel-Tipp-Punkte je Nutzer und Phase – nur abgeschlossene Spiele
        from models import Match
        from settings import get_scoring as _gs
        _sc = _gs()

        match_info = {
            mid: (phase, match_number, rh, ra)
            for mid, phase, match_number, rh, ra in session.execute(
                select(Match.id, Match.phase, Match.match_number, Match.result_home, Match.result_away)
            ).all()
        }

        finished_ids = session.scalars(
            select(Match.id).where(Match.is_finished.is_(True))
        ).all()

        rows = session.execute(
            select(Prediction.user_id, Prediction.points_awarded, Prediction.match_id,
                   Prediction.pred_home, Prediction.pred_away)
            .where(Prediction.match_id.in_(finished_ids))
        ).all() if finished_ids else []

        def _phase_key(phase: str, match_number: int | None) -> str:
            if phase == "group":
                mn = match_number or 0
                if mn <= 24:  return "st1"
                if mn <= 48:  return "st2"
                return "st3"
            return phase

        match_pts: dict[int, dict[str, int]] = {}
        exact_c: dict[int, int] = {}
        goal_diff_c: dict[int, int] = {}
        tendency_c: dict[int, int] = {}

        def _sign(x: int) -> int:
            return 1 if x > 0 else (-1 if x < 0 else 0)

        for uid, pts, mid, ph, pa in rows:
            info = match_info.get(mid)
            raw_phase = info[0] if info else "group"
            match_num = info[1] if info else None
            rh, ra    = (info[2], info[3]) if info else (None, None)
            phase     = _phase_key(raw_phase, match_num)

            match_pts.setdefault(uid, {}).setdefault(phase, 0)
            match_pts[uid][phase] += pts or 0

            # Klassifizierung direkt aus Tipp vs. Ergebnis – unabhängig von
            # KO-Bonus oder Joker, die in points_awarded eingerechnet sind.
            if rh is not None and ra is not None and ph is not None and pa is not None:
                if ph == rh and pa == ra:
                    exact_c[uid] = exact_c.get(uid, 0) + 1
                elif (ph - pa) == (rh - ra):
                    goal_diff_c[uid] = goal_diff_c.get(uid, 0) + 1
                elif _sign(ph - pa) == _sign(rh - ra):
                    tendency_c[uid] = tendency_c.get(uid, 0) + 1

        # Langfrist: Gruppen-Tipps
        group_pts: dict[int, int] = {}
        for uid, pts in session.execute(
            select(GroupPrediction.user_id, GroupPrediction.points_awarded)
        ).all():
            group_pts[uid] = group_pts.get(uid, 0) + (pts or 0)

        # Langfrist: Sonder-Tipps
        special_pts: dict[int, int] = {}
        for uid, pts in session.execute(
            select(SpecialTip.user_id, SpecialTip.points_awarded)
        ).all():
            special_pts[uid] = special_pts.get(uid, 0) + (pts or 0)

        standings: list[Standing] = []
        for u in users:
            phases = match_pts.get(u.id, {})
            longterm = group_pts.get(u.id, 0) + special_pts.get(u.id, 0)
            total = sum(phases.values()) + longterm
            standings.append(Standing(
                user_id=u.id,
                display_name=u.display_name,
                in_pool=u.in_pool,
                has_paid=u.has_paid,
                total_points=total,
                phase_points=phases,
                longterm_points=longterm,
                exact_count=exact_c.get(u.id, 0),
                goal_diff_count=goal_diff_c.get(u.id, 0),
                tendency_count=tendency_c.get(u.id, 0),
            ))

    # Sortierung: Punkte absteigend, dann Name (stabiler Tiebreak)
    standings.sort(key=lambda s: (-s.total_points, s.display_name.lower()))

    # Ränge mit gleicher Platzierung bei Punktgleichheit ("competition ranking")
    last_points = None
    last_rank = 0
    for i, st in enumerate(standings, start=1):
        if st.total_points != last_points:
            last_rank = i
            last_points = st.total_points
        st.rank = last_rank
    return standings


# ---------------------------------------------------------------------------
# Kasse / Topf-Auszahlung
# ---------------------------------------------------------------------------

@dataclass
class PoolPayout:
    user_id: int
    display_name: str
    pool_rank: int       # Platz innerhalb der Einzahler
    overall_rank: int    # Platz in der Gesamtwertung
    amount: float        # Auszahlung in EUR


@dataclass
class PoolSummary:
    enabled: bool
    buy_in: float
    currency: str
    payers: int
    pot_total: float
    paid_in: float                 # bereits eingezahlt (has_paid)
    outstanding: float             # noch offen (in_pool, aber nicht has_paid)
    payouts: list[PoolPayout] = field(default_factory=list)


def _tier_structure(pool: dict, n_payers: int) -> list[float]:
    """Wählt die richtige Auszahlungsstufe basierend auf der Einzahlerzahl."""
    tiers = pool.get("payout_tiers", {})
    thresholds = pool.get("tier_thresholds", [15, 20])
    if len(thresholds) >= 2 and n_payers >= thresholds[1] and "5" in tiers:
        base = tiers["5"]
    elif len(thresholds) >= 1 and n_payers >= thresholds[0] and "4" in tiers:
        base = tiers["4"]
    else:
        base = tiers.get("3", pool.get("payout_structure", [0.60, 0.30, 0.10]))
    return _scaled_structure(base, n_payers)


def _scaled_structure(base: list[float], n_payers: int) -> list[float]:
    """Passt den Auszahlungsschlüssel an die Zahl der Einzahler an und
    renormiert auf Summe 1.0. Beispiel: [0.6,0.3,0.1] bei 2 Zahlern
    -> [0.6,0.3] -> [0.667,0.333]; bei 1 Zahler -> [1.0]."""
    if n_payers <= 0:
        return []
    cut = base[:n_payers]
    total = sum(cut)
    if total <= 0:
        return [1.0 / n_payers] * n_payers
    return [x / total for x in cut]


def compute_pool(standings: list[Standing] | None = None) -> PoolSummary:
    """Berechnet Topfgröße und Auszahlung – nur unter den Einzahlern."""
    pool = get_pool()
    if standings is None:
        standings = compute_standings()

    buy_in = float(pool["buy_in"])
    currency = pool.get("currency", "EUR")

    # Einzahler = Opt-in. Für den Topf zählt das tatsächlich gezahlte Geld;
    # für die Reihenfolge alle Opt-in-Teilnehmer.
    opted_in = [s for s in standings if s.in_pool]
    paid = [s for s in opted_in if s.has_paid]

    summary = PoolSummary(
        enabled=bool(pool.get("enabled", True)),
        buy_in=buy_in,
        currency=currency,
        payers=len(opted_in),
        pot_total=round(len(opted_in) * buy_in, 2),
        paid_in=round(len(paid) * buy_in, 2),
        outstanding=round((len(opted_in) - len(paid)) * buy_in, 2),
    )

    if not summary.enabled or summary.payers == 0:
        return summary

    # Einzahler in der bereits sortierten Gesamtreihenfolge -> relative Rangfolge
    ranked_payers = [s for s in standings if s.in_pool]  # behält Gesamt-Sortierung
    structure = _tier_structure(pool, len(ranked_payers))

    # Auszahlung; faire Behandlung von Punktgleichheit auf bezahlten Plätzen:
    # gleich punktende Einzahler teilen sich die Summe ihrer Plätze.
    i = 0
    n_tiers = len(structure)
    pot = summary.pot_total
    while i < len(ranked_payers):
        # Gruppe gleicher Punktzahl bestimmen
        j = i
        while j + 1 < len(ranked_payers) and \
                ranked_payers[j + 1].total_points == ranked_payers[i].total_points:
            j += 1
        tie_members = ranked_payers[i:j + 1]
        # Anteile der von dieser Gruppe belegten Plätze summieren
        share_sum = sum(structure[k] for k in range(i, min(j + 1, n_tiers)))
        per_member = (pot * share_sum) / len(tie_members) if share_sum > 0 else 0.0
        for rank_offset, st in enumerate(tie_members):
            if per_member > 0:
                summary.payouts.append(PoolPayout(
                    user_id=st.user_id,
                    display_name=st.display_name,
                    pool_rank=i + 1,  # gemeinsamer Platz bei Gleichstand
                    overall_rank=st.rank,
                    amount=round(per_member, 2),
                ))
        i = j + 1

    return summary
