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

def _get_live_scores():
    try:
        from results_sync import get_live_scores
        return get_live_scores()
    except Exception:
        return {}

_env.globals["get_live_scores"] = _get_live_scores
templates = Jinja2Templates(env=_env)


def get_current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_user(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    return user


def require_admin(request: Request):
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return user
