"""
api_sports.py
=============
Optionale Integration mit TheSportsDB für Spielerfotos.

Ohne API-Key: gibt None zurück, App läuft ohne Fotos.
Mit API-Key:  setzt SPORTSDB_API_KEY als Umgebungsvariable.
              Kostenloser Key: https://www.thesportsdb.com/api.php

Verwendung:
    from api_sports import get_player_photo
    url = get_player_photo("Erling Haaland")  # -> str | None
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
import json
import logging

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("SPORTSDB_API_KEY", "")
_BASE    = "https://www.thesportsdb.com/api/v1/json"

# Einfacher In-Memory-Cache: name -> (photo_url | None, timestamp)
_cache: dict[str, tuple[str | None, float]] = {}
_CACHE_TTL = 3600  # 1 Stunde


def _fetch(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wm2026-tippspiel/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("TheSportsDB-Anfrage fehlgeschlagen: %s", e)
        return None


def get_player_photo(name: str) -> str | None:
    """
    Gibt die Foto-URL eines Spielers zurück oder None.
    Ohne gesetzten API-Key immer None.
    """
    if not _API_KEY:
        return None

    now = time.time()
    if name in _cache:
        url, ts = _cache[name]
        if now - ts < _CACHE_TTL:
            return url

    encoded = urllib.parse.quote(name)
    data = _fetch(f"{_BASE}/{_API_KEY}/searchplayers.php?p={encoded}")

    photo = None
    if data and data.get("player"):
        player = data["player"][0]
        photo = player.get("strThumb") or player.get("strCutout") or None

    _cache[name] = (photo, now)
    return photo


def api_key_configured() -> bool:
    """True wenn ein API-Key gesetzt ist."""
    return bool(_API_KEY)
