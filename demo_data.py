"""
demo_data.py
============
Simuliert die komplette WM 2026 (alle 104 Spiele) für Testzwecke.

Verwendung:
    python demo_data.py          # Komplette WM simulieren
    python demo_data.py 10       # Nur erste 10 Gruppenspiele
    python demo_data.py reset    # Alle Demo-Daten zurücksetzen
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone

from database import get_session
from models import GroupResult, Match, Prediction, Setting, Team, User
from scoring import recalculate_everything
from sqlalchemy import select


# ─────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────

def _random_score() -> tuple[int, int]:
    """Realistisches Fußballergebnis."""
    scores = [
        (0,0),(1,0),(0,1),(1,1),(2,0),(0,2),(2,1),(1,2),
        (2,2),(3,0),(0,3),(3,1),(1,3),(3,2),(2,3),(3,3),
        (4,0),(0,4),(4,1),(1,4),(4,2),(2,4),(5,0),(0,5),
    ]
    weights = [4,8,8,6,7,7,8,8,4,5,5,4,4,3,3,2,2,2,2,2,1,1,1,1]
    return random.choices(scores, weights=weights)[0]


def _ko_score() -> tuple[int, int]:
    """K.o.-Ergebnis: kein Unentschieden (nach Elfmeter immer ein Sieger)."""
    home, away = _random_score()
    while home == away:
        home, away = _random_score()
    return home, away


def _add_predictions(s, matches: list[Match], users: list[User]) -> None:
    """Legt zufällige Tipps für alle Nutzer an, falls noch keine vorhanden."""
    for m in matches:
        for u in users:
            existing = s.scalar(
                select(Prediction).where(
                    Prediction.user_id == u.id,
                    Prediction.match_id == m.id,
                )
            )
            if not existing:
                ph, pa = _random_score()
                s.add(Prediction(user_id=u.id, match_id=m.id,
                                 pred_home=ph, pred_away=pa))


def _calc_standings(matches: list[Match]) -> dict[str, list[dict]]:
    """Berechnet Gruppentabellen aus abgeschlossenen Spielen."""
    rows: dict[str, dict[int, dict]] = {}
    for m in matches:
        if not m.has_result or m.phase != "group":
            continue
        grp = m.group_letter or "?"
        for tid, gf, ga in [
            (m.home_team_id, m.result_home, m.result_away),
            (m.away_team_id, m.result_away, m.result_home),
        ]:
            if tid is None:
                continue
            rows.setdefault(grp, {}).setdefault(tid, {
                "team_id": tid, "sp": 0, "s": 0, "u": 0, "n": 0,
                "tore": 0, "gegen": 0,
            })
            r = rows[grp][tid]
            r["sp"] += 1; r["tore"] += gf; r["gegen"] += ga
            if gf > ga: r["s"] += 1
            elif gf == ga: r["u"] += 1
            else: r["n"] += 1

    result: dict[str, list[dict]] = {}
    for grp, tdict in rows.items():
        def key(r):
            pkt = r["s"] * 3 + r["u"]
            td  = r["tore"] - r["gegen"]
            return (-pkt, -td, -r["tore"])
        result[grp] = sorted(tdict.values(), key=key)
    return result


def _best_thirds(standings: dict[str, list[dict]]) -> list[dict]:
    """Gibt die 8 besten Drittplatzierten zurück, sortiert nach Punkten/TD."""
    thirds = []
    for grp, rows in standings.items():
        if len(rows) >= 3:
            r = rows[2]
            r["group"] = grp
            thirds.append(r)
    def key(r):
        pkt = r["s"] * 3 + r["u"]
        td  = r["tore"] - r["gegen"]
        return (-pkt, -td, -r["tore"])
    return sorted(thirds, key=key)[:8]


def _assign_thirds(best: list[dict]) -> dict[int, int]:
    """
    Weist die besten Drittplatzierten den K.o.-Slots zu.
    Jeder Slot akzeptiert nur Teams aus bestimmten Gruppen (laut WM-2026-Regeln).
    Gibt {match_number: team_id} zurück.
    """
    from data_schedule import KO_FIXTURES

    # Slots mit erlaubten Gruppen
    slots: list[tuple[int, list[str]]] = []
    for no, _, _, _, _, hc, ac in KO_FIXTURES:
        for code in (hc, ac):
            if code.startswith("3["):
                slots.append((no, list(code[2:-1])))

    assignment: dict[int, int] = {}
    used_slots: set[int] = set()

    # Greedy-Zuweisung: Besten Dritten zuerst, ersten passenden Slot nehmen
    for r in best:
        grp = r["group"]
        tid = r["team_id"]
        assigned = False
        # 1. Versuch: passender Slot für die Gruppe
        for slot_no, allowed in slots:
            if slot_no not in used_slots and grp in allowed:
                assignment[slot_no] = tid
                used_slots.add(slot_no)
                assigned = True
                break
        # 2. Fallback: irgendein freier Slot
        if not assigned:
            for slot_no, _ in slots:
                if slot_no not in used_slots:
                    assignment[slot_no] = tid
                    used_slots.add(slot_no)
                    break

    return assignment


def _set_kickoff_past(matches: list[Match]) -> None:
    """Markiert Spiele als gesperrt ohne echte Kickoff-Zeiten zu verändern."""
    pass  # Kickoff-Zeiten bleiben korrekt – is_finished=True reicht für Demo


# ─────────────────────────────────────────────────────────────────
# Haupt-Simulation
# ─────────────────────────────────────────────────────────────────

def simulate(n: int | None = None) -> None:
    """
    Simuliert die WM komplett (oder nur die ersten n Gruppenspiele).
    """
    with get_session() as s:
        users = list(s.scalars(select(User)).all())
        if not users:
            print("Keine Nutzer vorhanden.")
            return

        all_matches = list(s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all())
        for m in all_matches:
            _ = m.home_team, m.away_team

        group_matches = [m for m in all_matches if m.phase == "group"]
        ko_matches    = [m for m in all_matches if m.phase != "group"]

        if not group_matches:
            print("Keine Spiele in der DB. Bitte erst 'python import_schedule.py' ausführen.")
            return

        # ── Gruppenphase ──────────────────────────────────────────
        target = group_matches if n is None else group_matches[:n]
        print(f"Simuliere {len(target)} Gruppenspiele für {len(users)} Nutzer...")
        _set_kickoff_past(target)
        for m in target:
            if not m.is_finished:
                h, a = _random_score()
                m.result_home, m.result_away = h, a
                m.is_finished = True
                if h > a:   m.winner_team_id = m.home_team_id
                elif a > h: m.winner_team_id = m.away_team_id
                t1 = m.home_team.name if m.home_team else m.home_placeholder or "?"
                t2 = m.away_team.name if m.away_team else m.away_placeholder or "?"
                print(f"  {t1} {h}:{a} {t2}")
        _add_predictions(s, target, users)

        if n is not None:
            print(f"\nOK {len(target)} Gruppenspiele simuliert (Teil-Demo).")
            return

        # ── Tabellen berechnen ────────────────────────────────────
        standings = _calc_standings(all_matches)

        # ── GroupResult schreiben ─────────────────────────────────
        for grp, rows in standings.items():
            if len(rows) < 2:
                continue
            gr = s.get(GroupResult, grp)
            if not gr:
                gr = GroupResult(group_letter=grp)
                s.add(gr)
            gr.actual_1st  = rows[0]["team_id"]
            gr.actual_2nd  = rows[1]["team_id"]

        # ── Beste 8 Dritte >> K.o.-Slots ──────────────────────────
        best = _best_thirds(standings)
        thirds_map = _assign_thirds(best)
        if thirds_map:
            import json
            row = s.get(Setting, "ko_thirds")
            payload = json.dumps({str(k): v for k, v in thirds_map.items()})
            if row:
                row.value = payload
            else:
                s.add(Setting(key="ko_thirds", value=payload))
            print(f"\n  {len(thirds_map)} Drittplatzierte den K.o.-Slots zugewiesen.")

    # ── propagate() >> K.o.-Teams eintragen ───────────────────────
    from knockout import propagate
    filled = propagate()
    print(f"  {filled} K.o.-Team-Slots befüllt.")

    # ── K.o.-Phasen simulieren ────────────────────────────────────
    ko_phases = ["round32", "round16", "quarter", "semi", "third_place", "final"]
    phase_labels = {
        "round32": "Sechzehntelfinale (16 Spiele)",
        "round16": "Achtelfinale (8 Spiele)",
        "quarter": "Viertelfinale (4 Spiele)",
        "semi":    "Halbfinale (2 Spiele)",
        "third_place": "Spiel um Platz 3",
        "final":   "Finale",
    }

    for phase in ko_phases:
        with get_session() as s:
            phase_matches = list(s.scalars(
                select(Match)
                .where(Match.phase == phase)
                .order_by(Match.match_number)
            ).all())
            for m in phase_matches:
                _ = m.home_team, m.away_team

            ready = [m for m in phase_matches
                     if m.home_team_id and m.away_team_id and not m.is_finished]

            if not ready:
                print(f"  {phase_labels[phase]}: keine Spiele bereit.")
                continue

            print(f"\n{phase_labels[phase]}:")
            _set_kickoff_past(ready)
            for m in ready:
                h, a = _ko_score()
                m.result_home, m.result_away = h, a
                m.is_finished = True
                m.winner_team_id = m.home_team_id if h > a else m.away_team_id
                t1 = m.home_team.name if m.home_team else "?"
                t2 = m.away_team.name if m.away_team else "?"
                winner = t1 if h > a else t2
                print(f"  {t1} {h}:{a} {t2}  >> Sieger: {winner}")
            _add_predictions(s, ready, list(s.scalars(select(User)).all()))

        # Nach jeder Runde propagieren damit nächste Runde Teams hat
        filled = propagate()
        if filled:
            print(f"  >> {filled} weitere K.o.-Slots befüllt.")

    # ── TournamentResult setzen (Weltmeister + Gesamttore) ───────
    with get_session() as s:
        final_match = s.scalar(
            select(Match).where(Match.phase == "final", Match.is_finished == True)
        )
        if final_match:
            _ = final_match.home_team, final_match.away_team
            champion_id = final_match.winner_team_id
            # Gesamttore aller Gruppenspiele
            all_done = s.scalars(select(Match).where(Match.is_finished == True)).all()
            total_goals = sum(
                (m.result_home or 0) + (m.result_away or 0) for m in all_done
            )
            # Zufälliger Torschütze aus dem Siegerkader
            from data_squads import SQUADS
            from data_teams import GROUPS
            # flag code des Champions
            champ_flag = None
            if champion_id:
                champ_team = s.get(Team, champion_id)
                if champ_team:
                    from data_teams import GROUPS as G
                    for teams in G.values():
                        for name_de, name_en, code in teams:
                            if name_de == champ_team.name:
                                champ_flag = code
                                break
            top_scorer = None
            if champ_flag and champ_flag in SQUADS:
                strikers = [p["name"] for p in SQUADS[champ_flag] if p["pos"] == "ST"]
                if strikers:
                    top_scorer = random.choice(strikers)
            from models import TournamentResult
            tr = s.scalar(select(TournamentResult))
            if not tr:
                tr = TournamentResult(id=1)
                s.add(tr)
            tr.champion_team_id = champion_id
            tr.top_scorer = top_scorer
            tr.total_goals = total_goals
            champ_name = final_match.home_team.name if final_match.winner_team_id == final_match.home_team_id else final_match.away_team.name if final_match.away_team else "?"
            print(f"\nWeltmeister: {champ_name} | Torschuetze: {top_scorer} | Tore gesamt: {total_goals}")

    # ── Punkte neu berechnen ──────────────────────────────────────
    print("Berechne alle Punkte...")
    recalculate_everything()
    print("\nOK Komplette WM simuliert! Alle 104 Spiele, alle Phasen.")
    print("  >> Spielplan, Leaderboard, Tipp-Übersicht und Siegerurkunden sind befüllt.")
    print("  >> Zum Zurücksetzen: python demo_data.py reset")


# ─────────────────────────────────────────────────────────────────
# Reset
# ─────────────────────────────────────────────────────────────────

def reset() -> None:
    """Setzt alle Demo-Daten zurück."""
    with get_session() as s:
        # Ergebnisse löschen
        matches = list(s.scalars(select(Match).where(Match.is_finished == True)).all())
        for m in matches:
            m.result_home = m.result_away = None
            m.is_finished = False
            m.winner_team_id = None
            # K.o.-Teams zurücksetzen
            if m.phase != "group":
                m.home_team_id = None
                m.away_team_id = None

        # Alle Tipps löschen + Joker zurücksetzen
        for p in s.scalars(select(Prediction)).all():
            s.delete(p)
        from models import GroupPrediction, SpecialTip
        for gp in s.scalars(select(GroupPrediction)).all():
            s.delete(gp)
        for sp in s.scalars(select(SpecialTip)).all():
            s.delete(sp)
        for u in s.scalars(select(User)).all():
            u.joker_match_id = None

        # GroupResults löschen
        for gr in s.scalars(select(GroupResult)).all():
            s.delete(gr)

        # TournamentResult löschen
        from models import TournamentResult
        tr = s.scalar(select(TournamentResult))
        if tr:
            s.delete(tr)

        # ko_thirds löschen
        row = s.get(Setting, "ko_thirds")
        if row:
            s.delete(row)

    # K.o.-Platzhalter wiederherstellen
    from import_schedule import import_ko_placeholders
    try:
        import_ko_placeholders()
        print("K.o.-Platzhalter wiederhergestellt.")
    except Exception:
        print("Hinweis: K.o.-Platzhalter konnten nicht automatisch wiederhergestellt werden.")

    # Echte Kickoff-Zeiten wiederherstellen
    from datetime import timedelta
    from data_schedule import GROUP_FIXTURES, KO_FIXTURES, YEAR
    from import_schedule import _utc
    with get_session() as s:
        for no, group, home, away, city, d, t in GROUP_FIXTURES:
            m = s.scalar(select(Match).where(Match.match_number == no))
            if m:
                m.kickoff_utc = _utc(d, t)
                m.venue = city
        for no, phase, city, d, t, hc, ac in KO_FIXTURES:
            m = s.scalar(select(Match).where(Match.match_number == no))
            if m:
                m.kickoff_utc = _utc(d, t)
                m.venue = city
    print("Spielzeiten wiederhergestellt.")

    print(f"OK {len(matches)} Spiele zurückgesetzt, Punkte auf 0, GroupResults gelöscht.")


# ─────────────────────────────────────────────────────────────────
# Einstieg
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if arg == "reset":
        reset()
    elif arg == "all":
        simulate()
    else:
        try:
            simulate(int(arg))
        except ValueError:
            print(f"Ungültiges Argument: {arg}")
            print("Verwendung: python demo_data.py [all|anzahl|reset]")
            sys.exit(1)
