"""
database.py
===========
SQLAlchemy-Setup. Dieselbe Codebasis läuft auf:
  - SQLite  (lokal, keine Einrichtung)        sqlite:///wm2026.db
  - Postgres/Supabase (online, persistent)    postgresql+psycopg://...

Gesteuert allein über config.DATABASE_URL bzw. die Umgebungsvariable
DATABASE_URL. Es muss KEIN Code geändert werden, um zu wechseln.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Gemeinsame Basisklasse für alle ORM-Modelle."""
    pass


# Render liefert postgresql:// → auf psycopg3-Treiber umbiegen
_db_url = DATABASE_URL
if _db_url.startswith("postgresql://") or _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    _db_url = _db_url.replace("postgres://", "postgresql+psycopg://", 1)

# SQLite braucht ein Sonder-Argument für den Mehr-Thread-Betrieb.
_connect_args = {}
if _db_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    _db_url,
    echo=False,
    future=True,
    pool_pre_ping=True,      # erkennt abgelaufene Verbindungen (wichtig bei Supabase)
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def get_session():
    """
    Kontext-Manager für eine Datenbank-Session.

    Beispiel:
        with get_session() as s:
            s.add(obj)
            # commit/rollback wird automatisch gehandhabt
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Legt alle Tabellen an (idempotent – bestehende bleiben unangetastet)."""
    import models  # noqa: F401  (Modelle müssen registriert sein)
    Base.metadata.create_all(engine)
