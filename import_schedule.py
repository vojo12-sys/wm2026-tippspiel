"""
import_schedule.py
===================
Spielt den offiziellen Spielplan (104 Spiele) in die Datenbank ein und
ersetzt dabei die vorläufigen Gruppenspiele.

  - Gruppenspiele: echte Paarungen, Städte, Anstoßzeiten (ET -> UTC)
  - K.-o.-Spiele:  Termine, Städte, Platzhalter (Sieger/Zweiter/Dritter/…)

ACHTUNG: Setzt die matches-Tabelle neu und löscht damit bestehende Tipps.
Vor Turnierstart gedacht. Aufruf (nach seed.py):

    python import_schedule.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from data_schedule import GROUP_FIXTURES, KO_FIXTURES, NAME_ALIASES, YEAR
from database import get_session, init_db
from knockout import placeholder_text
from models import GroupPrediction, Match, Prediction, Team

ET_OFFSET = timedelta(hours=4)  # EDT = UTC-4  ->  UTC = ET + 4h


def _utc(mm_dd: str, hhmm: str) -> datetime:
    mm, dd = (int(x) for x in mm_dd.split("-"))
    hh, mi = (int(x) for x in hhmm.split(":"))
    et = datetime(YEAR, mm, dd, hh, mi)          # ET-Wandzeit (naiv)
    return (et + ET_OFFSET).replace(tzinfo=timezone.utc)


def _team_index() -> dict[str, int]:
    with get_session() as s:
        return {t.name_en: t.id for t in s.scalars(select(Team)).all()}


def import_schedule() -> tuple[int, int]:
    init_db()
    idx = _team_index()

    def tid(name_en: str) -> int:
        return idx[NAME_ALIASES.get(name_en, name_en)]

    with get_session() as s:
        # Tipps + Spiele zurücksetzen (Neuaufbau vor Turnierstart)
        s.execute(delete(Prediction))
        # GroupPredictions werden NICHT gelöscht – sie bleiben auch nach Spielplan-Import gültig
        s.execute(delete(Match))

    grp = ko = 0
    with get_session() as s:
        for no, group, home, away, city, d, t in GROUP_FIXTURES:
            s.add(Match(
                match_number=no, phase="group", group_letter=group,
                home_team_id=tid(home), away_team_id=tid(away),
                kickoff_utc=_utc(d, t), venue=city,
            ))
            grp += 1

        for no, phase, city, d, t, hc, ac in KO_FIXTURES:
            s.add(Match(
                match_number=no, phase=phase, group_letter=None,
                home_team_id=None, away_team_id=None,
                home_placeholder=placeholder_text(hc),
                away_placeholder=placeholder_text(ac),
                kickoff_utc=_utc(d, t), venue=city,
            ))
            ko += 1
    return grp, ko


def import_ko_placeholders() -> int:
    """Setzt K.o.-Spiele auf leere Teams + Platzhaltertext zurück (für Demo-Reset)."""
    with get_session() as s:
        updated = 0
        for no, phase, city, d, t, hc, ac in KO_FIXTURES:
            m = s.scalar(select(Match).where(Match.match_number == no))
            if m:
                m.home_team_id = None
                m.away_team_id = None
                m.home_placeholder = placeholder_text(hc)
                m.away_placeholder = placeholder_text(ac)
                updated += 1
    return updated


def main() -> None:
    print("Importiere offiziellen Spielplan ...")
    grp, ko = import_schedule()
    print(f"  {grp} Gruppenspiele + {ko} K.-o.-Spiele = {grp + ko} Spiele angelegt.")
    print("Gruppen-Anstoßzeiten sind exakt (ET->UTC). K.-o.-Zeiten sind vorläufig.")


if __name__ == "__main__":
    main()
