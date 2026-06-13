"""
migrate_match5_date.py
======================
Korrigiert den Anstoßzeitpunkt von Match 5 (Australien vs Türkei):
  Falsch: 13.06.2026 04:00 CEST
  Richtig: 14.06.2026 06:00 CEST

Lokal:
    python migrate_match5_date.py

Produktion (Render):
    python migrate_match5_date.py "postgresql://..."
"""

import sys
import os
from datetime import datetime, timezone, timedelta

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import get_session
from models import Match
from sqlalchemy import select

CEST = timezone(timedelta(hours=2))
NEW_KICKOFF = datetime(2026, 6, 14, 4, 0, 0, tzinfo=timezone.utc)  # 06:00 CEST

with get_session() as s:
    m = s.scalars(select(Match).where(Match.match_number == 5)).first()
    if not m:
        print("FEHLER: Match 5 nicht gefunden.")
        sys.exit(1)

    ht = m.home_team.name if m.home_team else "?"
    at = m.away_team.name if m.away_team else "?"
    old = m.kickoff_utc.astimezone(CEST).strftime("%d.%m.%Y %H:%M")
    m.kickoff_utc = NEW_KICKOFF
    new = m.kickoff_utc.astimezone(CEST).strftime("%d.%m.%Y %H:%M")

    print(f"Match 5: {ht} vs {at}")
    print(f"  Vorher:  {old} CEST")
    print(f"  Nachher: {new} CEST")
    print("OK - Datum korrigiert.")
