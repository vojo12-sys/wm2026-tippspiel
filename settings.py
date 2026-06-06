"""
settings.py
===========
Brücke zwischen den Standardwerten in config.py und der zur Laufzeit
änderbaren Konfiguration in der settings-Tabelle.

get_scoring() / get_pool() liefern immer die aktuell gültige Konfiguration:
Standard aus config.py, überschrieben durch das, was der Admin in der
Datenbank gespeichert hat.
"""

from __future__ import annotations

import json
from typing import Any

from config import DEFAULT_POOL, DEFAULT_RULES, DEFAULT_SCORING
from database import get_session
from models import Setting


def _read(key: str) -> Any | None:
    with get_session() as s:
        row = s.get(Setting, key)
        return json.loads(row.value) if row else None


def _write(key: str, value: Any) -> None:
    with get_session() as s:
        row = s.get(Setting, key)
        if row:
            row.value = json.dumps(value)
        else:
            s.add(Setting(key=key, value=json.dumps(value)))


def get_scoring() -> dict:
    """Aktuelles Punktesystem (Standard + Admin-Overrides)."""
    merged = dict(DEFAULT_SCORING)
    override = _read("scoring")
    if override:
        merged.update(override)
    return merged


def set_scoring(scoring: dict) -> None:
    _write("scoring", scoring)


def get_pool() -> dict:
    """Aktuelle Kassen-/Pool-Konfiguration (Standard + Admin-Overrides)."""
    merged = dict(DEFAULT_POOL)
    override = _read("pool")
    if override:
        merged.update(override)
    return merged


def set_pool(pool: dict) -> None:
    _write("pool", pool)


def get_rules() -> str:
    val = _read("rules")
    return val if isinstance(val, str) else DEFAULT_RULES


def set_rules(text: str) -> None:
    _write("rules", text)
