"""
Fügt penalty_home und penalty_away Spalten zur matches-Tabelle hinzu.
Lokal ausführen mit Render-DB-URL:
  $env:DATABASE_URL="postgresql://..."; python migrate_penalty_cols.py
"""
import os

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    import sqlite3
    con = sqlite3.connect("wm2026.db")
    cur = con.cursor()
    cur.execute("PRAGMA table_info(matches)")
    cols = [r[1] for r in cur.fetchall()]
    for col in ("penalty_home", "penalty_away"):
        if col not in cols:
            cur.execute(f"ALTER TABLE matches ADD COLUMN {col} INTEGER")
            print(f"SQLite: {col} hinzugefügt")
        else:
            print(f"SQLite: {col} bereits vorhanden")
    con.commit()
    con.close()
else:
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)
    with engine.connect() as con:
        for col in ("penalty_home", "penalty_away"):
            try:
                con.execute(text(f"ALTER TABLE matches ADD COLUMN {col} INTEGER"))
                con.commit()
                print(f"Postgres: {col} hinzugefügt")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Postgres: {col} bereits vorhanden")
                else:
                    raise
print("Migration abgeschlossen.")
