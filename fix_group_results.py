"""
fix_group_results.py
====================
Korrigiert Gruppen-Ergebnisse (lokal SQLite oder Render PostgreSQL via DATABASE_URL):
  1. Spiele #1-24 (Demo-Daten → echte API-Ergebnisse)
  2. Spiel #35 (Curaçao vs Ecuador 0:0, war nicht in API wegen vertauschter Teams)
  3. Spiele #51-66 (fertig laut API, noch nicht in DB)
  4. Spiel #49 (Schweiz vs Kanada 3:1) bleibt als manuelle Korrektur erhalten

Verwendung lokal:     python fix_group_results.py
Verwendung auf Render: $env:DATABASE_URL="<external-url>"; python fix_group_results.py
"""
from __future__ import annotations

import os
import ssl
import json
import urllib.request
import sys

sys.stdout.reconfigure(encoding="utf-8")

# .env nur lokal laden (Render hat Env-Vars direkt)
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()

API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
if not API_KEY:
    print("FEHLER: FOOTBALL_API_KEY nicht gesetzt")
    sys.exit(1)

# Ungültige DATABASE_URL-Platzhalter abfangen (z. B. "<external-url>")
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url and (_db_url.startswith("<") or not any(_db_url.startswith(p) for p in ("sqlite", "postgresql", "postgres"))):
    print(f"WARNUNG: DATABASE_URL sieht ungültig aus: {_db_url!r}")
    print("         Bitte echte Render-URL angeben oder Variable weglassen (dann SQLite).")
    sys.exit(1)

ctx = ssl._create_unverified_context()


def api_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        return json.loads(resp.read())


# ── API-Daten holen ────────────────────────────────────────────────────────────
print("Lade fertige Gruppenspiele von football-data.org …")
data = api_get("https://api.football-data.org/v4/competitions/WC/matches?stage=GROUP_STAGE&status=FINISHED")
api_matches = data.get("matches", [])
print(f"  {len(api_matches)} fertige Spiele empfangen")

# ── SQLAlchemy-Session ────────────────────────────────────────────────────────
from sqlalchemy import select
from database import get_session
from models import Match, Team

# Manuell nicht überschreiben
MATCH_49_NUM = 49
# Manuell setzen (API hat Heimteams vertauscht)
MATCH_35_NUM = 35

# API short name → name_en in der DB
API_NAME_ALIAS: dict[str, str] = {
    "Bosnia-H.": "Bosnia and Herzegovina",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Korea Republic": "South Korea",
    "Cabo Verde": "Cape Verde",
    "USA": "United States",
    "Turkey": "Türkiye",
    "Congo DR": "DR Congo",
}


def resolve_team_id(api_name: str, team_by_name_en: dict[str, int]) -> int | None:
    name = API_NAME_ALIAS.get(api_name, api_name)
    return team_by_name_en.get(name)


with get_session() as s:
    # Teams-Mapping aufbauen
    team_by_name_en: dict[str, int] = {t.name_en: t.id for t in s.scalars(select(Team)).all()}

    # Alle Gruppen-Matches laden
    db_matches_list = s.scalars(select(Match).where(Match.phase == "group")).all()
    db_by_teams: dict[tuple[int, int], Match] = {
        (m.home_team_id, m.away_team_id): m for m in db_matches_list
    }
    db_by_num: dict[int, Match] = {m.match_number: m for m in db_matches_list}

    m49 = db_by_num.get(MATCH_49_NUM)
    if m49:
        print(f"\nSpiel #49 (Schweiz vs Kanada): DB {m49.result_home}:{m49.result_away} bleibt (manuelle Korrektur)")

    updated = 0
    changes: list[str] = []

    for api_m in api_matches:
        home_api = api_m["homeTeam"].get("shortName") or api_m["homeTeam"].get("name", "")
        away_api = api_m["awayTeam"].get("shortName") or api_m["awayTeam"].get("name", "")
        home_id = resolve_team_id(home_api, team_by_name_en)
        away_id = resolve_team_id(away_api, team_by_name_en)

        score = api_m.get("score", {})
        ft = score.get("fullTime", {})
        ht = score.get("halfTime", {})
        penalties = score.get("penalties") or {}
        extra = score.get("extraTime") or {}
        duration = score.get("duration", "REGULAR")
        winner_code = score.get("winner")

        home_goals = ft.get("home")
        away_goals = ft.get("away")
        if home_goals is None or away_goals is None:
            continue

        pen_home = penalties.get("home")
        pen_away = penalties.get("away")
        extra_home = extra.get("home")
        extra_away = extra.get("away")

        if duration == "PENALTY_SHOOTOUT" or (pen_home is not None and pen_away is not None):
            result_h = extra_home if extra_home is not None else home_goals
            result_a = extra_away if extra_away is not None else away_goals
            went_penalties = True
            went_extra = True
        elif duration == "EXTRA_TIME" or (extra_home is not None and extra_away is not None):
            result_h = extra_home if extra_home is not None else home_goals
            result_a = extra_away if extra_away is not None else away_goals
            went_penalties = False
            went_extra = True
        else:
            result_h = home_goals
            result_a = away_goals
            went_penalties = False
            went_extra = False

        ht_h = ht.get("home")
        ht_a = ht.get("away")

        # DB-Match suchen (normal)
        db_m = db_by_teams.get((home_id, away_id)) if home_id and away_id else None

        # Fallback: Heimteams vertauscht (wie bei Match #35)
        if db_m is None and home_id and away_id:
            db_m = db_by_teams.get((away_id, home_id))
            if db_m is not None:
                result_h, result_a = result_a, result_h
                if winner_code == "HOME_TEAM":
                    winner_code = "AWAY_TEAM"
                elif winner_code == "AWAY_TEAM":
                    winner_code = "HOME_TEAM"

        if db_m is None:
            continue

        # Match #49 nicht überschreiben
        if db_m.match_number == MATCH_49_NUM:
            continue

        # Schon korrekt?
        if db_m.is_finished and db_m.result_home == result_h and db_m.result_away == result_a:
            continue

        if winner_code == "HOME_TEAM":
            winner_team_id = db_m.home_team_id
        elif winner_code == "AWAY_TEAM":
            winner_team_id = db_m.away_team_id
        else:
            winner_team_id = None

        old = f"{db_m.result_home}:{db_m.result_away}" if db_m.is_finished else "ausstehend"
        new = f"{result_h}:{result_a}"

        db_m.result_home = result_h
        db_m.result_away = result_a
        db_m.went_to_penalties = went_penalties
        db_m.went_to_extra_time = went_extra
        db_m.winner_team_id = winner_team_id
        db_m.is_finished = True
        if ht_h is not None and ht_a is not None:
            db_m.ht_home = ht_h
            db_m.ht_away = ht_a

        changes.append(f"  #{db_m.match_number:3d} {old:12s} → {new}")
        updated += 1

    # Match #35 direkt setzen falls noch offen
    m35 = db_by_num.get(MATCH_35_NUM)
    if m35 and not m35.is_finished:
        m35.result_home = 0
        m35.result_away = 0
        m35.went_to_penalties = False
        m35.went_to_extra_time = False
        m35.winner_team_id = None
        m35.is_finished = True
        changes.append(f"  #{MATCH_35_NUM:3d} ausstehend   → 0:0  (Curaçao vs Ecuador, manuell)")
        updated += 1

print(f"\n{len(changes)} Ergebnisse aktualisiert:")
for c in changes:
    print(c)
if not changes:
    print("  Keine Änderungen notwendig.")

# ── Punkte neu berechnen ──────────────────────────────────────────────────────
print("\nBerechne Punkte neu …")
from scoring import recalculate_everything, update_total_goals
from standings import save_all_rank_snapshots
save_all_rank_snapshots()
recalculate_everything()
update_total_goals()
print("Punkte-Neuberechnung abgeschlossen.")

try:
    from qualification import update_qualifications
    update_qualifications()
    print("Qualifikationen aktualisiert.")
except Exception as e:
    print(f"qualification: {e}")

print("\nFertig!")
