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

import json

from database import get_session
from models import GroupPrediction, Prediction, Setting, SpecialTip, User
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
    prev_rank: int = 0
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

    # Sortierung: Punkte → Exakte Tipps → Tordifferenz → Tendenz → Name
    standings.sort(key=lambda s: (
        -s.total_points, -s.exact_count, -s.goal_diff_count, -s.tendency_count,
        s.display_name.lower()
    ))

    # Gleicher Rang nur wenn alle Kriterien identisch sind
    last_key = None
    last_rank = 0
    for i, st in enumerate(standings, start=1):
        key = (st.total_points, st.exact_count, st.goal_diff_count, st.tendency_count)
        if key != last_key:
            last_rank = i
            last_key = key
        st.rank = last_rank

    # Vorherige Ränge aus Snapshot laden
    snapshot = _load_rank_snapshot()
    for st in standings:
        st.prev_rank = snapshot.get(st.user_id, 0)

    return standings


def _load_rank_snapshot() -> dict[int, int]:
    with get_session() as s:
        setting = s.get(Setting, "rank_snapshot")
        if setting:
            try:
                return {int(k): v for k, v in json.loads(setting.value).items()}
            except Exception:
                pass
    return {}


def save_rank_snapshot(standings: list[Standing]) -> None:
    """Speichert aktuelle Ränge als Vergleichsbasis (vor Ergebnis-Sync aufrufen)."""
    snapshot = json.dumps({str(st.user_id): st.rank for st in standings})
    with get_session() as s:
        setting = s.get(Setting, "rank_snapshot")
        if setting:
            setting.value = snapshot
        else:
            s.add(Setting(key="rank_snapshot", value=snapshot))


def save_phase_rank_snapshot(phase: str, uid_rank: dict[int, int]) -> None:
    key = f"rank_snapshot_{phase}"
    value = json.dumps({str(uid): r for uid, r in uid_rank.items()})
    with get_session() as s:
        setting = s.get(Setting, key)
        if setting:
            setting.value = value
        else:
            s.add(Setting(key=key, value=value))


def load_phase_rank_snapshot(phase: str) -> dict[int, int]:
    key = f"rank_snapshot_{phase}"
    with get_session() as s:
        setting = s.get(Setting, key)
        if setting:
            try:
                return {int(k): v for k, v in json.loads(setting.value).items()}
            except Exception:
                pass
    return {}


def _phase_ranks(standings: list[Standing], key_fn) -> dict[int, int]:
    """Hilfsfunktion: sortiert Standings nach key_fn und gibt {user_id: rank} zurück."""
    sorted_rows = sorted(standings, key=key_fn, reverse=True)
    uid_rank: dict[int, int] = {}
    last_pts, last_rank = None, 0
    for i, st in enumerate(sorted_rows, 1):
        pts = key_fn(st)
        if pts != last_pts:
            last_rank = i
            last_pts = pts
        uid_rank[st.user_id] = last_rank
    return uid_rank


def save_all_rank_snapshots() -> None:
    """Speichert Gesamt- und Phasen-Rangsnapshots vor einem Ergebnis-Sync."""
    standings = compute_standings()
    save_rank_snapshot(standings)

    _KO = ("round32", "round16", "quarter", "semi", "third_place", "final")
    save_phase_rank_snapshot("st1",   _phase_ranks(standings, lambda s: s.phase_points.get("st1", 0)))
    save_phase_rank_snapshot("st2",   _phase_ranks(standings, lambda s: s.phase_points.get("st2", 0)))
    save_phase_rank_snapshot("st3",   _phase_ranks(standings, lambda s: s.phase_points.get("st3", 0)))
    save_phase_rank_snapshot("group", _phase_ranks(standings, lambda s: s.phase_points.get("st1", 0) + s.phase_points.get("st2", 0) + s.phase_points.get("st3", 0)))
    save_phase_rank_snapshot("ko",    _phase_ranks(standings, lambda s: sum(s.phase_points.get(k, 0) for k in _KO)))


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


# ---------------------------------------------------------------------------
# Treffer-Serien (über alle Nutzer) – für Homepage-Ranglisten
# ---------------------------------------------------------------------------

def compute_streak_rankings() -> list[dict]:
    """Längste und aktuelle Treffer-Serie je Nutzer, inkl. dabei erzielter Punkte."""
    from models import Match

    with get_session() as session:
        users = session.scalars(select(User).where(User.is_spectator == False)).all()
        finished_ids = session.scalars(
            select(Match.id).where(Match.is_finished.is_(True)).order_by(Match.kickoff_utc)
        ).all()
        rows = session.execute(
            select(Prediction.user_id, Prediction.match_id, Prediction.points_awarded)
            .where(Prediction.match_id.in_(finished_ids))
        ).all() if finished_ids else []

    pts_by_user_match: dict[int, dict[int, int]] = {}
    for uid, mid, pts in rows:
        pts_by_user_match.setdefault(uid, {})[mid] = pts or 0

    result: list[dict] = []
    for u in users:
        user_pts = pts_by_user_match.get(u.id, {})
        streak = max_streak = streak_pts = max_streak_pts = 0
        for mid in finished_ids:
            pts = user_pts.get(mid, 0)
            if pts > 0:
                streak += 1
                streak_pts += pts
                if streak > max_streak:
                    max_streak = streak
                    max_streak_pts = streak_pts
            else:
                streak = 0
                streak_pts = 0
        result.append({
            "user_id": u.id,
            "display_name": u.display_name,
            "max_streak": max_streak,
            "max_streak_pts": max_streak_pts,
            "current_streak": streak,
            "current_streak_pts": streak_pts,
        })
    return result


# ---------------------------------------------------------------------------
# Positionsdauer: an wie vielen Spielen stand ein Nutzer (nach Tippstand zu
# diesem Zeitpunkt) auf Platz 1 bzw. auf dem letzten Platz
# ---------------------------------------------------------------------------

def compute_position_durations() -> list[dict]:
    """Zählt je Nutzer, nach wie vielen abgeschlossenen Spielen er (gemäß bis
    dahin gesammelten Tipp-Punkten, gleiche Tie-Breaker wie die Rangliste)
    auf Platz 1 bzw. auf dem letzten Platz lag. Bei Gleichstand zählt der
    Spieltag für alle gleichplatzierten Nutzer."""
    from models import Match

    with get_session() as session:
        users = session.scalars(select(User).where(User.is_spectator == False)).all()
        finished = session.scalars(
            select(Match).where(Match.is_finished.is_(True)).order_by(Match.kickoff_utc)
        ).all()
        finished_ids = [m.id for m in finished]
        rows = session.execute(
            select(Prediction.user_id, Prediction.match_id, Prediction.points_awarded,
                   Prediction.pred_home, Prediction.pred_away)
            .where(Prediction.match_id.in_(finished_ids))
        ).all() if finished_ids else []

    match_result = {m.id: (m.result_home, m.result_away) for m in finished}

    pred_by_match: dict[int, dict[int, tuple]] = {}
    for uid, mid, pts, ph, pa in rows:
        pred_by_match.setdefault(mid, {})[uid] = (pts or 0, ph, pa)

    def _sign(x: int) -> int:
        return 1 if x > 0 else (-1 if x < 0 else 0)

    user_ids = [u.id for u in users]
    cum_pts = {uid: 0 for uid in user_ids}
    cum_exact = {uid: 0 for uid in user_ids}
    cum_diff = {uid: 0 for uid in user_ids}
    cum_tend = {uid: 0 for uid in user_ids}
    top_count = {uid: 0 for uid in user_ids}
    bottom_count = {uid: 0 for uid in user_ids}

    for m in finished:
        rh, ra = match_result[m.id]
        preds = pred_by_match.get(m.id, {})
        for uid in user_ids:
            pts, ph, pa = preds.get(uid, (0, None, None))
            cum_pts[uid] += pts
            if ph is not None and pa is not None and rh is not None and ra is not None:
                if ph == rh and pa == ra:
                    cum_exact[uid] += 1
                elif (ph - pa) == (rh - ra):
                    cum_diff[uid] += 1
                elif _sign(ph - pa) == _sign(rh - ra):
                    cum_tend[uid] += 1

        keys = {uid: (cum_pts[uid], cum_exact[uid], cum_diff[uid], cum_tend[uid]) for uid in user_ids}
        best_key = max(keys.values())
        worst_key = min(keys.values())
        for uid in user_ids:
            if keys[uid] == best_key:
                top_count[uid] += 1
            if keys[uid] == worst_key:
                bottom_count[uid] += 1

    return [{
        "user_id": u.id,
        "display_name": u.display_name,
        "top_count": top_count[u.id],
        "bottom_count": bottom_count[u.id],
    } for u in users]
