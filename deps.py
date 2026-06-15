from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from settings import get_pool

def get_pot_info() -> dict:
    """Topf-Infos für die Sidebar: Gesamtbetrag und Einzahlerzahl."""
    try:
        from sqlalchemy import select, func
        from database import get_session
        from models import User
        pool = get_pool()
        if not pool.get("enabled"):
            return {"enabled": False}
        with get_session() as s:
            payers = s.scalar(
                select(func.count()).select_from(User).where(User.in_pool == True)
            ) or 0
        buy_in = float(pool.get("buy_in", 20))
        return {
            "enabled": True,
            "payers": payers,
            "buy_in": buy_in,
            "pot_total": round(payers * buy_in, 2),
            "currency": pool.get("currency", "EUR"),
        }
    except Exception:
        return {"enabled": False}

# Python 3.14 Kompatibilität: Jinja2 LRUCache-Bug umgehen via cache_size=0
_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
    cache_size=0,
)
_env.globals["get_pool"] = get_pool
_env.globals["get_pot_info"] = get_pot_info

def get_bonus_tips_incomplete(user_id: int | None) -> bool:
    """True wenn Turnier noch nicht gestartet UND User noch keine Bonus Tipps abgegeben hat."""
    if user_id is None:
        return False
    from datetime import datetime, timezone
    from config import TOURNAMENT_START_UTC
    if datetime.now(timezone.utc) >= datetime.fromisoformat(TOURNAMENT_START_UTC):
        return False
    try:
        from sqlalchemy import select
        from database import get_session
        from models import SpecialTip, GroupPrediction
        with get_session() as s:
            has_special = s.scalar(
                select(SpecialTip).where(SpecialTip.user_id == user_id)
            ) is not None
            has_group = s.scalar(
                select(GroupPrediction).where(GroupPrediction.user_id == user_id)
            ) is not None
        return not (has_special or has_group)
    except Exception:
        return False


def _get_live_scores():
    try:
        from results_sync import get_live_scores
        return get_live_scores()
    except Exception:
        return {}

_env.globals["get_live_scores"] = _get_live_scores
_env.globals["get_bonus_tips_incomplete"] = get_bonus_tips_incomplete
templates = Jinja2Templates(env=_env)


def get_current_user(request: Request) -> dict | None:
    return request.session.get("user")


_TRACKED_ROUTES = {"/tipps", "/langfrist", "/spielplan", "/leaderboard",
                   "/uebersicht", "/torschuetzen", "/stats", "/profil",
                   "/regeln", "/teams", "/"}

def _log_visit(user_id: int, path: str) -> None:
    try:
        from database import get_session
        from models import User, UserVisit
        from datetime import datetime, timezone
        route = path.split("?")[0]
        if route not in _TRACKED_ROUTES:
            return
        with get_session() as s:
            s.add(UserVisit(user_id=user_id, route=route))
            u = s.get(User, user_id)
            if u:
                u.last_seen = datetime.now(timezone.utc)
                u.visit_count = (u.visit_count or 0) + 1
    except Exception:
        pass


def require_user(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    if request.method == "GET":
        _log_visit(user["id"], request.url.path)
    return user


def require_admin(request: Request):
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return user


def require_non_spectator(request: Request):
    """Wie require_user, aber blockiert Zuschauer-Accounts."""
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.get("is_spectator"):
        request.session["flash"] = {
            "message": "Diese Seite ist nur für Tipp-Teilnehmer verfügbar.",
            "type": "warning",
        }
        return RedirectResponse("/home", status_code=302)
    return user
