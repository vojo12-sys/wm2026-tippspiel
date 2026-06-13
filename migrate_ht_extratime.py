"""
migrate_ht_extratime.py
=======================
Fügt drei neue Spalten zur matches-Tabelle hinzu:
  - went_to_extra_time  BOOLEAN DEFAULT 0
  - ht_home             INTEGER NULL
  - ht_away             INTEGER NULL

Lokal (SQLite):
    python migrate_ht_extratime.py

Produktion (Render):
    python migrate_ht_extratime.py "postgresql://..."
"""
import sys, os

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine

with engine.connect() as conn:
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("matches")]

    added = []
    if "went_to_extra_time" not in cols:
        conn.execute(text("ALTER TABLE matches ADD COLUMN went_to_extra_time BOOLEAN NOT NULL DEFAULT false"))
        added.append("went_to_extra_time")
    if "ht_home" not in cols:
        conn.execute(text("ALTER TABLE matches ADD COLUMN ht_home INTEGER"))
        added.append("ht_home")
    if "ht_away" not in cols:
        conn.execute(text("ALTER TABLE matches ADD COLUMN ht_away INTEGER"))
        added.append("ht_away")

    conn.commit()

if added:
    print(f"OK - Spalten hinzugefuegt: {', '.join(added)}")
else:
    print("Spalten bereits vorhanden - nichts zu tun.")
