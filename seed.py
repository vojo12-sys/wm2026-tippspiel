"""
seed.py
=======
Initialisiert die Datenbank: legt alle Tabellen an und befüllt die
Stammdaten (48 Teams, leere Ergebnis-Zeilen für Gruppen und Turnier).

Aufruf:
    python seed.py

Idempotent: bereits vorhandene Teams werden nicht doppelt angelegt.
Der eigentliche Spielplan (104 Spiele mit Anstoßzeiten) wird im nächsten
Schritt über ein separates Import-Skript eingespielt (data_fixtures).
"""

from __future__ import annotations

from sqlalchemy import select

from database import get_session, init_db
from data_teams import GROUPS, all_teams
from models import GroupResult, Team, TournamentResult


def seed_teams() -> int:
    added = 0
    with get_session() as s:
        existing = {t.name for t in s.scalars(select(Team)).all()}
        for name_de, name_en, code, letter in all_teams():
            if name_de in existing:
                continue
            s.add(Team(name=name_de, name_en=name_en, flag_code=code, group_letter=letter))
            added += 1
    return added


def seed_result_rows() -> None:
    """Legt leere Ergebnis-Zeilen an, die der Admin später befüllt."""
    with get_session() as s:
        existing_groups = {gr.group_letter for gr in s.scalars(select(GroupResult)).all()}
        for letter in GROUPS:
            if letter not in existing_groups:
                s.add(GroupResult(group_letter=letter))
        if s.get(TournamentResult, 1) is None:
            s.add(TournamentResult(id=1))


def main() -> None:
    print("Lege Tabellen an ...")
    init_db()
    print("Befülle Teams ...")
    n = seed_teams()
    print(f"  {n} Teams neu angelegt.")
    print("Initialisiere Ergebnis-Zeilen ...")
    seed_result_rows()
    print("Fertig. Datenbank ist einsatzbereit.")


if __name__ == "__main__":
    main()
