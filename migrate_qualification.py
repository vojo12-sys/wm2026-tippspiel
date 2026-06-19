"""
migrate_qualification.py
=========================
Fügt manual_1st/manual_2nd (BOOLEAN DEFAULT false) zur group_results-Tabelle hinzu.

Lokal:      python migrate_qualification.py
Produktion: python migrate_qualification.py "postgresql://..."
"""
import sys, os

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine
from sqlalchemy import text, inspect

with engine.connect() as conn:
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("group_results")]
    dialect = engine.dialect.name
    default = "false" if dialect == "postgresql" else "0"

    for col in ("manual_1st", "manual_2nd"):
        if col not in cols:
            conn.execute(text(
                f"ALTER TABLE group_results ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT {default}"
            ))
            conn.commit()
            print(f"OK – Spalte {col} hinzugefügt.")
        else:
            print(f"Spalte {col} bereits vorhanden – nichts zu tun.")
