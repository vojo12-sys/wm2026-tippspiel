from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from config import DISPLAY_TIMEZONE, PHASES, TOTAL_MATCHES
from database import get_session
from deps import require_user, templates
from datetime import timezone
from models import Match, Prediction, User

router = APIRouter()


_DAYS_DE = {"Mon": "Mo", "Tue": "Di", "Wed": "Mi", "Thu": "Do", "Fri": "Fr", "Sat": "Sa", "Sun": "So"}

def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(DISPLAY_TIMEZONE)
    day = _DAYS_DE.get(local.strftime("%a"), local.strftime("%a"))
    return f"{day} {local.strftime('%d.%m. · %H:%M')}"


def _spieltag(match_number: int) -> int:
    """Gruppenphase: Matches 1-24 = ST1, 25-48 = ST2, 49-72 = ST3."""
    if match_number <= 24:
        return 1
    if match_number <= 48:
        return 2
    return 3


def _load_matches() -> dict[str, list[Match]]:
    with get_session() as s:
        rows = s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all()
        for m in rows:
            _ = m.home_team, m.away_team
        by_phase: dict[str, list[Match]] = {}
        for m in rows:
            by_phase.setdefault(m.phase, []).append(m)
        return by_phase


def _active_spieltag(group_matches: list[Match]) -> int:
    """Spieltag mit dem nächsten noch nicht gesperrten Spiel; fallback: 3."""
    now = datetime.now(timezone.utc)
    for m in sorted(group_matches, key=lambda x: (x.kickoff_utc or datetime.min.replace(tzinfo=timezone.utc), x.match_number)):
        if not m.is_locked:
            return _spieltag(m.match_number)
    return 3


def _load_predictions(user_id: int) -> dict[int, tuple[int, int]]:
    with get_session() as s:
        rows = s.execute(
            select(Prediction.match_id, Prediction.pred_home, Prediction.pred_away)
            .where(Prediction.user_id == user_id)
        ).all()
    return {mid: (h, a) for mid, h, a in rows}


def _count_tipped(user_id: int) -> int:
    with get_session() as s:
        return s.scalar(
            select(func.count()).select_from(Prediction).where(Prediction.user_id == user_id)
        ) or 0


def _get_joker_match_id(user_id: int) -> int | None:
    with get_session() as s:
        u = s.get(User, user_id)
        return u.joker_match_id if u else None


def _today_open_count(by_phase: dict, preds: dict) -> int:
    today = datetime.now(DISPLAY_TIMEZONE).date()
    count = 0
    for matches in by_phase.values():
        for m in matches:
            if m.is_locked or m.id in preds:
                continue
            if m.kickoff_utc:
                ko = m.kickoff_utc if m.kickoff_utc.tzinfo else m.kickoff_utc.replace(tzinfo=timezone.utc)
                if ko.astimezone(DISPLAY_TIMEZONE).date() == today:
                    count += 1
    return count


def _joker_match_locked(joker_match_id: int | None) -> bool:
    if joker_match_id is None:
        return False
    with get_session() as s:
        m = s.get(Match, joker_match_id)
        return m.is_locked if m else False


def _next_kickoff_iso() -> str | None:
    """ISO-String des nächsten noch nicht gesperrten Spiels."""
    now = datetime.now(timezone.utc)
    with get_session() as s:
        m = s.scalar(
            select(Match)
            .where(Match.kickoff_utc > now)
            .order_by(Match.kickoff_utc)
        )
        if m and m.kickoff_utc:
            ko = m.kickoff_utc
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            return ko.isoformat()
    return None


@router.get("/tipps")
async def tipps_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    by_phase = _load_matches()
    preds = _load_predictions(user["id"])
    count = _count_tipped(user["id"])
    joker_match_id = _get_joker_match_id(user["id"])
    joker_locked = _joker_match_locked(joker_match_id)
    today_open = _today_open_count(by_phase, preds)
    next_kickoff = _next_kickoff_iso()
    group_matches = by_phase.get("group", [])
    active_st = _active_spieltag(group_matches) if group_matches else 1
    spieltage: dict[int, list[Match]] = {}
    for m in group_matches:
        spieltage.setdefault(_spieltag(m.match_number), []).append(m)
    return templates.TemplateResponse(request, "tipps.html", {
        "user": user,
        "active": "tipps",
        "by_phase": by_phase,
        "preds": preds,
        "count": count,
        "total": TOTAL_MATCHES,
        "phases": PHASES,
        "fmt": _fmt,
        "joker_match_id": joker_match_id,
        "joker_locked": joker_locked,
        "today_open": today_open,
        "next_kickoff": next_kickoff,
        "flash": request.session.pop("flash", None),
        "spieltage": spieltage,
        "active_st": active_st,
    })


@router.post("/tipps")
async def tipps_post(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    # Erst gruppieren: {match_id: {"home": score, "away": score}}
    scores: dict[int, dict[str, int]] = {}
    for key, val in form.items():
        if not key.startswith("match_"):
            continue
        parts = key.split("_")
        if len(parts) != 3:
            continue
        _, match_id_str, side = parts
        if side not in ("home", "away"):
            continue
        try:
            match_id = int(match_id_str)
            score = int(val)
            if score < 0:
                continue
        except (ValueError, TypeError):
            continue
        scores.setdefault(match_id, {})[side] = score

    saved = 0
    with get_session() as s:
        for match_id, sides in scores.items():
            if "home" not in sides or "away" not in sides:
                continue
            m = s.get(Match, match_id)
            if m is None or m.is_locked:
                continue
            pred = s.scalar(
                select(Prediction).where(
                    Prediction.user_id == user["id"],
                    Prediction.match_id == match_id,
                )
            )
            if pred is None:
                pred = Prediction(user_id=user["id"], match_id=match_id,
                                  pred_home=sides["home"], pred_away=sides["away"])
                s.add(pred)
            else:
                pred.pred_home = sides["home"]
                pred.pred_away = sides["away"]
            saved += 1
    request.session["flash"] = {"message": f"{saved} Tipp(s) gespeichert.", "type": "success"}
    return RedirectResponse("/tipps", status_code=303)


@router.post("/tipps/joker/{match_id}")
async def set_joker(request: Request, match_id: int, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user
    with get_session() as s:
        u = s.get(User, user["id"])
        m = s.get(Match, match_id)
        if u is None or m is None:
            request.session["flash"] = {"message": "Ungültige Anfrage.", "type": "danger"}
            return RedirectResponse("/tipps", status_code=303)
        if u.joker_match_id is not None:
            current = s.get(Match, u.joker_match_id)
            if current and current.is_locked:
                request.session["flash"] = {"message": "Joker-Spiel bereits angepfiffen – kann nicht mehr geändert werden.", "type": "warning"}
                return RedirectResponse("/tipps", status_code=303)
        if m.is_locked:
            request.session["flash"] = {"message": "Spiel bereits gesperrt – Joker kann nicht mehr gesetzt werden.", "type": "danger"}
            return RedirectResponse("/tipps", status_code=303)
        u.joker_match_id = match_id
        home = m.home_team.name if m.home_team else (m.home_placeholder or "?")
        away = m.away_team.name if m.away_team else (m.away_placeholder or "?")
        _ = home, away
    request.session["flash"] = {
        "message": f"🃏 Joker gesetzt! Deine Punkte für dieses Spiel werden verdoppelt.",
        "type": "success"
    }
    return RedirectResponse("/tipps", status_code=303)
