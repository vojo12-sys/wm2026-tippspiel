from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from database import get_session
from models import Match, Team, TopScorer

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
_BASE = "https://api.football-data.org/v4"
_COMPETITION = "2000"  # FIFA World Cup 2026
_FINISHED_STATUSES = {"FINISHED"}
_LIVE_STATUSES = {"IN_PLAY", "PAUSED"}

# In-Memory-Cache für laufende Spiele:  match_id -> {home, away, minute, status}
_live_scores: dict[int, dict] = {}


def get_live_scores() -> dict[int, dict]:
    """Gibt den aktuellen Live-Score-Cache zurück."""
    return _live_scores

# ISO-3166 Ländercodes für Flaggen (Auswahl häufiger Nationen)
_NATIONALITY_FLAGS: dict[str, str] = {
    "Germany": "de", "France": "fr", "Brazil": "br", "Argentina": "ar",
    "Spain": "es", "England": "gb-eng", "Portugal": "pt", "Netherlands": "nl",
    "Belgium": "be", "Italy": "it", "Croatia": "hr", "Morocco": "ma",
    "Japan": "jp", "South Korea": "kr", "Mexico": "mx", "USA": "us",
    "Canada": "ca", "Uruguay": "uy", "Colombia": "co", "Ecuador": "ec",
    "Switzerland": "ch", "Austria": "at", "Sweden": "se", "Denmark": "dk",
    "Norway": "no", "Poland": "pl", "Serbia": "rs", "Ukraine": "ua",
    "Senegal": "sn", "Nigeria": "ng", "Ivory Coast": "ci", "Ghana": "gh",
    "Cameroon": "cm", "Egypt": "eg", "Tunisia": "tn", "Algeria": "dz",
    "Saudi Arabia": "sa", "Iran": "ir", "Qatar": "qa", "Australia": "au",
    "New Zealand": "nz", "South Africa": "za", "Turkey": "tr",
    "Czech Republic": "cz", "Scotland": "gb-sct", "Bosnia and Herzegovina": "ba",
    "Uzbekistan": "uz", "Iraq": "iq", "Jordan": "jo", "Paraguay": "py",
    "Bolivia": "bo", "Chile": "cl", "Peru": "pe", "Venezuela": "ve",
    "Panama": "pa", "Costa Rica": "cr", "Haiti": "ht", "Jamaica": "jm",
    "DR Congo": "cd", "Cabo Verde": "cv", "Cape Verde": "cv",
}


def _flag_for_nationality(nationality: str | None) -> str | None:
    if not nationality:
        return None
    return _NATIONALITY_FLAGS.get(nationality)


def sync_results() -> int:
    """Holt abgeschlossene WM-Spiele und aktualisiert die DB."""
    if not _API_KEY:
        logger.warning("FOOTBALL_API_KEY nicht gesetzt – sync übersprungen")
        return 0

    updated = _sync_matches()
    _sync_scorers()
    return updated


def _sync_matches() -> int:
    try:
        resp = httpx.get(
            f"{_BASE}/competitions/{_COMPETITION}/matches",
            headers={"X-Auth-Token": _API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("football-data.org Matches-Fehler: %s", e)
        return 0

    matches_data = resp.json().get("matches", [])
    updated = 0
    new_live: dict[int, dict] = {}
    finished_ids: set[int] = set()

    with get_session() as s:
        team_by_name: dict[str, int] = {
            t.name_en: t.id for t in s.scalars(select(Team)).all()
        }

        for fd in matches_data:
            status = fd.get("status", "")
            if status not in _FINISHED_STATUSES and status not in _LIVE_STATUSES:
                continue

            score = fd.get("score", {})
            # Für laufende Spiele: currentScore, für abgeschlossene: fullTime
            if status in _LIVE_STATUSES:
                current = score.get("halfTime") if status == "PAUSED" else score.get("fullTime") or {}
                # football-data liefert laufende Tore unter fullTime sobald IN_PLAY
                live_score = score.get("fullTime", {})
                home_goals = live_score.get("home")
                away_goals = live_score.get("away")
            else:
                full = score.get("fullTime", {})
                home_goals = full.get("home")
                away_goals = full.get("away")

            if home_goals is None or away_goals is None:
                continue

            kickoff_str = fd.get("utcDate", "")
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            m = s.scalar(
                select(Match).where(Match.kickoff_utc == kickoff, Match.is_finished == False)
            )
            if m is None:
                home_name = fd.get("homeTeam", {}).get("name", "")
                away_name = fd.get("awayTeam", {}).get("name", "")
                home_id = team_by_name.get(home_name)
                away_id = team_by_name.get(away_name)
                if home_id and away_id:
                    m = s.scalar(
                        select(Match).where(
                            Match.home_team_id == home_id,
                            Match.away_team_id == away_id,
                            Match.is_finished == False,
                        )
                    )
            if m is None:
                continue

            if status in _LIVE_STATUSES:
                # Nur Live-Cache updaten, kein DB-Commit, keine Punkte
                minute = fd.get("minute")
                new_live[m.id] = {
                    "home": home_goals,
                    "away": away_goals,
                    "minute": minute,
                    "status": status,  # IN_PLAY oder PAUSED
                    "ts": time.time(),
                }
                logger.info("LIVE Sp.%s: %d:%d (%s')", m.match_number, home_goals, away_goals, minute)
            else:
                # Abgeschlossen: in DB schreiben
                finished_ids.add(m.id)
                duration = score.get("duration", "REGULAR")
                penalties = score.get("penalties") or {}
                pen_home = penalties.get("home")
                pen_away = penalties.get("away")
                extra = score.get("extraTime") or {}
                extra_home = extra.get("home")
                extra_away = extra.get("away")
                half = score.get("halfTime") or {}
                ht_h = half.get("home")
                ht_a = half.get("away")
                if ht_h is not None and ht_a is not None:
                    m.ht_home = ht_h
                    m.ht_away = ht_a
                if duration == "PENALTY_SHOOTOUT" or (pen_home is not None and pen_away is not None):
                    # Elfmeterschießen: ET-Score als offizielles Ergebnis (FIFA-Regel: Elfmeter zählen nicht)
                    if extra_home is not None and extra_away is not None:
                        m.result_home = extra_home
                        m.result_away = extra_away
                    else:
                        m.result_home = home_goals
                        m.result_away = away_goals
                    m.went_to_penalties = True
                    m.went_to_extra_time = True
                elif duration == "EXTRA_TIME" or (extra_home is not None and extra_away is not None):
                    # Verlängerung ohne Elfmeter
                    m.result_home = extra_home if extra_home is not None else home_goals
                    m.result_away = extra_away if extra_away is not None else away_goals
                    m.went_to_penalties = False
                    m.went_to_extra_time = True
                else:
                    m.result_home = home_goals
                    m.result_away = away_goals
                    m.went_to_penalties = False
                    m.went_to_extra_time = False
                m.is_finished = True
                winner = score.get("winner")
                if winner == "HOME_TEAM":
                    m.winner_team_id = m.home_team_id
                elif winner == "AWAY_TEAM":
                    m.winner_team_id = m.away_team_id
                # Aus Live-Cache entfernen
                new_live.pop(m.id, None)
                updated += 1
                logger.info("Spiel %s: %d:%d%s", m.match_number, m.result_home, m.result_away,
                            " n.E." if m.went_to_penalties else "")

    # Live-Cache aktualisieren:
    # - Abgeschlossene Spiele (jetzt in DB) gezielt entfernen
    # - Spiele, die die API in diesem Zyklus nicht gemeldet hat, behalten
    #   (kurze API-Lücke → letzter bekannter Stand bleibt sichtbar)
    # - Einträge älter als 120 min bereinigen (Spiel ist definitiv vorbei)
    now = time.time()
    for mid in finished_ids:
        _live_scores.pop(mid, None)
    for mid in list(_live_scores):
        if mid not in new_live:
            age_min = (now - _live_scores[mid].get("ts", now)) / 60
            if age_min > 120:
                del _live_scores[mid]
    _live_scores.update(new_live)

    if updated > 0:
        try:
            from qualification import update_qualifications
            from scoring import recalculate_everything, update_total_goals
            from standings import save_all_rank_snapshots
            save_all_rank_snapshots()
            update_qualifications()
            recalculate_everything()
            update_total_goals()
        except Exception as e:
            logger.error("Punkte-Neuberechnung: %s", e)

    return updated


def _sync_scorers() -> None:
    """Holt die aktuelle Torschützenliste von football-data.org."""
    try:
        resp = httpx.get(
            f"{_BASE}/competitions/{_COMPETITION}/scorers?limit=50",
            headers={"X-Auth-Token": _API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("football-data.org Scorers-Fehler: %s", e)
        return

    scorers_data = resp.json().get("scorers", [])
    if not scorers_data:
        return

    with get_session() as s:
        # Alle vorhandenen Einträge löschen und neu aufbauen
        existing = s.scalars(select(TopScorer)).all()
        for e in existing:
            s.delete(e)

        for rank, entry in enumerate(scorers_data, 1):
            player = entry.get("player", {})
            team = entry.get("team", {})
            nationality = player.get("nationality")
            team_name = team.get("name", "")

            # Team-Flagge aus unserer DB suchen
            team_flag = None
            if team_name:
                db_team = s.scalar(select(Team).where(Team.name_en == team_name))
                if db_team:
                    team_flag = db_team.flag_code

            s.add(TopScorer(
                player_name=player.get("name", "Unbekannt"),
                nationality=nationality,
                flag_code=_flag_for_nationality(nationality),
                team_name=team_name,
                team_flag_code=team_flag,
                goals=entry.get("goals") or 0,
                assists=entry.get("assists") or 0,
                penalties=entry.get("penalties") or 0,
                matches_played=entry.get("playedMatches") or 0,
                rank=rank,
            ))

    logger.info("Torschützenliste aktualisiert: %d Einträge", len(scorers_data))
