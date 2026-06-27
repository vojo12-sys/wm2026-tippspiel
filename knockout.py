"""
knockout.py
===========
Logik für die K.-o.-Phase (Variante A: Paarungen schalten sich frei, sobald
sie feststehen).

Zubringer werden aufgelöst aus:
  - Gruppensieger / -zweite      -> Tabelle group_results (vom Admin gepflegt)
  - beste acht Dritte            -> Setting "ko_thirds"
                                    {Spiel-Nr: {"team_id": int, "manual": bool}}
                                    (vom Admin je 3[...]-Slot zugewiesen)
  - Sieger/Verlierer Vorspiele   -> aus den Spielergebnissen (winner_team_id)

propagate() trägt in jedes K.-o.-Spiel die bekannten Teams ein und schaltet es
damit zum Tippen frei. Idempotent – nach jedem Ergebnis erneut aufrufbar.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select

from data_schedule import KO_FIXTURES
from database import get_session
from models import GroupResult, Match, Setting

# Spiel-Nr -> (heim_code, gast_code)
_FEEDERS = {no: (hc, ac) for no, _, _, _, _, hc, ac in KO_FIXTURES}


def placeholder_text(code: str) -> str:
    """Menschlich lesbarer Platzhalter für ein noch unbekanntes Team."""
    if re.fullmatch(r"1[A-L]", code):
        return f"Sieger Gruppe {code[1]}"
    if re.fullmatch(r"2[A-L]", code):
        return f"2. Gruppe {code[1]}"
    if code.startswith("3["):
        letters = "/".join(code[2:-1])
        return f"3. ({letters})"
    if code.startswith("W"):
        return f"Sieger Spiel {code[1:]}"
    if code.startswith("L"):
        return f"Verlierer Spiel {code[1:]}"
    return code


def get_thirds_state() -> dict[int, dict]:
    """Aktueller Zustand der Dritt-Platz-Slots:
    {Spiel-Nr: {"team_id": int, "manual": bool}}."""
    with get_session() as s:
        row = s.get(Setting, "ko_thirds")
        if not row:
            return {}
        return {int(k): v for k, v in json.loads(row.value).items()}


def set_third_slot(match_no: int, team_id: int | None, manual: bool) -> None:
    """Setzt (oder löscht, bei team_id=None) die Zuordnung für einen
    Dritt-Platz-Slot. manual=True markiert eine Admin-Überschreibung, die
    die automatische Berechnung nicht mehr anfasst."""
    with get_session() as s:
        row = s.get(Setting, "ko_thirds")
        state = json.loads(row.value) if row else {}
        if team_id is None:
            state.pop(str(match_no), None)
        else:
            state[str(match_no)] = {"team_id": team_id, "manual": manual}
        payload = json.dumps(state)
        if row:
            row.value = payload
        else:
            s.add(Setting(key="ko_thirds", value=payload))


def _thirds_assignment() -> dict[int, int]:
    """Spiel-Nr -> team_id, für propagate()."""
    return {no: v["team_id"] for no, v in get_thirds_state().items()}


def _loser_team_id(m: Match) -> int | None:
    if not (m and m.winner_team_id and m.home_team_id and m.away_team_id):
        return None
    return m.away_team_id if m.winner_team_id == m.home_team_id else m.home_team_id


def _resolve(code, *, first, second, thirds, match_no, by_no) -> int | None:
    """Gibt die team_id zu einem Zubringer-Code zurück oder None (noch offen)."""
    if re.fullmatch(r"1[A-L]", code):
        return first.get(code[1])
    if re.fullmatch(r"2[A-L]", code):
        return second.get(code[1])
    if code.startswith("3["):
        return thirds.get(match_no)
    if code.startswith("W"):
        m = by_no.get(int(code[1:]))
        return m.winner_team_id if m else None
    if code.startswith("L"):
        return _loser_team_id(by_no.get(int(code[1:])))
    return None


def propagate() -> int:
    """Trägt alle aktuell bestimmbaren Teams in die K.-o.-Spiele ein.
    Korrigiert auch falsch gesetzte Werte in noch nicht gespielten Matches.
    Gibt die Zahl neu gesetzter/korrigierter Team-Slots zurück."""
    thirds = _thirds_assignment()
    filled = 0
    with get_session() as s:
        results = {gr.group_letter: gr for gr in s.scalars(select(GroupResult)).all()}
        first = {g: r.actual_1st for g, r in results.items() if r.actual_1st}
        second = {g: r.actual_2nd for g, r in results.items() if r.actual_2nd}

        ko_matches = s.scalars(select(Match).where(Match.phase != "group")).all()
        by_no = {m.match_number: m for m in ko_matches}

        # Mehrere Durchläufe, damit sich Runden nacheinander auflösen können
        for _ in range(6):
            changed = False
            for m in ko_matches:
                hc, ac = _FEEDERS[m.match_number]
                for attr, code in (("home_team_id", hc), ("away_team_id", ac)):
                    current = getattr(m, attr)
                    tid = _resolve(code, first=first, second=second, thirds=thirds,
                                   match_no=m.match_number, by_no=by_no)
                    if tid is None:
                        continue
                    if current is None:
                        setattr(m, attr, tid); filled += 1; changed = True
                    elif current != tid and not m.is_finished:
                        # Falsch gesetzter Wert in noch nicht gespieltem Match korrigieren
                        setattr(m, attr, tid); filled += 1; changed = True
            if not changed:
                break
    return filled


def third_place_slots() -> list[tuple[int, list[str]]]:
    """Liste der K.-o.-Spiele mit Dritt-Platz-Slot: (Spiel-Nr, [erlaubte Gruppen])."""
    out = []
    for no, _, _, _, _, hc, ac in KO_FIXTURES:
        for code in (hc, ac):
            if code.startswith("3["):
                out.append((no, list(code[2:-1])))
    return out
