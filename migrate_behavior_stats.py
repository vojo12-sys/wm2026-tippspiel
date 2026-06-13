"""
migrate_behavior_stats.py
=========================
Fügt show_behavior_stats (BOOLEAN DEFAULT true) zur users-Tabelle hinzu.

Lokal:      python migrate_behavior_stats.py
Produktion: python migrate_behavior_stats.py "postgresql://..."
"""
import sys, os

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine
from sqlalchemy import text, inspect

with engine.connect() as conn:
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("users")]

    if "show_behavior_stats" not in cols:
        dialect = engine.dialect.name
        default = "true" if dialect == "postgresql" else "1"
        conn.execute(text(
            f"ALTER TABLE users ADD COLUMN show_behavior_stats BOOLEAN NOT NULL DEFAULT {default}"
        ))
        conn.commit()
        print("OK – Spalte show_behavior_stats hinzugefügt.")
    else:
        print("Spalte bereits vorhanden – nichts zu tun.")
