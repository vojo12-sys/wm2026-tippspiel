from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from database import init_db

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.environ.get("FOOTBALL_API_KEY"):
        from results_sync import sync_results
        scheduler.add_job(sync_results, "interval", minutes=5, id="results_sync")
        scheduler.start()
        logger.info("Ergebnis-Sync gestartet (alle 5 Minuten)")
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="WM 2026 Tippspiel", lifespan=lifespan)

_secret = os.environ.get("SECRET_KEY", "dev-secret-change-me")
if _secret == "dev-secret-change-me":
    logger.warning("SECRET_KEY nicht gesetzt – unsicherer Dev-Schlüssel aktiv!")

app.add_middleware(
    SessionMiddleware,
    secret_key=_secret,
    session_cookie="wm2026_session",
    max_age=60 * 60 * 24 * 30,
    https_only=bool(os.environ.get("RENDER", False)),
)

app.mount("/static", StaticFiles(directory="static"), name="static")

from routes import auth, tipps, langfrist, spielplan, leaderboard, admin, regeln, uebersicht, torschuetzen, stats, profil, teams
app.include_router(auth.router)
app.include_router(tipps.router)
app.include_router(langfrist.router)
app.include_router(spielplan.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)
app.include_router(regeln.router)
app.include_router(uebersicht.router)
app.include_router(torschuetzen.router)
app.include_router(stats.router)
app.include_router(profil.router)
app.include_router(teams.router)
