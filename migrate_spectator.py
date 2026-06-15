"""Fügt is_spectator-Spalte zur user-Tabelle hinzu (einmalig)."""
import os
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS is_spectator BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.commit()
        print("OK: is_spectator Spalte hinzugefügt.")
    except Exception as e:
        print(f"Fehler: {e}")
