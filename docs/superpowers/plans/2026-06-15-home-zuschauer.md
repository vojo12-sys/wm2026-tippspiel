# Home-Seite + Zuschauer-Modus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Neue `/home` Dashboard-Seite als Einstiegspunkt nach Login + individuelle Zuschauer-Accounts mit eingeschränkter Navigation.

**Architecture:** `is_spectator` Boolean in der User-Tabelle, wird beim Login in die Session geschrieben. `base.html` blendet Navigation situativ aus. `require_non_spectator` Dependency schützt gesperrte Routes. Die neue `/home` Route ersetzt `/tipps` als Login-Ziel.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Bootstrap 5, SQLite (lokal) / PostgreSQL (Render)

---

## Dateien-Übersicht

| Datei | Aktion |
|---|---|
| `models.py` | `is_spectator` Spalte zu `User` hinzufügen |
| `auth.py` | `create_user` akzeptiert `is_spectator` Parameter |
| `routes/auth.py` | Login-Redirect → `/home`; `is_spectator` in Session |
| `templates/register.html` | Zuschauer-Checkbox |
| `routes/home.py` | **NEU** – Dashboard-Route |
| `templates/home.html` | **NEU** – Dashboard-Template |
| `main.py` | Home-Router registrieren |
| `templates/base.html` | Navigation + Topf-Widget für Zuschauer einschränken |
| `deps.py` | `require_non_spectator` Funktion |
| `routes/tipps.py` | `require_non_spectator` statt `require_user` |
| `routes/langfrist.py` | `require_non_spectator` statt `require_user` |
| `routes/uebersicht.py` | `require_non_spectator` statt `require_user` |
| `routes/stats.py` | `require_non_spectator` statt `require_user` |
| `routes/profil.py` | `require_non_spectator` statt `require_user` |
| `templates/leaderboard.html` | Kassen-Details für Zuschauer ausblenden |
| `routes/admin.py` | `POST /admin/user/{id}/toggle-spectator` Route |
| `templates/admin.html` | „Zuschauer"-Toggle-Button pro User (neben Passwort-Button) |

**Zuschauer dürfen sehen:** Home, Spielplan, Leaderboard (ohne Kasse), Tipp-Übersicht, Teams & Spielorte, News, Spielregeln, Torschützen

**Zuschauer dürfen NICHT sehen:** Tipps, Bonus Tipps, Meine Statistik, Profil, Admin

> **Update 2026-06-16:** Tipp-Übersicht wurde nachträglich für Zuschauer freigegeben (`routes/uebersicht.py` nutzt jetzt `require_user` statt `require_non_spectator`; Nav-Link in `base.html` nicht mehr eingeschränkt).

---

## Task 1: DB-Schema – `is_spectator` Spalte

**Files:**
- Modify: `models.py`

- [ ] **Schritt 1: `is_spectator` Feld zu User-Model hinzufügen**

In `models.py`, nach der Zeile mit `is_admin` (ca. Zeile 46) einfügen:

```python
is_spectator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
```

- [ ] **Schritt 2: ALTER TABLE für bestehende DB ausführen**

Da die DB bereits existiert, muss die Spalte manuell hinzugefügt werden. Im Projekt-Ordner ausführen:

```bash
# SQLite (lokal)
python -c "
from database import engine
with engine.connect() as conn:
    conn.execute(__import__('sqlalchemy').text('ALTER TABLE users ADD COLUMN is_spectator BOOLEAN NOT NULL DEFAULT 0'))
    conn.commit()
print('OK')
"
```

Erwartete Ausgabe: `OK`

Für die Remote-DB (Render PostgreSQL) analog mit gesetzter `DATABASE_URL` Umgebungsvariable ausführen.

- [ ] **Schritt 3: Verifizieren**

```bash
python -c "
from database import get_session
from models import User
from sqlalchemy import select
with get_session() as s:
    u = s.scalar(select(User).limit(1))
    print('is_spectator:', u.is_spectator if u else 'kein User')
"
```

Erwartete Ausgabe: `is_spectator: False`

---

## Task 2: Auth – `is_spectator` in Session + Login-Redirect zu `/home`

**Files:**
- Modify: `auth.py`
- Modify: `routes/auth.py`

- [ ] **Schritt 1: `create_user` in `auth.py` erweitern**

Signatur von `create_user` (ca. Zeile 43) ändern:

```python
def create_user(username: str, display_name: str, password: str,
                *, is_admin: bool = False, is_spectator: bool = False) -> int:
    """Legt einen Teilnehmer an und gibt dessen ID zurück."""
    with get_session() as s:
        if s.scalar(select(User).where(User.username == username)):
            raise ValueError(f"Benutzername '{username}' existiert bereits.")
        u = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_spectator=is_spectator,
        )
        s.add(u)
        s.flush()
        return u.id
```

- [ ] **Schritt 2: Login-Session in `routes/auth.py` erweitern**

In `login_post` (ca. Zeile 131) das Session-Dict um `is_spectator` erweitern:

```python
request.session["user"] = {
    "id": u.id,
    "display_name": u.display_name,
    "is_admin": u.is_admin,
    "is_spectator": u.is_spectator,
}
```

- [ ] **Schritt 3: Login-Redirect auf `/home` ändern**

In `login_post` (ca. Zeile 136) den Redirect ändern:

```python
return RedirectResponse("/home", status_code=303)
```

Außerdem in `login_get` und `register_get` (je ca. Zeile 108/143) den bestehenden Redirect von `/tipps` auf `/home` ändern (für bereits eingeloggte User):

```python
# login_get, Zeile ~108:
return RedirectResponse("/home", status_code=302)

# register_get, Zeile ~143:
return RedirectResponse("/home", status_code=302)
```

---

## Task 3: Registrierung – Zuschauer-Checkbox

**Files:**
- Modify: `templates/register.html`
- Modify: `routes/auth.py`

- [ ] **Schritt 1: Checkbox in `register.html` einfügen**

Direkt vor dem `<button type="submit"...>` (ca. Zeile 37) einfügen:

```html
<div class="mb-4">
  <div class="form-check">
    <input class="form-check-input" type="checkbox" name="is_spectator" id="isSpectator" value="1">
    <label class="form-check-label" for="isSpectator">
      Ich möchte nur zuschauen <span class="text-muted small">(keine Tipp-Teilnahme)</span>
    </label>
  </div>
</div>
```

- [ ] **Schritt 2: `register_post` in `routes/auth.py` erweitern**

Funktionssignatur erweitern (Checkbox-Wert kommt als `"1"` oder fehlt):

```python
@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    is_spectator: str = Form(default=""),
):
```

Im Body von `register_post` beim `create_user`-Aufruf:

```python
    try:
        create_user(
            username.strip(),
            display_name.strip() or username.strip(),
            password,
            is_spectator=bool(is_spectator),
        )
    except ValueError as e:
```

---

## Task 4: Home-Route + Template

**Files:**
- Create: `routes/home.py`
- Create: `templates/home.html`
- Modify: `main.py`

- [ ] **Schritt 1: `routes/home.py` erstellen**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import Match, Prediction
from standings import compute_standings

router = APIRouter()

_MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


@router.get("/home")
async def home_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    from config import DISPLAY_TIMEZONE
    from results_sync import get_live_scores

    now = datetime.now(timezone.utc)
    lock_threshold = now + timedelta(minutes=10)

    with get_session() as s:
        # Nächste 5 Spiele
        upcoming_raw = list(s.scalars(
            select(Match)
            .where(Match.kickoff_utc > now, Match.is_finished == False)
            .order_by(Match.kickoff_utc)
            .limit(5)
        ).all())
        for m in upcoming_raw:
            _ = m.home_team, m.away_team  # Eager-load Relationships

        # Offene Tipps (nur für Nicht-Zuschauer)
        open_tips = 0
        if not user.get("is_spectator"):
            open_match_ids = [
                m.id for m in upcoming_raw
                if m.kickoff_utc.replace(tzinfo=timezone.utc) > lock_threshold
            ]
            if open_match_ids:
                tipped_ids = set(
                    row[0] for row in s.execute(
                        select(Prediction.match_id)
                        .where(
                            Prediction.user_id == user["id"],
                            Prediction.match_id.in_(open_match_ids),
                        )
                    ).all()
                )
                open_tips = len(open_match_ids) - len(tipped_ids)

    # Leaderboard Top 5
    standings = compute_standings()
    top5 = standings[:5]
    user_rank = None
    user_points = 0
    for r in standings:
        if r.user_id == user["id"]:
            user_rank = r.rank
            user_points = r.total_points
            break

    # Live-Scores
    live = get_live_scores()

    # Spiele aufbereiten
    upcoming = []
    for m in upcoming_raw:
        koff = m.kickoff_utc
        if koff.tzinfo is None:
            koff = koff.replace(tzinfo=timezone.utc)
        local_dt = koff.astimezone(DISPLAY_TIMEZONE)
        home = m.home_team.name if m.home_team else (m.home_placeholder or "TBD")
        away = m.away_team.name if m.away_team else (m.away_placeholder or "TBD")
        home_flag = m.home_team.flag_code if m.home_team else None
        away_flag = m.away_team.flag_code if m.away_team else None
        upcoming.append({
            "id": m.id,
            "home": home,
            "away": away,
            "home_flag": home_flag,
            "away_flag": away_flag,
            "date_de": f"{local_dt.day}. {_MONTHS_DE[local_dt.month - 1]}",
            "time_de": local_dt.strftime("%H:%M"),
            "kickoff_iso": koff.isoformat(),
            "live": live.get(str(m.id)),
        })

    return templates.TemplateResponse(request, "home.html", {
        "user": user,
        "active": "home",
        "upcoming": upcoming,
        "top5": top5,
        "user_rank": user_rank,
        "user_points": user_points,
        "open_tips": open_tips,
        "flash": request.session.pop("flash", None),
    })
```

- [ ] **Schritt 2: `templates/home.html` erstellen**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-1" style="font-family:'Bricolage Grotesque',sans-serif;font-weight:800">
  Willkommen, {{ user.display_name }}!
</h1>
{% if user.is_spectator %}
<p class="text-muted mb-4 small">Du schaust als Gast zu – viel Spaß beim Mitfiebern!</p>
{% else %}
<p class="text-muted mb-4 small">WM 2026 · Kanada · Mexiko · USA</p>
{% endif %}

<!-- ── Hero: Nächstes / Live-Spiel ─────────────────────────────── -->
{% if upcoming %}
{% set hero = upcoming[0] %}
<div class="card border-0 shadow-sm mb-4">
  <div class="card-body p-3 p-md-4">
    {% if hero.live %}
    <div class="d-flex align-items-center gap-2 mb-2">
      <span class="badge" style="background:#dc3545;animation:livepulse 1.2s infinite">● LIVE
        {% if hero.live.status == 'PAUSED' %}HZ{% elif hero.live.minute %} {{ hero.live.minute }}'{% endif %}
      </span>
      <span class="text-muted small">Laufendes Spiel</span>
    </div>
    <div class="d-flex align-items-center justify-content-center gap-3 py-2">
      <div class="text-center fw-bold" style="min-width:80px">
        {% if hero.home_flag %}<span class="fi fi-{{ hero.home_flag }} me-1"></span>{% endif %}
        {{ hero.home }}
      </div>
      <div class="text-center fw-bold" style="font-size:1.6rem;min-width:70px;font-family:'Bricolage Grotesque',sans-serif">
        {{ hero.live.home }}:{{ hero.live.away }}
      </div>
      <div class="text-center fw-bold" style="min-width:80px">
        {% if hero.away_flag %}<span class="fi fi-{{ hero.away_flag }} me-1"></span>{% endif %}
        {{ hero.away }}
      </div>
    </div>
    {% else %}
    <div class="text-muted small mb-2">Nächstes Spiel</div>
    <div class="d-flex align-items-center justify-content-center gap-3 py-2">
      <div class="text-center fw-bold" style="min-width:80px">
        {% if hero.home_flag %}<span class="fi fi-{{ hero.home_flag }} me-1"></span>{% endif %}
        {{ hero.home }}
      </div>
      <div class="text-center" style="min-width:70px">
        <div class="fw-bold" style="font-size:1.1rem">{{ hero.time_de }} Uhr</div>
        <div class="text-muted small">{{ hero.date_de }}</div>
      </div>
      <div class="text-center fw-bold" style="min-width:80px">
        {% if hero.away_flag %}<span class="fi fi-{{ hero.away_flag }} me-1"></span>{% endif %}
        {{ hero.away }}
      </div>
    </div>
    <div class="text-center mt-2">
      <span id="hero-countdown" class="badge bg-light text-dark border small" data-kickoff="{{ hero.kickoff_iso }}"></span>
    </div>
    {% endif %}
  </div>
</div>
{% endif %}

<!-- ── Persönliche Stats (nur Teilnehmer) ───────────────────────── -->
{% if not user.is_spectator %}
<div class="row g-3 mb-4">
  <div class="col-4">
    <div class="card border-0 shadow-sm text-center p-3">
      <div class="text-muted small">Rang</div>
      <div class="fw-bold" style="font-size:1.6rem;font-family:'Bricolage Grotesque',sans-serif;color:#1E4E8C">
        {% if user_rank %}{{ user_rank }}.{% else %}–{% endif %}
      </div>
    </div>
  </div>
  <div class="col-4">
    <div class="card border-0 shadow-sm text-center p-3">
      <div class="text-muted small">Punkte</div>
      <div class="fw-bold" style="font-size:1.6rem;font-family:'Bricolage Grotesque',sans-serif;color:#1E4E8C">
        {{ user_points }}
      </div>
    </div>
  </div>
  <div class="col-4">
    <a href="/tipps" class="text-decoration-none">
      <div class="card border-0 shadow-sm text-center p-3 {% if open_tips > 0 %}border-warning{% endif %}" style="{% if open_tips > 0 %}border:1px solid #ffc107!important{% endif %}">
        <div class="text-muted small">Offene Tipps</div>
        <div class="fw-bold" style="font-size:1.6rem;font-family:'Bricolage Grotesque',sans-serif;color:{% if open_tips > 0 %}#c08a12{% else %}#1E4E8C{% endif %}">
          {{ open_tips }}
        </div>
      </div>
    </a>
  </div>
</div>
{% endif %}

<!-- ── Leaderboard Top 5 ─────────────────────────────────────────── -->
{% if top5 %}
<div class="card border-0 shadow-sm mb-4">
  <div class="card-header border-0 bg-transparent d-flex justify-content-between align-items-center pt-3">
    <span class="fw-bold" style="font-family:'Bricolage Grotesque',sans-serif"><i class="bi bi-bar-chart me-2" style="color:var(--accent-dk)"></i>Leaderboard – Top 5</span>
    <a href="/leaderboard" class="small text-muted">Alle anzeigen →</a>
  </div>
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <tbody>
        {% for row in top5 %}
        <tr {% if row.user_id == user.id %}class="table-success"{% endif %}>
          <td class="ps-3" style="width:36px">
            {% if row.rank == 1 %}<span class="rank-1 fw-bold">1.</span>
            {% elif row.rank == 2 %}<span class="rank-2 fw-bold">2.</span>
            {% elif row.rank == 3 %}<span class="rank-3 fw-bold">3.</span>
            {% else %}<span class="text-muted">{{ row.rank }}.</span>{% endif %}
          </td>
          <td>{{ row.display_name }}{% if row.user_id == user.id %} <span class="badge" style="background:var(--accent);font-size:.6rem">Du</span>{% endif %}</td>
          <td class="text-end pe-3 fw-bold" style="color:#1E4E8C">{{ row.total_points }} Pkt</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}

<!-- ── Nächste Spiele ────────────────────────────────────────────── -->
{% set rest = upcoming[1:] %}
{% if rest %}
<div class="card border-0 shadow-sm mb-4">
  <div class="card-header border-0 bg-transparent pt-3">
    <span class="fw-bold" style="font-family:'Bricolage Grotesque',sans-serif"><i class="bi bi-calendar3 me-2" style="color:var(--accent-dk)"></i>Nächste Spiele</span>
  </div>
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <tbody>
        {% for m in rest %}
        <tr>
          <td class="ps-3 text-muted small" style="width:110px">{{ m.date_de }}<br>{{ m.time_de }} Uhr</td>
          <td>
            {% if m.home_flag %}<span class="fi fi-{{ m.home_flag }}"></span> {% endif %}{{ m.home }}
          </td>
          <td class="text-muted small text-center" style="width:30px">–</td>
          <td>
            {% if m.away_flag %}<span class="fi fi-{{ m.away_flag }}"></span> {% endif %}{{ m.away }}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}

<!-- ── Schnellzugriff ────────────────────────────────────────────── -->
<div class="mb-4">
  <div class="fw-bold mb-2" style="font-family:'Bricolage Grotesque',sans-serif"><i class="bi bi-grid me-2" style="color:var(--accent-dk)"></i>Schnellzugriff</div>
  <div class="row g-2">
    {% if not user.is_spectator %}
    <div class="col-6 col-md-3">
      <a href="/tipps" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-pencil-square me-2"></i>Tipps abgeben
      </a>
    </div>
    <div class="col-6 col-md-3">
      <a href="/langfrist" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-trophy me-2"></i>Bonus Tipps
      </a>
    </div>
    <div class="col-6 col-md-3">
      <a href="/stats" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-graph-up me-2"></i>Statistik
      </a>
    </div>
    {% endif %}
    <div class="col-6 col-md-3">
      <a href="/spielplan" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-calendar3 me-2"></i>Spielplan
      </a>
    </div>
    <div class="col-6 col-md-3">
      <a href="/teams" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-globe me-2"></i>Teams & Spielorte
      </a>
    </div>
    <div class="col-6 col-md-3">
      <a href="/torschuetzen" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-person-badge me-2"></i>Torschützen
      </a>
    </div>
    <div class="col-6 col-md-3">
      <a href="/regeln" class="btn btn-outline-secondary w-100 text-start">
        <i class="bi bi-info-circle me-2"></i>Spielregeln
      </a>
    </div>
  </div>
</div>

<!-- ── Spieltagesberichte (Platzhalter) ─────────────────────────── -->
<div class="card border-0 shadow-sm" style="border:1px solid rgba(126,200,227,.3)!important">
  <div class="card-body p-3 d-flex align-items-center gap-3">
    <i class="bi bi-newspaper" style="font-size:1.6rem;color:var(--accent-dk)"></i>
    <div>
      <div class="fw-bold">Spieltagesberichte <span class="badge" style="background:var(--accent);font-size:.65rem;vertical-align:middle">Demnächst</span></div>
      <div class="text-muted small">Zusammenfassungen der Spieltage mit Tipper-Analyse – bald verfügbar.</div>
    </div>
  </div>
</div>

<style>
@keyframes livepulse { 0%,100%{opacity:1} 50%{opacity:.4} }
</style>

<script>
// Countdown für nächstes Spiel
(function() {
  const el = document.getElementById('hero-countdown');
  if (!el) return;
  const target = new Date(el.dataset.kickoff);
  function update() {
    const diff = target - new Date();
    if (diff <= 0) { el.textContent = 'Gleich geht es los!'; return; }
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    if (h > 48) {
      const d = Math.floor(h / 24);
      el.textContent = 'in ' + d + ' Tag' + (d > 1 ? 'en' : '');
    } else if (h > 0) {
      el.textContent = 'in ' + h + 'h ' + m + 'min';
    } else {
      el.textContent = 'in ' + m + ' Minuten';
    }
    setTimeout(update, 30000);
  }
  update();
})();
</script>
{% endblock %}
```

- [ ] **Schritt 3: Home-Router in `main.py` registrieren**

In `main.py` nach den bestehenden Importen (Zeile ~62 wo andere Router eingebunden werden) einfügen. Zuerst den Import ganz oben:

```python
from routes import home
```

Dann beim Router-Registrieren (nach `app.include_router(auth.router)`):

```python
app.include_router(home.router)
```

- [ ] **Schritt 4: Testen**

App starten: `python -m uvicorn main:app --reload --port 8080`

- Browser → `http://localhost:8080/login` → einloggen → landet auf `/home` ✓
- Alle 4 Sektionen sichtbar (Hero, Stats, Leaderboard, Nächste Spiele) ✓
- Countdown läuft ✓

---

## Task 5: Navigation für Zuschauer einschränken (`base.html`)

**Files:**
- Modify: `templates/base.html`

- [ ] **Schritt 1: Eingeschränkte Nav-Links in Sidebar (Desktop) und Offcanvas (Mobile)**

In `base.html` gibt es **zwei Nav-Blöcke** (Sidebar Desktop ca. Zeile 119 und Offcanvas Mobile ca. Zeile 49). In **beiden** Blöcken folgende Links mit `{% if not user.is_spectator %}...{% endif %}` einwickeln:

- „Tipps abgeben" (`/tipps`)
- „Bonus Tipps" (`/langfrist`)
- „Tipp-Übersicht" (`/uebersicht`)
- „Meine Statistik" (`/stats`)

Beispiel für einen einzuwickelnden Block (beide Nav-Blöcke identisch anpassen):

```html
<!-- Vor der Nav: Home-Link für alle hinzufügen -->
<a href="/home" class="nav-link {% if active == 'home' %}active{% endif %}">
  <i class="bi bi-house me-2"></i>Home
</a>

{% if not user.is_spectator %}
<a href="/tipps" class="nav-link {% if active == 'tipps' %}active{% endif %}">
  <i class="bi bi-pencil-square me-2"></i>Tipps abgeben
</a>
<a href="/langfrist" class="nav-link {% if active == 'langfrist' %}active{% endif %} {% if user and get_bonus_tips_incomplete(user.id) %}nav-glow-gold{% endif %}">
  <i class="bi bi-trophy me-2"></i>Bonus Tipps
</a>
{% endif %}
<a href="/spielplan" class="nav-link {% if active == 'spielplan' %}active{% endif %}">
  <i class="bi bi-calendar3 me-2"></i>Spielplan
</a>
<a href="/leaderboard" class="nav-link {% if active == 'leaderboard' %}active{% endif %}">
  <i class="bi bi-bar-chart me-2"></i>Leaderboard
</a>
{% if not user.is_spectator %}
<a href="/uebersicht" class="nav-link {% if active == 'uebersicht' %}active{% endif %}">
  <i class="bi bi-table me-2"></i>Tipp-Übersicht
</a>
{% endif %}
<a href="/torschuetzen" class="nav-link {% if active == 'torschuetzen' %}active{% endif %}">
  <i class="bi bi-person-badge me-2"></i>Torschützen
</a>
{% if not user.is_spectator %}
<a href="/stats" class="nav-link {% if active == 'stats' %}active{% endif %}">
  <i class="bi bi-graph-up me-2"></i>Meine Statistik
</a>
{% endif %}
<a href="/teams" class="nav-link {% if active == 'teams' %}active{% endif %}">
  <i class="bi bi-globe me-2"></i>Teams & Spielorte
</a>
<a href="https://www.sportschau.de/fussball/fifa-wm-2026" target="_blank" rel="noopener" class="nav-link">
  <i class="bi bi-newspaper me-2"></i>News
</a>
<a href="/regeln" class="nav-link {% if active == 'regeln' %}active{% endif %}">
  <i class="bi bi-info-circle me-2"></i>Spielregeln
</a>
{% if user.is_admin %}
<a href="/admin" class="nav-link {% if active == 'admin' %}active{% endif %}">
  <i class="bi bi-gear me-2"></i>Admin
</a>
{% endif %}
```

- [ ] **Schritt 2: Topf-Widget für Zuschauer ausblenden**

Das Topf-Widget (in **beiden** Nav-Blöcken) mit Spectator-Check einwickeln. Die Bedingung `{% if _pot.enabled %}` erweitern:

```html
{% if _pot.enabled and not user.is_spectator %}
```

- [ ] **Schritt 3: Profil-Link für Zuschauer ausblenden**

Den Profil-Button im „Angemeldet als"-Bereich (ebenfalls in beiden Nav-Blöcken) für Zuschauer ausblenden:

```html
<div class="d-flex gap-2">
  {% if not user.is_spectator %}
  <a href="/profil" class="btn btn-outline-secondary btn-sm">Profil</a>
  {% endif %}
  <a href="/logout" class="btn btn-accent btn-sm">Abmelden</a>
</div>
```

- [ ] **Schritt 4: Testen**

- Als normaler Teilnehmer einloggen → alle Nav-Links sichtbar ✓
- Als Zuschauer einloggen → nur erlaubte Links sichtbar, kein Topf-Widget ✓

---

## Task 6: Route-Schutz – `require_non_spectator`

**Files:**
- Modify: `deps.py`
- Modify: `routes/tipps.py`, `routes/langfrist.py`, `routes/uebersicht.py`, `routes/stats.py`, `routes/profil.py`

- [ ] **Schritt 1: `require_non_spectator` in `deps.py` hinzufügen**

Am Ende von `deps.py` (nach `require_admin`) einfügen:

```python
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
```

- [ ] **Schritt 2: `routes/tipps.py` absichern**

Import ändern:
```python
from deps import require_non_spectator, templates
```

In der Route-Signatur:
```python
async def tipps_get(request: Request, user: dict = Depends(require_non_spectator)):
```

Und in der POST-Route (falls vorhanden) analog.

- [ ] **Schritt 3: `routes/langfrist.py` absichern**

```python
from deps import require_non_spectator, templates
# ...
async def langfrist_get(request: Request, user: dict = Depends(require_non_spectator)):
```

- [ ] **Schritt 4: `routes/uebersicht.py` absichern**

```python
from deps import require_non_spectator, templates
# ...
async def uebersicht_get(request: Request, user: dict = Depends(require_non_spectator)):
```

- [ ] **Schritt 5: `routes/stats.py` absichern**

```python
from deps import require_non_spectator, templates
# ...
async def stats_get(request: Request, user: dict = Depends(require_non_spectator)):
```

- [ ] **Schritt 6: `routes/profil.py` absichern**

```python
from deps import require_non_spectator, templates
# ...
async def profil_get(request: Request, user: dict = Depends(require_non_spectator)):
```

Hinweis: In jeder Datei nur den `require_user`-Import auf `require_non_spectator` ändern und im `Depends()`-Aufruf tauschen. Der Rest der Route bleibt unverändert.

- [ ] **Schritt 7: Testen**

- Als Zuschauer `/tipps` direkt aufrufen → Redirect zu `/home` mit Flash-Hinweis ✓
- Als Zuschauer `/stats` aufrufen → Redirect ✓
- Als Teilnehmer `/tipps` aufrufen → funktioniert wie vorher ✓

---

## Task 7: Leaderboard – Kassen-Details für Zuschauer ausblenden

**Files:**
- Modify: `templates/leaderboard.html`

- [ ] **Schritt 1: Pool-Anzeige im Leaderboard einschränken**

Im Leaderboard-Template den Bereich, wo `pool` angezeigt wird (Kasse/Topf-Details, Einzahlungen, wer bezahlt hat), suchen. Alle Stellen wo `pool` oder Kassen-Daten verwendet werden mit folgendem einwickeln:

```html
{% if not user.is_spectator %}
  <!-- Kassen-Sektion -->
{% endif %}
```

Hinweis: Mit `pool.enabled` bedingte Blöcke suchen – diese komplett mit dem Spectator-Check umschließen. Der Leaderboard-Rangtisch selbst (Punkte, Namen) bleibt für Zuschauer sichtbar.

---

## Task 8: Admin-Panel – Zuschauer-Toggle

**Files:**
- Modify: `routes/admin.py`
- Modify: `templates/admin.html`

- [ ] **Schritt 1: Toggle-Route in `routes/admin.py` hinzufügen**

Direkt nach dem `toggle-admin` Handler (ca. Zeile 177) einfügen:

```python
@router.post("/user/{user_id}/toggle-spectator")
async def toggle_spectator(request: Request, user_id: int, user: dict = Depends(require_admin)):
    with get_session() as s:
        u = s.get(User, user_id)
        if u and u.id != user["id"]:
            u.is_spectator = not u.is_spectator
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Schritt 2: Toggle-Button in `templates/admin.html` hinzufügen**

In der Nutzerliste, wo der „Passwort"-Button und der Admin-Toggle stehen, für jeden User einen zusätzlichen „Zuschauer"-Button hinzufügen. Das Muster ist identisch zu `toggle-admin`.

Den bestehenden Admin-Toggle-Button als Vorlage nehmen und direkt daneben einfügen:

```html
<form method="post" action="/admin/user/{{ u.id }}/toggle-spectator" class="d-inline">
  <button type="submit" class="btn btn-sm {% if u.is_spectator %}btn-info{% else %}btn-outline-secondary{% endif %}">
    <i class="bi bi-eye{% if not u.is_spectator %}-slash{% endif %}"></i>
    {% if u.is_spectator %}Zuschauer{% else %}Teilnehmer{% endif %}
  </button>
</form>
```

Wichtig: In der Admin-Route (`GET /admin`) werden User aus der DB geladen – sicherstellen, dass das `is_spectator` Feld mitgeladen wird (ist automatisch der Fall via SQLAlchemy).

- [ ] **Schritt 3: Testen**

- Admin-Panel öffnen → jeder User hat „Zuschauer/Teilnehmer"-Button ✓
- Button klicken → Status wechselt, Seite lädt neu ✓
- Nutzer nach Toggle einloggen → korrekte Navigation ✓

---

## Abschluss-Test

- [ ] Frischer Testdurchlauf: Neuen Zuschauer-Account registrieren (mit Checkbox)
- [ ] Einloggen → landet auf `/home`, sieht eingeschränkte Nav
- [ ] Direktzugriff auf `/tipps` → Redirect mit Hinweis
- [ ] Torschützen und Spielplan sind zugänglich
- [ ] Leaderboard zeigt Rangliste aber keine Kassen-Details
- [ ] Admin kann Zuschauer-Status per Toggle ändern
- [ ] Bestehende Teilnehmer-Accounts funktionieren wie vorher (keine Regressions)
- [ ] Service-Worker Cache-Version in `static/sw.js` hochzählen (z.B. `wm2026-v7`)
