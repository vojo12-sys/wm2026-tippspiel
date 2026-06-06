from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE
from database import get_session
from deps import require_user, templates
from models import Match, Team

router = APIRouter()

_KO_ORDER = ["round32", "round16", "quarter", "semi", "third_place", "final"]
_KO_LABELS = {
    "round32": "Sechzehntelfinale", "round16": "Achtelfinale",
    "quarter": "Viertelfinale", "semi": "Halbfinale",
    "third_place": "Spiel um Platz 3", "final": "Finale",
}


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m. %H:%M")


def _group_tables(matches: list[Match], live: dict | None = None) -> dict[str, list[dict]]:
    """Berechnet die aktuelle Gruppentabelle aus den Spielergebnissen.
    Alle 12 Gruppen werden angezeigt, auch ohne Ergebnisse."""
    from dataclasses import dataclass
    from data_teams import GROUPS

    @dataclass
    class Row:
        team_id: int
        name: str
        flag: str
        sp: int = 0
        s: int = 0
        u: int = 0
        n: int = 0
        tore: int = 0
        gegen: int = 0
        @property
        def td(self): return self.tore - self.gegen
        @property
        def pkt(self): return self.s * 3 + self.u

    # Alle Gruppen mit allen Teams vorbelegen (0 Punkte)
    tables: dict[str, dict[str, Row]] = {}
    for letter, teams in GROUPS.items():
        tables[letter] = {}
        for name_de, _name_en, flag_code in teams:
            tables[letter][name_de] = Row(team_id=0, name=name_de, flag=flag_code)

    # Ergebnisse eintragen (DB-Ergebnisse + Live-Cache)
    live = live or {}
    for m in matches:
        if m.phase != "group":
            continue
        if not m.home_team_id or not m.away_team_id:
            continue

        # Abgeschlossenes Spiel aus DB oder laufendes aus Live-Cache
        if m.has_result:
            home_goals, away_goals = m.result_home, m.result_away
        elif m.id in live:
            home_goals = live[m.id]["home"]
            away_goals = live[m.id]["away"]
        else:
            continue

        grp = m.group_letter or "?"
        if grp not in tables:
            tables[grp] = {}

        for team, goals_for, goals_against in [
            (m.home_team, home_goals, away_goals),
            (m.away_team, away_goals, home_goals),
        ]:
            if team is None:
                continue
            key = team.name
            if key not in tables[grp]:
                tables[grp][key] = Row(
                    team_id=team.id,
                    name=team.name,
                    flag=team.flag_code or "",
                )
            r = tables[grp][key]
            r.sp += 1
            r.tore += goals_for
            r.gegen += goals_against
            if goals_for > goals_against:
                r.s += 1
            elif goals_for == goals_against:
                r.u += 1
            else:
                r.n += 1

    # Sortieren: Punkte → Tordifferenz → Tore
    result: dict[str, list[dict]] = {}
    for grp, rows in sorted(tables.items()):
        sorted_rows = sorted(
            rows.values(),
            key=lambda r: (-r.pkt, -r.td, -r.tore, r.name)
        )
        result[grp] = [
            {
                "pos": i + 1, "name": r.name, "flag": r.flag,
                "sp": r.sp, "s": r.s, "u": r.u, "n": r.n,
                "tore": r.tore, "gegen": r.gegen,
                "td": r.td, "pkt": r.pkt,
            }
            for i, r in enumerate(sorted_rows)
        ]
    return result


@router.get("/spielplan")
async def spielplan_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    with get_session() as s:
        matches = s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all()
        for m in matches:
            _ = m.home_team, m.away_team
        matches = list(matches)

    group_matches: dict[str, list[Match]] = {}
    ko_matches: dict[str, list[Match]] = {}
    for m in matches:
        if m.phase == "group":
            group_matches.setdefault(m.group_letter or "?", []).append(m)
        else:
            ko_matches.setdefault(m.phase, []).append(m)

    try:
        from results_sync import get_live_scores
        live_scores = get_live_scores()
    except Exception:
        live_scores = {}
    group_tables = _group_tables(matches, live_scores)

    return templates.TemplateResponse(request, "spielplan.html", {
        "user": user, "active": "spielplan",
        "group_matches": group_matches,
        "ko_matches": ko_matches,
        "ko_order": _KO_ORDER,
        "ko_labels": _KO_LABELS,
        "group_tables": group_tables,
        "fmt": _fmt,
        "flash": request.session.pop("flash", None),
    })
