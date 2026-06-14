"""
migrate_visits.py
=================
Erstellt:
  - Tabelle user_visits
  - Spalten last_seen + visit_count in users

Lokal:      python migrate_visits.py
Produktion: python migrate_visits.py "postgresql://..."
"""
import sys, os
if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine, Base
from models import UserVisit, User
from sqlalchemy import text, inspect

# Tabelle user_visits anlegen
Base.metadata.create_all(engine, tables=[UserVisit.__table__])
print("Tabelle user_visits: OK")

# Spalten last_seen + visit_count in users (falls nicht vorhanden)
db_url = os.environ.get("DATABASE_URL", "")
is_pg = "postgres" in db_url

with engine.connect() as conn:
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("users")]

    if "last_seen" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN last_seen TIMESTAMP WITH TIME ZONE" if is_pg else "ALTER TABLE users ADD COLUMN last_seen DATETIME"))
        print("Spalte last_seen: hinzugefügt")
    else:
        print("Spalte last_seen: bereits vorhanden")

    if "visit_count" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN visit_count INTEGER NOT NULL DEFAULT 0"))
        print("Spalte visit_count: hinzugefügt")
    else:
        print("Spalte visit_count: bereits vorhanden")

    conn.commit()

print("Fertig.")
