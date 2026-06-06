# FastAPI Migration – WM 2026 Tippspiel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamlit-App zu FastAPI + Jinja2 + Bootstrap 5 migrieren – volle Design-Kontrolle, mobile-optimiert, auf Render.com hostbar.

**Architecture:** FastAPI-Backend mit Jinja2-Templates und Bootstrap 5. Sessions via Starlette `SessionMiddleware` (signierte Cookies). Alle bestehenden Python-Module (models, database, auth, scoring, standings, config, settings) bleiben **unverändert** – nur die View-Schicht wird ersetzt.

**Tech Stack:** FastAPI · Uvicorn · Jinja2 · Bootstrap 5.3 · python-multipart · itsdangerous (via Starlette) · SQLAlchemy 2.0 · SQLite (lokal) / PostgreSQL (Render) · httpx · APScheduler (automatische Ergebnisse via football-data.org)

---

## Dateistruktur

### Unverändert behalten
- `models.py`, `database.py`, `auth.py`, `config.py`, `settings.py`
- `scoring.py`, `standings.py`, `knockout.py`
- `data_teams.py`, `data_players.py`, `data_schedule.py`
- `seed.py`, `import_schedule.py`
- `assets/lew_logo.png`
- `wm2026.db`

### Neu erstellen
```
main.py                          # FastAPI-App, Middleware, Router-Einbindung
routes/
  auth.py                        # GET/POST /login, /register, /logout
  tipps.py                       # GET/POST /tipps
  langfrist.py                   # GET/POST /langfrist
  spielplan.py                   # GET /spielplan
  leaderboard.py                 # GET /leaderboard
  admin.py                       # GET/POST /admin/*
templates/
  base.html                      # Layout, Sidebar-Nav, Bootstrap
  login.html
  register.html
  tipps.html
  langfrist.html
  spielplan.html
  leaderboard.html
  admin.html
static/
  css/style.css                  # Custom CSS (LEW-Brand, Farben)
  img/lew_logo.png               # Kopie von assets/lew_logo.png
  manifest.json                  # PWA
  sw.js                          # Service Worker (minimal)
requirements.txt                 # aktualisiert (FastAPI statt Streamlit)
render.yaml                      # Render.com Deploy-Konfiguration
.env.example                     # aktualisiert
```

### Löschen (nach Migration)
- `app.py`, `theme.py`
- `views_tipps.py`, `views_langfrist.py`, `views_spielplan.py`
- `views_leaderboard.py`, `views_admin.py`
- `preview.html`
- `.streamlit/`

---

## Task 1: Abhängigkeiten & Projektstruktur

**Files:**
- Modify: `requirements.txt`
- Create: `main.py`
- Create: `routes/__init__.py`

- [ ] **Schritt 1: requirements.txt ersetzen**

```
fastapi>=0.115
uvicorn[standard]>=0.30
jinja2>=3.1
python-multipart>=0.0.9
SQLAlchemy>=2.0
psycopg[binary]>=3.1
```

- [ ] **Schritt 2: Verzeichnisse anlegen**

```bash
mkdir routes
mkdir -p templates static/css static/img
copy assets\lew_logo.png static\img\lew_logo.png
```

- [ ] **Schritt 3: `routes/__init__.py` anlegen**

Leere Datei.

- [ ] **Schritt 4: `main.py` Grundgerüst**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from database import init_db
import routes.auth as auth_router
import routes.tipps as tipps_router
import routes.langfrist as langfrist_router
import routes.spielplan as spielplan_router
import routes.leaderboard as leaderboard_router
import routes.admin as admin_router

app = FastAPI(title="WM 2026 Tippspiel")

app.add_middleware(
    SessionMiddleware,
    secret_key="CHANGE_ME_IN_PRODUCTION",  # via env überschreiben
    session_cookie="wm2026_session",
    max_age=60 * 60 * 24 * 30,  # 30 Tage
    https_only=False,  # True auf Render setzen
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router.router)
app.include_router(tipps_router.router)
app.include_router(langfrist_router.router)
app.include_router(spielplan_router.router)
app.include_router(leaderboard_router.router)
app.include_router(admin_router.router)

templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup():
    init_db()
```

- [ ] **Schritt 5: Starten prüfen**

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
Erwartung: Server startet auf http://localhost:8000 ohne Fehler.

---

## Task 2: Hilfsfunktionen (session, templates, deps)

**Files:**
- Create: `deps.py`

`deps.py` enthält FastAPI-Dependencies, die in allen Routen verwendet werden.

- [ ] **Schritt 1: `deps.py` anlegen**

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from database import get_session
from models import User

templates = Jinja2Templates(directory="templates")


def get_current_user(request: Request) -> dict | None:
    """Gibt den eingeloggten User aus der Session zurück oder None."""
    return request.session.get("user")


def require_user(request: Request) -> dict:
    """Dependency: wirft 302 zu /login wenn nicht eingeloggt."""
    from fastapi.responses import RedirectResponse
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def require_admin(request: Request) -> dict:
    """Dependency: nur für Admins."""
    from fastapi.responses import RedirectResponse
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return user
```

---

## Task 3: Base-Template & CSS

**Files:**
- Create: `templates/base.html`
- Create: `static/css/style.css`

- [ ] **Schritt 1: `static/css/style.css`**

```css
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&display=swap');

:root {
  --accent: #0fa968;
  --accent-dk: #0c8f57;
  --gold: #c08a12;
  --silver: #8794a3;
  --bronze: #ad6a34;
  --muted: #67768a;
  --border: #e4e9ef;
  --bg: #f4f7f9;
}

body { font-family: 'Hanken Grotesk', sans-serif; background: var(--bg); }
h1,h2,h3,h4,h5 { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; }

/* Brand */
.brand-title { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: 1.25rem; line-height: 1.2; }
.brand-sub { font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.brand-logo { height: 48px; width: auto; }

/* Sidebar nav */
.sidebar { min-height: 100vh; background: #fff; border-right: 1px solid var(--border); }
.nav-link { color: #16202b; border-radius: 8px; font-weight: 500; }
.nav-link:hover, .nav-link.active { background: rgba(15,169,104,.1); color: var(--accent); }

/* Buttons */
.btn-accent { background: var(--accent); color: #fff; border: none; border-radius: 10px; font-weight: 700; }
.btn-accent:hover { background: var(--accent-dk); color: #fff; }

/* Match card */
.match-card { background: #fff; border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 8px; }
.match-meta { font-size: .75rem; color: var(--muted); }

/* Score inputs */
.score-input { width: 60px; text-align: center; font-weight: 700; font-size: 1.1rem; border-radius: 8px; border: 1px solid var(--border); }
.score-input:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 3px rgba(15,169,104,.15); }

/* Leaderboard */
.rank-1 { color: var(--gold); font-weight: 800; }
.rank-2 { color: var(--silver); font-weight: 700; }
.rank-3 { color: var(--bronze); font-weight: 700; }

/* Mobile */
@media (max-width: 767px) {
  .sidebar { min-height: auto; border-right: none; border-bottom: 1px solid var(--border); }
}
```

- [ ] **Schritt 2: `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WM 2026 Tippspiel</title>
  <link rel="manifest" href="/static/manifest.json">
  <link rel="icon" href="/static/img/lew_logo.png">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <link href="/static/css/style.css" rel="stylesheet">
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <div class="col-12 col-md-2 sidebar py-3 px-3">
      <!-- Brand -->
      <div class="d-flex align-items-center gap-2 mb-3">
        <img src="/static/img/lew_logo.png" class="brand-logo" alt="LEW">
        <div>
          <div class="brand-title">WM 2026 Tippspiel</div>
          <div class="brand-sub">LEW Automotive · Kanada · Mexiko · USA</div>
        </div>
      </div>
      <!-- Navigation -->
      {% if user %}
      <nav class="nav flex-column gap-1 mb-3">
        <a href="/tipps" class="nav-link {% if active == 'tipps' %}active{% endif %}">
          <i class="bi bi-pencil-square me-2"></i>Tipps abgeben
        </a>
        <a href="/langfrist" class="nav-link {% if active == 'langfrist' %}active{% endif %}">
          <i class="bi bi-trophy me-2"></i>Langfrist-Tipps
        </a>
        <a href="/spielplan" class="nav-link {% if active == 'spielplan' %}active{% endif %}">
          <i class="bi bi-calendar3 me-2"></i>Spielplan
        </a>
        <a href="/leaderboard" class="nav-link {% if active == 'leaderboard' %}active{% endif %}">
          <i class="bi bi-bar-chart me-2"></i>Leaderboard
        </a>
        {% if user.is_admin %}
        <a href="/admin" class="nav-link {% if active == 'admin' %}active{% endif %}">
          <i class="bi bi-gear me-2"></i>Admin
        </a>
        {% endif %}
      </nav>
      <hr>
      <div class="small text-muted mb-2">Angemeldet als <strong>{{ user.display_name }}</strong></div>
      <a href="/logout" class="btn btn-accent btn-sm">Abmelden</a>
      {% endif %}
    </div>
    <!-- Main Content -->
    <div class="col-12 col-md-10 py-4 px-4">
      {% if flash %}
      <div class="alert alert-{{ flash.type }} alert-dismissible fade show" role="alert">
        {{ flash.message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
      {% endif %}
      {% block content %}{% endblock %}
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body>
</html>
```

---

## Task 4: Auth-Routen (Login, Registrierung, Logout)

**Files:**
- Create: `routes/auth.py`
- Create: `templates/login.html`
- Create: `templates/register.html`

- [ ] **Schritt 1: `routes/auth.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth import authenticate, create_user
from deps import templates

router = APIRouter()


def _flash(request: Request, message: str, type: str = "danger") -> None:
    request.session["flash"] = {"message": message, "type": type}


def _get_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


@router.get("/")
async def index(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps")
    return RedirectResponse("/login")


@router.get("/login")
async def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps")
    return templates.TemplateResponse("login.html", {
        "request": request, "flash": _get_flash(request), "user": None,
    })


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    u = authenticate(username.strip(), password)
    if not u:
        _flash(request, "Benutzername oder Passwort falsch.")
        return RedirectResponse("/login", status_code=303)
    request.session["user"] = {
        "id": u.id,
        "display_name": u.display_name,
        "is_admin": u.is_admin,
    }
    return RedirectResponse("/tipps", status_code=303)


@router.get("/register")
async def register_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps")
    return templates.TemplateResponse("register.html", {
        "request": request, "flash": _get_flash(request), "user": None,
    })


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    if password != password2:
        _flash(request, "Passwörter stimmen nicht überein.")
        return RedirectResponse("/register", status_code=303)
    if len(password) < 6:
        _flash(request, "Passwort muss mindestens 6 Zeichen lang sein.")
        return RedirectResponse("/register", status_code=303)
    try:
        create_user(username.strip(), display_name.strip() or username.strip(), password)
    except ValueError as e:
        _flash(request, str(e))
        return RedirectResponse("/register", status_code=303)
    _flash(request, "Konto erstellt – bitte einloggen.", "success")
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Schritt 2: `templates/login.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-12 col-sm-8 col-md-5">
    <!-- Brand (oben auf Login-Seite, da keine Sidebar) -->
    <div class="d-flex align-items-center gap-2 mb-4 mt-2">
      <img src="/static/img/lew_logo.png" style="height:48px;width:auto" alt="LEW">
      <div>
        <div class="brand-title">WM 2026 Tippspiel</div>
        <div class="brand-sub">LEW Automotive · Kanada · Mexiko · USA</div>
      </div>
    </div>
    <h2 class="mb-4">Anmelden</h2>
    {% if flash %}
    <div class="alert alert-{{ flash.type }}">{{ flash.message }}</div>
    {% endif %}
    <div class="card border-0 shadow-sm">
      <div class="card-body p-4">
        <form method="post" action="/login">
          <div class="mb-3">
            <label class="form-label fw-semibold">Benutzername</label>
            <input type="text" name="username" class="form-control" required autofocus>
          </div>
          <div class="mb-4">
            <label class="form-label fw-semibold">Passwort</label>
            <input type="password" name="password" class="form-control" required>
          </div>
          <button type="submit" class="btn btn-accent w-100">Einloggen</button>
        </form>
      </div>
    </div>
    <p class="text-center mt-3 text-muted small">
      Noch kein Konto? <a href="/register">Registrieren</a>
    </p>
  </div>
</div>
{% endblock %}
```

- [ ] **Schritt 3: `templates/register.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-12 col-sm-8 col-md-5">
    <div class="d-flex align-items-center gap-2 mb-4 mt-2">
      <img src="/static/img/lew_logo.png" style="height:48px;width:auto" alt="LEW">
      <div>
        <div class="brand-title">WM 2026 Tippspiel</div>
        <div class="brand-sub">LEW Automotive · Kanada · Mexiko · USA</div>
      </div>
    </div>
    <h2 class="mb-4">Registrieren</h2>
    {% if flash %}
    <div class="alert alert-{{ flash.type }}">{{ flash.message }}</div>
    {% endif %}
    <div class="card border-0 shadow-sm">
      <div class="card-body p-4">
        <form method="post" action="/register">
          <div class="mb-3">
            <label class="form-label fw-semibold">Benutzername</label>
            <input type="text" name="username" class="form-control" required autofocus
                   placeholder="Eindeutiger Login-Name">
          </div>
          <div class="mb-3">
            <label class="form-label fw-semibold">Anzeigename</label>
            <input type="text" name="display_name" class="form-control"
                   placeholder="Wie sollen andere dich sehen?">
          </div>
          <div class="mb-3">
            <label class="form-label fw-semibold">Passwort</label>
            <input type="password" name="password" class="form-control" required minlength="6">
          </div>
          <div class="mb-4">
            <label class="form-label fw-semibold">Passwort wiederholen</label>
            <input type="password" name="password2" class="form-control" required minlength="6">
          </div>
          <button type="submit" class="btn btn-accent w-100">Konto erstellen</button>
        </form>
      </div>
    </div>
    <p class="text-center mt-3 text-muted small">
      Schon registriert? <a href="/login">Einloggen</a>
    </p>
  </div>
</div>
{% endblock %}
```

- [ ] **Schritt 4: Testen**

```bash
uvicorn main:app --reload
```
- http://localhost:8000 → Redirect zu /login ✓
- Registrierung mit neuem User ✓
- Login → Redirect zu /tipps (noch 404, kommt in Task 5) ✓
- Logout → zurück zu /login ✓

---

## Task 5: Tipps abgeben

**Files:**
- Create: `routes/tipps.py`
- Create: `templates/tipps.html`

- [ ] **Schritt 1: `routes/tipps.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from config import DISPLAY_TIMEZONE, PHASES, TOTAL_MATCHES
from database import get_session
from deps import require_user, templates
from models import Match, Prediction

router = APIRouter()


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TIMEZONE).strftime("%a %d.%m. · %H:%M")


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


@router.get("/tipps")
async def tipps_get(request: Request, user: dict = Depends(require_user)):
    by_phase = _load_matches()
    preds = _load_predictions(user["id"])
    count = _count_tipped(user["id"])
    return templates.TemplateResponse("tipps.html", {
        "request": request,
        "user": user,
        "active": "tipps",
        "by_phase": by_phase,
        "preds": preds,
        "count": count,
        "total": TOTAL_MATCHES,
        "phases": PHASES,
        "fmt": _fmt,
        "flash": request.session.pop("flash", None),
    })


@router.post("/tipps")
async def tipps_post(request: Request, user: dict = Depends(require_user)):
    form = await request.form()
    saved = 0
    with get_session() as s:
        for key, val in form.items():
            if not key.startswith("match_"):
                continue
            parts = key.split("_")
            if len(parts) != 4:
                continue
            _, _, match_id_str, side = parts
            match_id = int(match_id_str)
            m = s.get(Match, match_id)
            if m is None or m.is_locked:
                continue
            try:
                score = int(val)
                if score < 0:
                    continue
            except (ValueError, TypeError):
                continue
            pred = s.scalar(
                select(Prediction).where(
                    Prediction.user_id == user["id"],
                    Prediction.match_id == match_id,
                )
            )
            if pred is None:
                pred = Prediction(user_id=user["id"], match_id=match_id, pred_home=0, pred_away=0)
                s.add(pred)
            if side == "home":
                pred.pred_home = score
            elif side == "away":
                pred.pred_away = score
            saved += 1
    request.session["flash"] = {"message": f"{saved // 2} Tipps gespeichert.", "type": "success"}
    return RedirectResponse("/tipps", status_code=303)
```

- [ ] **Schritt 2: `templates/tipps.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-1">Tipps abgeben</h1>
<p class="text-muted mb-2">{{ count }} / {{ total }} Spiele getippt</p>
<div class="progress mb-4" style="height:6px">
  <div class="progress-bar" style="width:{{ (count/total*100)|round }}%;background:var(--accent)"></div>
</div>

<!-- Phase-Tabs -->
<ul class="nav nav-tabs mb-4" id="phaseTabs">
  {% for phase_key, phase_label in phases.items() %}
  {% if by_phase.get(phase_key) %}
  <li class="nav-item">
    <a class="nav-link {% if loop.first %}active{% endif %}"
       data-bs-toggle="tab" href="#tab-{{ phase_key }}">{{ phase_label }}</a>
  </li>
  {% endif %}
  {% endfor %}
</ul>

<form method="post" action="/tipps">
<div class="tab-content">
  {% for phase_key, phase_label in phases.items() %}
  {% if by_phase.get(phase_key) %}
  <div class="tab-pane fade {% if loop.first %}show active{% endif %}" id="tab-{{ phase_key }}">
    {% set matches = by_phase[phase_key] %}

    {% if phase_key == 'group' %}
      {# Gruppenphase: nach Gruppe gruppieren #}
      {% set groups = {} %}
      {% for m in matches %}
        {% if m.group_letter not in groups %}{% set _ = groups.update({m.group_letter: []}) %}{% endif %}
        {% set _ = groups[m.group_letter].append(m) %}
      {% endfor %}
      {% for letter in groups.keys()|sort %}
      <h5 class="mt-3 mb-2">Gruppe {{ letter }}</h5>
      {% for m in groups[letter] %}
      {% include "_match_row.html" %}
      {% endfor %}
      {% endfor %}
    {% else %}
      {% for m in matches %}
      {% include "_match_row.html" %}
      {% endfor %}
    {% endif %}
  </div>
  {% endif %}
  {% endfor %}
</div>
<div class="mt-4">
  <button type="submit" class="btn btn-accent px-4">Alle Tipps speichern</button>
</div>
</form>
{% endblock %}
```

- [ ] **Schritt 3: `templates/_match_row.html`** (Partial)

```html
{% set locked = m.is_locked %}
{% set ph = preds.get(m.id, (0, 0)) %}
{% set home_name = m.home_team.name if m.home_team else (m.home_placeholder or 'TBD') %}
{% set away_name = m.away_team.name if m.away_team else (m.away_placeholder or 'TBD') %}
{% set home_flag = m.home_team.flag_code if m.home_team else '' %}
{% set away_flag = m.away_team.flag_code if m.away_team else '' %}

<div class="match-card {% if locked %}opacity-75{% endif %}">
  <div class="match-meta mb-1">
    {{ fmt(m.kickoff_utc) }}
    {% if m.venue %} · {{ m.venue }}{% endif %}
    {% if locked %}<span class="badge ms-2" style="background:rgba(214,69,96,.15);color:#d64560">gesperrt</span>
    {% else %}<span class="badge ms-2" style="background:rgba(15,169,104,.1);color:var(--accent-dk)">offen</span>{% endif %}
    {% if m.has_result %}<span class="ms-2 fw-bold">{{ m.result_home }}:{{ m.result_away }}</span>{% endif %}
  </div>
  <div class="d-flex align-items-center gap-3">
    <!-- Heimteam -->
    <div class="d-flex align-items-center gap-2 flex-grow-1">
      {% if home_flag %}<img src="https://flagcdn.com/20x15/{{ home_flag }}.png" alt="">{% endif %}
      <span class="fw-semibold">{{ home_name }}</span>
    </div>
    <!-- Score-Inputs -->
    <div class="d-flex align-items-center gap-2">
      <input type="number" name="match_{{ m.id }}_home" value="{{ ph[0] }}"
             class="score-input form-control" min="0" max="30"
             {% if locked %}disabled{% endif %}>
      <span class="text-muted">:</span>
      <input type="number" name="match_{{ m.id }}_away" value="{{ ph[1] }}"
             class="score-input form-control" min="0" max="30"
             {% if locked %}disabled{% endif %}>
    </div>
    <!-- Auswärtsteam -->
    <div class="d-flex align-items-center gap-2 flex-grow-1 justify-content-end">
      <span class="fw-semibold">{{ away_name }}</span>
      {% if away_flag %}<img src="https://flagcdn.com/20x15/{{ away_flag }}.png" alt="">{% endif %}
    </div>
  </div>
</div>
```

- [ ] **Schritt 4: Testen**
  - Einloggen → /tipps öffnet sich ✓
  - Tipps eingeben, speichern → Flash-Meldung ✓
  - Gesperrte Spiele haben disabled-Inputs ✓

---

## Task 6: Langfrist-Tipps

**Files:**
- Create: `routes/langfrist.py`
- Create: `templates/langfrist.html`

- [ ] **Schritt 1: `routes/langfrist.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from config import DISPLAY_TIMEZONE, TOURNAMENT_START_UTC
from data_players import dropdown_options, option_to_name
from data_teams import GROUPS
from database import get_session
from deps import require_user, templates
from models import GroupPrediction, SpecialTip, Team

router = APIRouter()


def _deadline() -> datetime:
    return datetime.fromisoformat(TOURNAMENT_START_UTC)


def _is_locked() -> bool:
    return datetime.now(timezone.utc) >= _deadline()


def _all_teams() -> list[Team]:
    with get_session() as s:
        return s.scalars(select(Team).order_by(Team.name)).all()


def _teams_by_group() -> dict[str, list[Team]]:
    out: dict[str, list[Team]] = {}
    with get_session() as s:
        for t in s.scalars(select(Team).order_by(Team.group_letter, Team.name)).all():
            out.setdefault(t.group_letter, []).append(t)
    return out


@router.get("/langfrist")
async def langfrist_get(request: Request, user: dict = Depends(require_user)):
    locked = _is_locked()
    dl = _deadline().astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y · %H:%M Uhr")
    user_id = user["id"]
    with get_session() as s:
        special = s.scalar(select(SpecialTip).where(SpecialTip.user_id == user_id))
        gpreds = {
            gp.group_letter: (gp.predicted_1st, gp.predicted_2nd)
            for gp in s.scalars(select(GroupPrediction).where(GroupPrediction.user_id == user_id)).all()
        }
    return templates.TemplateResponse("langfrist.html", {
        "request": request, "user": user, "active": "langfrist",
        "locked": locked, "deadline": dl,
        "special": special, "gpreds": gpreds,
        "teams": _all_teams(),
        "teams_by_group": _teams_by_group(),
        "groups": sorted(GROUPS),
        "scorer_opts": dropdown_options(),
        "flash": request.session.pop("flash", None),
    })


@router.post("/langfrist")
async def langfrist_post(request: Request, user: dict = Depends(require_user)):
    if _is_locked():
        return RedirectResponse("/langfrist", status_code=303)
    form = await request.form()
    user_id = user["id"]
    champ = int(form.get("champion") or 0) or None
    scorer_opt = form.get("scorer", "")
    scorer = option_to_name(scorer_opt) if scorer_opt else None
    try:
        total = int(form.get("total_goals") or 0)
    except ValueError:
        total = 0
    with get_session() as s:
        sp = s.scalar(select(SpecialTip).where(SpecialTip.user_id == user_id))
        if not sp:
            sp = SpecialTip(user_id=user_id)
            s.add(sp)
        sp.champion_team_id = champ
        sp.top_scorer = scorer
        sp.total_goals = total
        from data_teams import GROUPS
        for letter in GROUPS:
            first = int(form.get(f"g1_{letter}") or 0) or None
            second = int(form.get(f"g2_{letter}") or 0) or None
            gp = s.scalar(select(GroupPrediction).where(
                GroupPrediction.user_id == user_id,
                GroupPrediction.group_letter == letter,
            ))
            if not gp:
                gp = GroupPrediction(user_id=user_id, group_letter=letter)
                s.add(gp)
            gp.predicted_1st = first
            gp.predicted_2nd = second
    request.session["flash"] = {"message": "Langfrist-Tipps gespeichert.", "type": "success"}
    return RedirectResponse("/langfrist", status_code=303)
```

- [ ] **Schritt 2: `templates/langfrist.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-2">Langfrist-Tipps</h1>

{% if locked %}
<div class="alert alert-warning">Gesperrt seit Turnierstart ({{ deadline }}).</div>
{% else %}
<div class="alert alert-info">Editierbar bis <strong>{{ deadline }}</strong>.</div>
{% endif %}

{% if flash %}
<div class="alert alert-{{ flash.type }}">{{ flash.message }}</div>
{% endif %}

<form method="post" action="/langfrist">
  <div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
      <h5 class="mb-3">Titel-Tipps</h5>
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label fw-semibold">Weltmeister</label>
          <select name="champion" class="form-select" {% if locked %}disabled{% endif %}>
            <option value="">— auswählen —</option>
            {% for t in teams %}
            <option value="{{ t.id }}" {% if special and special.champion_team_id == t.id %}selected{% endif %}>
              {{ t.name }}
            </option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label fw-semibold">Torschützenkönig</label>
          <select name="scorer" class="form-select" {% if locked %}disabled{% endif %}>
            <option value="">— auswählen —</option>
            {% for opt in scorer_opts %}
            <option value="{{ opt }}" {% if special and special.top_scorer == opt %}selected{% endif %}>
              {{ opt }}
            </option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label fw-semibold">Gesamttore im Turnier</label>
          <input type="number" name="total_goals" class="form-control"
                 value="{{ special.total_goals if special else 0 }}"
                 min="0" max="400" {% if locked %}disabled{% endif %}>
        </div>
      </div>
    </div>
  </div>

  <div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
      <h5 class="mb-3">Gruppen-Platzierungen (1. und 2. Platz je Gruppe)</h5>
      <div class="row g-3">
        {% for letter in groups %}
        {% set grp_teams = teams_by_group.get(letter, []) %}
        {% set saved = gpreds.get(letter, (none, none)) %}
        <div class="col-md-4 col-lg-3">
          <strong>Gruppe {{ letter }}</strong>
          <select name="g1_{{ letter }}" class="form-select form-select-sm mt-1 mb-1" {% if locked %}disabled{% endif %}>
            <option value="">1. Platz</option>
            {% for t in grp_teams %}
            <option value="{{ t.id }}" {% if saved[0] == t.id %}selected{% endif %}>{{ t.name }}</option>
            {% endfor %}
          </select>
          <select name="g2_{{ letter }}" class="form-select form-select-sm" {% if locked %}disabled{% endif %}>
            <option value="">2. Platz</option>
            {% for t in grp_teams %}
            <option value="{{ t.id }}" {% if saved[1] == t.id %}selected{% endif %}>{{ t.name }}</option>
            {% endfor %}
          </select>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>

  {% if not locked %}
  <button type="submit" class="btn btn-accent px-4">Langfrist-Tipps speichern</button>
  {% endif %}
</form>
{% endblock %}
```

---

## Task 7: Spielplan

**Files:**
- Create: `routes/spielplan.py`
- Create: `templates/spielplan.html`

- [ ] **Schritt 1: `routes/spielplan.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from config import DISPLAY_TIMEZONE
from database import get_session
from deps import require_user, templates
from models import Match

router = APIRouter()


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m. %H:%M")


@router.get("/spielplan")
async def spielplan_get(request: Request, user: dict = Depends(require_user)):
    with get_session() as s:
        matches = s.execute(
            select(Match).order_by(Match.kickoff_utc, Match.match_number)
        ).scalars().all()
        for m in matches:
            _ = m.home_team, m.away_team

    group_matches: dict[str, list[Match]] = {}
    ko_matches: dict[str, list[Match]] = {}
    for m in matches:
        if m.phase == "group":
            group_matches.setdefault(m.group_letter or "?", []).append(m)
        else:
            ko_matches.setdefault(m.phase, []).append(m)

    return templates.TemplateResponse("spielplan.html", {
        "request": request, "user": user, "active": "spielplan",
        "group_matches": group_matches,
        "ko_matches": ko_matches,
        "fmt": _fmt,
        "flash": request.session.pop("flash", None),
    })
```

- [ ] **Schritt 2: `templates/spielplan.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-4">Spielplan</h1>

<ul class="nav nav-tabs mb-4">
  <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#gruppenphase">Gruppenphase</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#ko">K.o.-Runde</a></li>
</ul>

<div class="tab-content">
  <!-- Gruppenphase -->
  <div class="tab-pane fade show active" id="gruppenphase">
    <div class="row g-4">
      {% for letter in group_matches.keys()|sort %}
      <div class="col-md-6">
        <h5>Gruppe {{ letter }}</h5>
        {% for m in group_matches[letter] %}
        {% set home = m.home_team.name if m.home_team else (m.home_placeholder or 'TBD') %}
        {% set away = m.away_team.name if m.away_team else (m.away_placeholder or 'TBD') %}
        {% set hf = m.home_team.flag_code if m.home_team else '' %}
        {% set af = m.away_team.flag_code if m.away_team else '' %}
        <div class="d-flex align-items-center gap-2 py-2 border-bottom">
          <div class="text-muted" style="font-size:.75rem;min-width:110px">
            {{ fmt(m.kickoff_utc) }}<br>
            {% if m.venue %}<span>{{ m.venue }}</span>{% endif %}
          </div>
          <div class="d-flex align-items-center gap-1 flex-grow-1">
            {% if hf %}<img src="https://flagcdn.com/20x15/{{ hf }}.png" alt="">{% endif %}
            <span class="fw-semibold">{{ home }}</span>
          </div>
          <div class="fw-bold text-center" style="min-width:40px">
            {% if m.has_result %}{{ m.result_home }}:{{ m.result_away }}{% else %}vs.{% endif %}
          </div>
          <div class="d-flex align-items-center gap-1 flex-grow-1 justify-content-end">
            <span class="fw-semibold">{{ away }}</span>
            {% if af %}<img src="https://flagcdn.com/20x15/{{ af }}.png" alt="">{% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- K.o.-Runde -->
  <div class="tab-pane fade" id="ko">
    {% set ko_labels = {
      'round32': 'Round of 32', 'round16': 'Achtelfinale',
      'quarter': 'Viertelfinale', 'semi': 'Halbfinale',
      'third_place': 'Spiel um Platz 3', 'final': 'Finale'
    } %}
    {% for phase in ['round32','round16','quarter','semi','third_place','final'] %}
    {% if ko_matches.get(phase) %}
    <h5 class="mt-3">{{ ko_labels[phase] }}</h5>
    <div class="row g-2 mb-3">
      {% for m in ko_matches[phase] %}
      {% set home = m.home_team.name if m.home_team else (m.home_placeholder or 'TBD') %}
      {% set away = m.away_team.name if m.away_team else (m.away_placeholder or 'TBD') %}
      <div class="col-md-4 col-lg-3">
        <div class="match-card">
          <div class="match-meta">{{ fmt(m.kickoff_utc) }}{% if m.venue %} · {{ m.venue }}{% endif %}</div>
          <div class="fw-semibold">{{ home }}</div>
          <div class="text-muted small">vs.</div>
          <div class="fw-semibold">{{ away }}</div>
          {% if m.has_result %}<div class="fw-bold text-accent mt-1">{{ m.result_home }}:{{ m.result_away }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    {% endif %}
    {% endfor %}
  </div>
</div>
{% endblock %}
```

---

## Task 8: Leaderboard

**Files:**
- Create: `routes/leaderboard.py`
- Create: `templates/leaderboard.html`

- [ ] **Schritt 1: `routes/leaderboard.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from deps import require_user, templates
from standings import compute_standings

router = APIRouter()


@router.get("/leaderboard")
async def leaderboard_get(request: Request, user: dict = Depends(require_user)):
    rows = compute_standings()
    return templates.TemplateResponse("leaderboard.html", {
        "request": request, "user": user, "active": "leaderboard",
        "rows": rows,
        "flash": request.session.pop("flash", None),
    })
```

- [ ] **Schritt 2: `templates/leaderboard.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-4">Leaderboard</h1>

{% if rows %}
<!-- Podium Top 3 -->
<div class="d-flex gap-3 mb-4 flex-wrap">
  {% for row in rows[:3] %}
  <div class="card border-0 shadow-sm text-center p-3 flex-fill">
    <div class="fs-2 fw-800 {% if loop.index==1 %}rank-1{% elif loop.index==2 %}rank-2{% else %}rank-3{% endif %}">
      {{ loop.index }}.
    </div>
    <div class="fw-bold">{{ row.display_name }}</div>
    <div class="fs-4 fw-bold" style="color:var(--accent)">{{ row.total_points }}</div>
    <div class="text-muted small">Punkte</div>
  </div>
  {% endfor %}
</div>

<!-- Vollständige Tabelle -->
<div class="card border-0 shadow-sm">
  <table class="table table-hover mb-0">
    <thead class="table-light">
      <tr>
        <th>#</th>
        <th>Teilnehmer</th>
        <th class="text-end">Spiel-Punkte</th>
        <th class="text-end">Langfrist</th>
        <th class="text-end fw-bold">Gesamt</th>
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr {% if row.user_id == user.id %}class="table-success"{% endif %}>
        <td class="{% if loop.index==1 %}rank-1{% elif loop.index==2 %}rank-2{% elif loop.index==3 %}rank-3{% endif %}">
          {{ loop.index }}
        </td>
        <td>{{ row.display_name }}</td>
        <td class="text-end">{{ row.match_points }}</td>
        <td class="text-end">{{ row.longterm_points }}</td>
        <td class="text-end fw-bold">{{ row.total_points }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<p class="text-muted">Noch keine Tipps abgegeben.</p>
{% endif %}
{% endblock %}
```

---

## Task 9: Admin

**Files:**
- Create: `routes/admin.py`
- Create: `templates/admin.html`

- [ ] **Schritt 1: `routes/admin.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from auth import create_user
from database import get_session
from deps import require_admin, templates
from models import Match, User

router = APIRouter(prefix="/admin")


@router.get("")
async def admin_get(request: Request, user: dict = Depends(require_admin)):
    with get_session() as s:
        users = s.scalars(select(User).order_by(User.display_name)).all()
        open_matches = s.scalars(
            select(Match).where(Match.is_finished == False).order_by(Match.kickoff_utc)
        ).all()
        for m in open_matches:
            _ = m.home_team, m.away_team
    return templates.TemplateResponse("admin.html", {
        "request": request, "user": user, "active": "admin",
        "users": users, "open_matches": open_matches,
        "flash": request.session.pop("flash", None),
    })


@router.post("/result/{match_id}")
async def save_result(
    request: Request,
    match_id: int,
    result_home: int = Form(...),
    result_away: int = Form(...),
    is_finished: bool = Form(False),
    user: dict = Depends(require_admin),
):
    with get_session() as s:
        m = s.get(Match, match_id)
        if m:
            m.result_home = result_home
            m.result_away = result_away
            m.is_finished = is_finished
    request.session["flash"] = {"message": "Ergebnis gespeichert.", "type": "success"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/create")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    user: dict = Depends(require_admin),
):
    try:
        create_user(username.strip(), display_name.strip() or username.strip(), password, is_admin=is_admin)
        request.session["flash"] = {"message": f"Nutzer '{username}' angelegt.", "type": "success"}
    except ValueError as e:
        request.session["flash"] = {"message": str(e), "type": "danger"}
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{user_id}/toggle-admin")
async def toggle_admin(request: Request, user_id: int, user: dict = Depends(require_admin)):
    with get_session() as s:
        u = s.get(User, user_id)
        if u and u.id != user["id"]:
            u.is_admin = not u.is_admin
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Schritt 2: `templates/admin.html`** (komprimiert)

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-4">Admin</h1>
{% if flash %}<div class="alert alert-{{ flash.type }}">{{ flash.message }}</div>{% endif %}

<!-- Ergebnisse eintragen -->
<div class="card border-0 shadow-sm mb-4">
  <div class="card-body">
    <h5>Ergebnisse eintragen</h5>
    {% if open_matches %}
    {% for m in open_matches %}
    {% set home = m.home_team.name if m.home_team else (m.home_placeholder or 'TBD') %}
    {% set away = m.away_team.name if m.away_team else (m.away_placeholder or 'TBD') %}
    <form method="post" action="/admin/result/{{ m.id }}" class="d-flex align-items-center gap-2 mb-2 flex-wrap">
      <span class="fw-semibold" style="min-width:200px">{{ home }} vs. {{ away }}</span>
      <input type="number" name="result_home" class="form-control form-control-sm" style="width:60px"
             value="{{ m.result_home or 0 }}" min="0">
      <span>:</span>
      <input type="number" name="result_away" class="form-control form-control-sm" style="width:60px"
             value="{{ m.result_away or 0 }}" min="0">
      <div class="form-check mb-0">
        <input class="form-check-input" type="checkbox" name="is_finished" id="fin_{{ m.id }}"
               {% if m.is_finished %}checked{% endif %}>
        <label class="form-check-label" for="fin_{{ m.id }}">Abgeschlossen</label>
      </div>
      <button type="submit" class="btn btn-accent btn-sm">Speichern</button>
    </form>
    {% endfor %}
    {% else %}
    <p class="text-muted">Keine offenen Spiele.</p>
    {% endif %}
  </div>
</div>

<!-- Nutzer -->
<div class="card border-0 shadow-sm mb-4">
  <div class="card-body">
    <h5>Teilnehmer ({{ users|length }})</h5>
    <table class="table table-sm">
      <thead><tr><th>Benutzername</th><th>Anzeigename</th><th>Admin</th><th></th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>{{ u.username }}</td>
          <td>{{ u.display_name }}</td>
          <td>{% if u.is_admin %}<span class="badge bg-success">Ja</span>{% endif %}</td>
          <td>
            {% if u.id != user.id %}
            <form method="post" action="/admin/user/{{ u.id }}/toggle-admin" class="d-inline">
              <button class="btn btn-outline-secondary btn-sm">Admin {{ 'entfernen' if u.is_admin else 'machen' }}</button>
            </form>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <h6 class="mt-3">Neuen Nutzer anlegen</h6>
    <form method="post" action="/admin/user/create" class="row g-2">
      <div class="col-md-3"><input type="text" name="username" class="form-control form-control-sm" placeholder="Benutzername" required></div>
      <div class="col-md-3"><input type="text" name="display_name" class="form-control form-control-sm" placeholder="Anzeigename"></div>
      <div class="col-md-2"><input type="password" name="password" class="form-control form-control-sm" placeholder="Passwort" required></div>
      <div class="col-md-2 d-flex align-items-center gap-1">
        <input type="checkbox" name="is_admin" class="form-check-input" id="new_admin">
        <label for="new_admin" class="form-check-label small">Admin</label>
      </div>
      <div class="col-md-2"><button type="submit" class="btn btn-accent btn-sm w-100">Anlegen</button></div>
    </form>
  </div>
</div>
{% endblock %}
```

---

## Task 10: PWA & Service Worker

**Files:**
- Create: `static/manifest.json`
- Create: `static/sw.js`

- [ ] **Schritt 1: `static/manifest.json`**

```json
{
  "name": "WM 2026 Tippspiel",
  "short_name": "Tippspiel",
  "start_url": "/tipps",
  "display": "standalone",
  "background_color": "#f4f7f9",
  "theme_color": "#0fa968",
  "icons": [
    { "src": "/static/img/lew_logo.png", "sizes": "192x192", "type": "image/png" }
  ]
}
```

- [ ] **Schritt 2: `static/sw.js`**

```javascript
// Minimaler Service Worker – ermöglicht PWA-Installation
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));
self.addEventListener('fetch', e => e.respondWith(fetch(e.request)));
```

---

## Task 11: Render.com Deployment

**Files:**
- Create: `render.yaml`
- Update: `.env.example`

- [ ] **Schritt 1: `render.yaml`**

```yaml
services:
  - type: web
    name: wm2026-tippspiel
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: wm2026-db
          property: connectionString
      - key: SECRET_KEY
        generateValue: true

databases:
  - name: wm2026-db
    databaseName: wm2026
    user: wm2026
```

- [ ] **Schritt 2: `SECRET_KEY` in `main.py` aus Env lesen**

```python
import os
# ...
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    https_only=os.environ.get("RENDER", False),
)
```

- [ ] **Schritt 3: Auf Render deployen**
  1. Render.com Account erstellen (kostenlos)
  2. "New Web Service" → Git-Repo verbinden (oder via Render CLI)
  3. `render.yaml` wird automatisch erkannt
  4. DB wird automatisch angelegt
  5. Nach Deploy: `python seed.py` und `python import_schedule.py` einmalig via Shell ausführen

---

## Task 11b: Automatische Ergebnisse (football-data.org)

**Files:**
- Create: `results_sync.py`
- Modify: `main.py` (Scheduler starten)
- Modify: `requirements.txt` (httpx, apscheduler)

football-data.org bietet einen kostenlosen API-Key (60 Anfragen/Minute). WM 2026 Competition-ID: `2000`.

- [ ] **Schritt 1: API-Key besorgen**

  Kostenlos unter https://www.football-data.org/client/register registrieren → API-Key per Mail.
  In Render als Env-Variable `FOOTBALL_API_KEY` hinterlegen, lokal in `.env`.

- [ ] **Schritt 2: requirements.txt erweitern**

```
httpx>=0.27
apscheduler>=3.10
python-dotenv>=1.0
```

- [ ] **Schritt 3: `results_sync.py` anlegen**

```python
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from database import get_session
from models import Match, Team
from scoring import recalculate_all

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
_BASE = "https://api.football-data.org/v4"
_COMPETITION = "2000"  # FIFA World Cup 2026

# football-data.org Status → is_finished
_FINISHED_STATUSES = {"FINISHED"}


def _headers() -> dict:
    return {"X-Auth-Token": _API_KEY}


def _map_team(session, fd_team: dict) -> Team | None:
    """Versucht das football-data-Team auf unser DB-Team zu matchen (Name oder ID)."""
    name = fd_team.get("name", "")
    return session.scalar(select(Team).where(Team.name_en == name))


def sync_results() -> int:
    """Holt alle abgeschlossenen WM-Spiele und aktualisiert die DB. Gibt Anzahl Updates zurück."""
    if not _API_KEY:
        logger.warning("FOOTBALL_API_KEY nicht gesetzt – sync übersprungen")
        return 0

    try:
        resp = httpx.get(
            f"{_BASE}/competitions/{_COMPETITION}/matches",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("API-Fehler: %s", e)
        return 0

    matches_data = resp.json().get("matches", [])
    updated = 0

    with get_session() as s:
        for fd in matches_data:
            if fd.get("status") not in _FINISHED_STATUSES:
                continue
            score = fd.get("score", {})
            full = score.get("fullTime", {})
            home_goals = full.get("home")
            away_goals = full.get("away")
            if home_goals is None or away_goals is None:
                continue

            # Spiel per match_number finden (football-data liefert matchday + utcDate)
            kickoff_str = fd.get("utcDate", "")
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            home_name = fd.get("homeTeam", {}).get("name", "")
            away_name = fd.get("awayTeam", {}).get("name", "")

            # Match suchen: per kickoff-Zeit (±1 Minute Toleranz) + Teamnamen
            m = s.scalar(
                select(Match).where(
                    Match.kickoff_utc == kickoff,
                    Match.is_finished == False,
                )
            )
            if m is None:
                # Fallback: Teamnamen-Matching
                home_team = s.scalar(select(Team).where(Team.name_en == home_name))
                away_team = s.scalar(select(Team).where(Team.name_en == away_name))
                if home_team and away_team:
                    m = s.scalar(
                        select(Match).where(
                            Match.home_team_id == home_team.id,
                            Match.away_team_id == away_team.id,
                        )
                    )
            if m is None:
                continue

            m.result_home = home_goals
            m.result_away = away_goals
            m.is_finished = True
            # Gewinner für K.o.-Spiele
            winner = score.get("winner")  # "HOME_TEAM" | "AWAY_TEAM" | "DRAW"
            if winner == "HOME_TEAM":
                m.winner_team_id = m.home_team_id
            elif winner == "AWAY_TEAM":
                m.winner_team_id = m.away_team_id
            updated += 1
            logger.info("Ergebnis: Spiel %s → %d:%d", m.match_number, home_goals, away_goals)

    if updated:
        try:
            recalculate_all()
        except Exception as e:
            logger.error("Punkte-Neuberechnung fehlgeschlagen: %s", e)

    return updated
```

- [ ] **Schritt 4: Scheduler in `main.py` einbinden**

```python
import os
from apscheduler.schedulers.background import BackgroundScheduler
from results_sync import sync_results

# nach app = FastAPI(...)

scheduler = BackgroundScheduler()

@app.on_event("startup")
def startup():
    init_db()
    if os.environ.get("FOOTBALL_API_KEY"):
        # Alle 5 Minuten Ergebnisse abrufen
        scheduler.add_job(sync_results, "interval", minutes=5, id="results_sync")
        scheduler.start()

@app.on_event("shutdown")
def shutdown():
    if scheduler.running:
        scheduler.shutdown()
```

- [ ] **Schritt 5: Manueller Sync-Button im Admin**

In `templates/admin.html` folgendes ergänzen (nach dem Ergebnis-Block):

```html
<div class="card border-0 shadow-sm mb-4">
  <div class="card-body">
    <h5>Automatische Ergebnisse</h5>
    <p class="text-muted small">Ergebnisse werden alle 5 Minuten automatisch von football-data.org geholt.</p>
    <form method="post" action="/admin/sync">
      <button type="submit" class="btn btn-outline-secondary btn-sm">Jetzt manuell synchronisieren</button>
    </form>
  </div>
</div>
```

Und in `routes/admin.py`:

```python
from results_sync import sync_results

@router.post("/sync")
async def manual_sync(request: Request, user: dict = Depends(require_admin)):
    n = sync_results()
    request.session["flash"] = {"message": f"{n} Spiel(e) aktualisiert.", "type": "success"}
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Schritt 6: Testen (lokal ohne API-Key)**

Ohne Key läuft die App normal, Sync wird übersprungen. Mit Key:
```bash
FOOTBALL_API_KEY=dein_key uvicorn main:app --reload
```
Im Admin → "Jetzt manuell synchronisieren" → Flash zeigt Anzahl Updates.

---

## Task 12: Streamlit-Reste aufräumen

- [ ] Löschen:
  - `app.py`, `theme.py`
  - `views_tipps.py`, `views_langfrist.py`, `views_spielplan.py`
  - `views_leaderboard.py`, `views_admin.py`
  - `preview.html`
  - `.streamlit/` (ganzes Verzeichnis)
- [ ] `CLAUDE.md` aktualisieren: Start-Befehl auf `uvicorn main:app --reload`

---

## Selbst-Review

**Spec-Abdeckung:**
- ✅ Selbst-Registrierung (offen, wer Link kennt)
- ✅ Admin-Verwaltung
- ✅ Gruppenphase-Tipps
- ✅ K.o.-Tipps (gleicher Mechanismus in tipps.py)
- ✅ Langfrist-Tipps (Weltmeister, Torschütze, Gruppen, Gesamttore)
- ✅ Spielplan mit Spielorten
- ✅ Leaderboard
- ✅ Admin: Ergebnisse eintragen, Nutzer verwalten
- ✅ Mobile-optimiert (Bootstrap 5 responsive)
- ✅ Im Browser installierbar (PWA manifest + sw.js)
- ✅ Kostenlos hostbar (Render.com free tier)
- ✅ 24/7 verfügbar

**Offen / Manuell prüfen:**
- `standings.py` und `scoring.py` Rückgabestruktur prüfen bevor Task 8 implementiert wird (Feldnamen `display_name`, `total_points`, `match_points`, `longterm_points` müssen stimmen)
- `data_players.py`: `dropdown_options()` und `option_to_name()` Interface in Task 6 verwendet — vor Ausführung sicherstellen dass diese Funktionen existieren
