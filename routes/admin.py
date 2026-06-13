from __future__ import annotations

import io
import os
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select

from auth import create_user, hash_password
from config import TOTAL_MATCHES
from data_players import dropdown_options, option_to_name
from data_teams import GROUPS
from database import get_session
from deps import require_admin, templates
from models import GroupPrediction, Match, Prediction, SpecialTip, Team, User
from settings import get_pool, get_rules, get_scoring, set_pool, set_rules, set_scoring
from scoring import recalculate_match, recalculate_everything
from standings import compute_standings

router = APIRouter(prefix="/admin")


@router.get("")
async def admin_get(request: Request, user: dict = Depends(require_admin)):
    with get_session() as s:
        users = list(s.scalars(select(User).order_by(User.display_name)).all())
        open_matches = list(s.execute(
            select(Match).where(Match.is_finished == False).order_by(Match.kickoff_utc)
        ).scalars().all())
        for m in open_matches:
            _ = m.home_team, m.away_team
        finished_matches = list(s.execute(
            select(Match).where(Match.is_finished == True).order_by(Match.kickoff_utc)
        ).scalars().all())
        for m in finished_matches:
            _ = m.home_team, m.away_team

    scoring = get_scoring()
    pool = get_pool()
    rules = get_rules()
    tiers = pool.get("payout_tiers", {})
    thresholds = pool.get("tier_thresholds", [15, 20])

    return templates.TemplateResponse(request, "admin.html", {
        "user": user, "active": "admin",
        "users": users,
        "open_matches": open_matches,
        "finished_matches": finished_matches,
        "scoring": scoring,
        "pool": pool,
        "tiers": tiers,
        "thresholds": thresholds,
        "rules": rules,
        "flash": request.session.pop("flash", None),
    })


# ── Ergebnisse ──────────────────────────────────────────────────────────────

@router.post("/result/{match_id}")
async def save_result(
    request: Request,
    match_id: int,
    result_home: int = Form(...),
    result_away: int = Form(...),
    went_to_penalties: bool = Form(False),
    user: dict = Depends(require_admin),
):
    with get_session() as s:
        m = s.get(Match, match_id)
        if m:
            m.result_home = result_home
            m.result_away = result_away
            m.is_finished = True
            m.went_to_penalties = went_to_penalties
            if result_home > result_away:
                m.winner_team_id = m.home_team_id
            elif result_away > result_home:
                m.winner_team_id = m.away_team_id
            else:
                m.winner_team_id = None
    recalculate_match(match_id)
    request.session["flash"] = {"message": "Ergebnis gespeichert.", "type": "success"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/result/{match_id}/undo")
async def undo_result(request: Request, match_id: int, user: dict = Depends(require_admin)):
    with get_session() as s:
        m = s.get(Match, match_id)
        if m:
            m.result_home = None
            m.result_away = None
            m.is_finished = False
            m.winner_team_id = None
            m.went_to_penalties = False
            for p in s.scalars(select(Prediction).where(Prediction.match_id == match_id)).all():
                p.points_awarded = 0
    request.session["flash"] = {"message": "Ergebnis zurückgesetzt.", "type": "warning"}
    return RedirectResponse("/admin", status_code=303)


# ── Nutzer ───────────────────────────────────────────────────────────────────

@router.post("/user/create")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    is_admin_flag: bool = Form(False),
    user: dict = Depends(require_admin),
):
    try:
        create_user(
            username.strip(),
            display_name.strip() or username.strip(),
            password,
            is_admin=is_admin_flag,
        )
        request.session["flash"] = {"message": f"Nutzer '{username}' angelegt.", "type": "success"}
    except ValueError as e:
        request.session["flash"] = {"message": str(e), "type": "danger"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{user_id}/reset-password")
async def reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    user: dict = Depends(require_admin),
):
    if len(new_password) < 6:
        request.session["flash"] = {"message": "Passwort muss mind. 6 Zeichen haben.", "type": "danger"}
        return RedirectResponse("/admin", status_code=303)
    name = None
    with get_session() as s:
        u = s.get(User, user_id)
        if u:
            u.password_hash = hash_password(new_password)
            name = u.display_name
    if name:
        request.session["flash"] = {"message": f"Passwort für '{name}' zurückgesetzt.", "type": "success"}
    else:
        request.session["flash"] = {"message": "Nutzer nicht gefunden.", "type": "danger"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{user_id}/delete")
async def delete_user(request: Request, user_id: int, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        request.session["flash"] = {"message": "Du kannst dich nicht selbst löschen.", "type": "danger"}
        return RedirectResponse("/admin", status_code=303)
    name = None
    with get_session() as s:
        u = s.get(User, user_id)
        if u:
            name = u.display_name
            s.delete(u)
    if name:
        request.session["flash"] = {"message": f"Nutzer '{name}' gelöscht.", "type": "success"}
    else:
        request.session["flash"] = {"message": "Nutzer nicht gefunden.", "type": "danger"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{user_id}/toggle-admin")
async def toggle_admin(request: Request, user_id: int, user: dict = Depends(require_admin)):
    with get_session() as s:
        u = s.get(User, user_id)
        if u and u.id != user["id"]:
            u.is_admin = not u.is_admin
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{user_id}/pool")
async def update_pool_status(
    request: Request,
    user_id: int,
    in_pool: bool = Form(False),
    has_paid: bool = Form(False),
    user: dict = Depends(require_admin),
):
    with get_session() as s:
        u = s.get(User, user_id)
        if u:
            u.in_pool = in_pool
            u.has_paid = has_paid if in_pool else False
    return RedirectResponse("/admin#kasse", status_code=303)


# ── Scoring ──────────────────────────────────────────────────────────────────

@router.post("/scoring")
async def save_scoring(request: Request, user: dict = Depends(require_admin)):
    form = await request.form()
    def _int(key: str, default: int) -> int:
        try:
            return max(0, int(form.get(key, default)))
        except (ValueError, TypeError):
            return default

    scoring = {
        "exact":               _int("exact", 4),
        "goal_diff":           _int("goal_diff", 3),
        "tendency":            _int("tendency", 2),
        "ko_advance_bonus":    _int("ko_advance_bonus", 1),
        "group_first":         _int("group_first", 3),
        "group_second":        _int("group_second", 2),
        "champion":            _int("champion", 15),
        "top_scorer":          _int("top_scorer", 10),
        "total_goals":         _int("total_goals", 5),
        "total_goals_tolerance": _int("total_goals_tolerance", 5),
    }
    set_scoring(scoring)
    recalculate_everything()
    request.session["flash"] = {"message": "Punktesystem gespeichert und alle Punkte neu berechnet.", "type": "success"}
    return RedirectResponse("/admin#punktesystem", status_code=303)


# ── Pool / Kasse ─────────────────────────────────────────────────────────────

@router.post("/pool")
async def save_pool(request: Request, user: dict = Depends(require_admin)):
    form = await request.form()
    try:
        buy_in = float(form.get("buy_in", 20))
    except (ValueError, TypeError):
        buy_in = 20.0

    def _pct(key: str) -> float:
        try:
            return max(0.0, min(1.0, float(form.get(key, 0)) / 100))
        except (ValueError, TypeError):
            return 0.0

    def _int(key: str, default: int) -> int:
        try:
            return max(1, int(form.get(key, default)))
        except (ValueError, TypeError):
            return default

    # Prozent → Anteile (werden intern normiert)
    def _tier(prefix: str, n: int) -> list[float]:
        vals = [_pct(f"{prefix}_{i}") for i in range(1, n + 1)]
        total = sum(vals)
        return [v / total for v in vals] if total > 0 else vals

    pool = {
        "enabled": form.get("enabled") == "on",
        "buy_in": buy_in,
        "currency": "EUR",
        "payout_tiers": {
            "3": _tier("t3", 3),
            "4": _tier("t4", 4),
            "5": _tier("t5", 5),
        },
        "tier_thresholds": [
            _int("threshold_4_minus1", 14) + 1,  # "Bis X" → Schwellenwert = X+1
            _int("threshold_5", 20),
        ],
    }
    set_pool(pool)
    request.session["flash"] = {"message": "Kassen-Einstellungen gespeichert.", "type": "success"}
    return RedirectResponse("/admin#kasse", status_code=303)


# ── Regeln ───────────────────────────────────────────────────────────────────

@router.post("/rules")
async def save_rules(
    request: Request,
    rules_text: str = Form(...),
    user: dict = Depends(require_admin),
):
    set_rules(rules_text)
    request.session["flash"] = {"message": "Spielregeln gespeichert.", "type": "success"}
    return RedirectResponse("/admin#regeln", status_code=303)


# ── Sync ─────────────────────────────────────────────────────────────────────

@router.post("/sync")
async def manual_sync(request: Request, user: dict = Depends(require_admin)):
    try:
        from results_sync import sync_results
        n = sync_results()
        request.session["flash"] = {"message": f"{n} Spiel(e) aktualisiert.", "type": "success"}
    except Exception as e:
        request.session["flash"] = {"message": f"Sync-Fehler: {e}", "type": "danger"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/test-api")
async def test_api(request: Request, user: dict = Depends(require_admin)):
    import os
    import httpx
    key = os.environ.get("FOOTBALL_API_KEY", "")
    if not key:
        request.session["flash"] = {"message": "FOOTBALL_API_KEY ist nicht gesetzt.", "type": "danger"}
        return RedirectResponse("/admin", status_code=303)
    try:
        resp = httpx.get(
            "https://api.football-data.org/v4/competitions/2000/matches?status=LIVE",
            headers={"X-Auth-Token": key},
            timeout=10,
        )
        msg = f"API Status: {resp.status_code} – {resp.text[:300]}"
        ftype = "success" if resp.status_code == 200 else "danger"
    except Exception as e:
        msg = f"Verbindungsfehler: {e}"
        ftype = "danger"
    request.session["flash"] = {"message": msg, "type": ftype}
    return RedirectResponse("/admin", status_code=303)


# ── Siegerurkunden ────────────────────────────────────────────────────────────

@router.post("/demo/simulate")
async def demo_simulate(request: Request, user: dict = Depends(require_admin)):
    try:
        from demo_data import simulate
        simulate()
        request.session["flash"] = {"message": "Komplette WM simuliert! Alle 104 Spiele und Punkte berechnet.", "type": "success"}
    except Exception as e:
        request.session["flash"] = {"message": f"Fehler bei Simulation: {e}", "type": "danger"}
    return RedirectResponse("/admin#tab-demo", status_code=303)


@router.post("/demo/reset")
async def demo_reset(request: Request, user: dict = Depends(require_admin)):
    try:
        from demo_data import reset
        reset()
        request.session["flash"] = {"message": "Demo-Daten zurückgesetzt.", "type": "success"}
    except Exception as e:
        request.session["flash"] = {"message": f"Fehler beim Reset: {e}", "type": "danger"}
    return RedirectResponse("/admin#tab-demo", status_code=303)


@router.get("/bonus")
async def bonus_admin_get(request: Request, uid: int | None = None, user: dict = Depends(require_admin)):
    with get_session() as s:
        users = list(s.scalars(select(User).order_by(User.display_name)).all())
        selected_user = None
        gpreds: dict[str, tuple] = {}
        special = None
        teams_by_group: dict[str, list] = {}

        if uid:
            selected_user = s.get(User, uid)
            if selected_user:
                for gp in s.scalars(select(GroupPrediction).where(GroupPrediction.user_id == uid)).all():
                    gpreds[gp.group_letter] = (gp.predicted_1st, gp.predicted_2nd)
                special = s.scalar(select(SpecialTip).where(SpecialTip.user_id == uid))
                if special and special.champion_team:
                    _ = special.champion_team

        for t in s.scalars(select(Team).order_by(Team.group_letter, Team.name)).all():
            teams_by_group.setdefault(t.group_letter, []).append(t)

    return templates.TemplateResponse(request, "admin_bonus.html", {
        "user": user, "active": "admin",
        "users": users,
        "selected_user": selected_user,
        "uid": uid,
        "gpreds": gpreds,
        "special": special,
        "teams_by_group": teams_by_group,
        "groups": sorted(GROUPS.keys()),
        "scorer_opts": dropdown_options(),
        "flash": request.session.pop("flash", None),
    })


@router.post("/bonus/{user_id}")
async def bonus_admin_save(request: Request, user_id: int, user: dict = Depends(require_admin)):
    form = await request.form()
    with get_session() as s:
        target = s.get(User, user_id)
        if not target:
            request.session["flash"] = {"message": "Nutzer nicht gefunden.", "type": "danger"}
            return RedirectResponse(f"/admin/bonus?uid={user_id}", status_code=303)

        # Sonder-Tipps
        try:
            champ = int(form.get("champion") or 0) or None
        except (ValueError, TypeError):
            champ = None
        scorer_opt = form.get("scorer", "")
        scorer = option_to_name(scorer_opt) if scorer_opt else None
        try:
            total = int(form.get("total_goals") or 0)
        except (ValueError, TypeError):
            total = 0

        sp = s.scalar(select(SpecialTip).where(SpecialTip.user_id == user_id))
        if not sp:
            sp = SpecialTip(user_id=user_id)
            s.add(sp)
        sp.champion_team_id = champ
        sp.top_scorer = scorer
        sp.total_goals = total

        # Gruppen-Tipps
        for letter in GROUPS.keys():
            try:
                first = int(form.get(f"g1_{letter}") or 0) or None
                second = int(form.get(f"g2_{letter}") or 0) or None
            except (ValueError, TypeError):
                first = second = None
            gp = s.scalar(select(GroupPrediction).where(
                GroupPrediction.user_id == user_id,
                GroupPrediction.group_letter == letter,
            ))
            if not gp:
                gp = GroupPrediction(user_id=user_id, group_letter=letter)
                s.add(gp)
            gp.predicted_1st = first
            gp.predicted_2nd = second

    request.session["flash"] = {"message": f"Bonus Tipps für '{target.display_name}' gespeichert.", "type": "success"}
    return RedirectResponse(f"/admin/bonus?uid={user_id}", status_code=303)


@router.get("/urkunden")
async def urkunden_get(request: Request, user: dict = Depends(require_admin)):
    from sqlalchemy import func, select as sa_select
    rows = compute_standings()
    pool = get_pool()

    with get_session() as s:
        tip_counts = dict(
            s.execute(
                sa_select(Prediction.user_id, func.count(Prediction.id))
                .group_by(Prediction.user_id)
            ).all()
        )

    KO_PHASES = {"round32", "round16", "quarter", "semi", "third_place", "final"}

    for r in rows:
        r.tips_total = tip_counts.get(r.user_id, 0)
        match_pts = sum(r.phase_points.values())
        r.pts_per_game = round(match_pts / r.tips_total, 2) if r.tips_total > 0 else 0.0

    sorted_group = sorted(rows, key=lambda r: -(r.phase_points.get("group", 0)))
    for i, r in enumerate(sorted_group, 1):
        r.group_rank = i

    sorted_ko = sorted(rows, key=lambda r: -sum(r.phase_points.get(p, 0) for p in KO_PHASES))
    for i, r in enumerate(sorted_ko, 1):
        r.ko_rank = i

    return templates.TemplateResponse(request, "urkunden.html", {
        "user": user,
        "rows": rows,
        "pool": pool,
        "total_matches": TOTAL_MATCHES,
        "flash": None,
    })


@router.get("/backup")
async def db_backup(request: Request, user: dict = Depends(require_admin)):
    """Exportiert die DB als SQL-Dump zum Download."""
    db_url = os.environ.get("DATABASE_URL", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    filename = f"wm2026_backup_{ts}.sql"

    if db_url:
        # PostgreSQL via pg_dump
        pg_url = db_url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
        try:
            result = subprocess.run(
                ["pg_dump", "--no-owner", "--no-acl", pg_url],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                request.session["flash"] = {"message": f"pg_dump Fehler: {result.stderr[:200]}", "type": "danger"}
                return RedirectResponse("/admin", status_code=303)
            content = result.stdout.encode("utf-8")
        except FileNotFoundError:
            request.session["flash"] = {"message": "pg_dump nicht gefunden – Backup nur lokal möglich.", "type": "danger"}
            return RedirectResponse("/admin", status_code=303)
    else:
        # SQLite: rohe DB-Datei als Bytes senden
        db_path = "wm2026.db"
        if not os.path.exists(db_path):
            request.session["flash"] = {"message": "Keine lokale DB gefunden.", "type": "danger"}
            return RedirectResponse("/admin", status_code=303)
        filename = f"wm2026_backup_{ts}.db"
        with open(db_path, "rb") as f:
            content = f.read()

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
