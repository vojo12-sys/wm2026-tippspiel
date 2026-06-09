# Bonus Tipps & UI-Verbesserungen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 7 unabhängige Verbesserungen: Umbenennung Langfrist→Bonus, goldenes Nav-Glow, Countdown, neue Gruppen-Scoring-Logik, Pott dauerhaft offen, Trefferquote-Format, Urkunden-Redesign.

**Architecture:** Alle Änderungen erfolgen in bestehenden Dateien — kein neues Routing, keine neuen Modelle. Scoring-Logik in `scoring.py` + `config.py`, UI in Templates + `static/css/style.css`, Glow-Logik als Jinja2-Global in `deps.py`.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy, Bootstrap 5, vanilla JS

---

## Datei-Übersicht

| Datei | Änderung |
|---|---|
| `config.py` | `group_second: 2→3`, neuer Key `group_partial_credit: 2`, Regeltext |
| `scoring.py` | Neue Gruppen-Scoring-Logik |
| `routes/profil.py` | `_pool_locked()` entfernen |
| `templates/profil.html` | `pool_locked`-Referenzen entfernen |
| `templates/base.html` | Nav-Text + Glow-Klasse |
| `templates/langfrist.html` | Titel, Button, Countdown |
| `templates/uebersicht.html` | Tab-Label + Zeilentexte |
| `templates/regeln.html` | Tabellenzeile „Langfrist" |
| `templates/leaderboard.html` | 2 Dezimalstellen + zentriert |
| `routes/langfrist.py` | `deadline_iso` + Flash-Text |
| `deps.py` | `get_bonus_tips_incomplete()` Jinja2-Global |
| `static/css/style.css` | `@keyframes bonus-glow` + `.nav-glow-gold` |
| `routes/admin.py` | `pts_per_game`, `group_rank`, `ko_rank` berechnen |
| `templates/urkunden.html` | Logo, Titel, Ränge, Experten-Koeffizient, Bonus-Label |

---

## Task 1: Gruppen-Scoring-Logik

**Files:**
- Modify: `config.py`
- Modify: `scoring.py`

- [ ] **Schritt 1: `config.py` anpassen**

In `DEFAULT_SCORING` Zeile `"group_second": 2` auf `3` ändern und neuen Key ergänzen:

```python
# --- Gruppen-Platzierungen (Bonus Tipps) ---
"group_first": 3,            # richtiger Gruppensieger (exakt 1. Platz)
"group_second": 3,           # richtiger Gruppenzweiter (exakt 2. Platz)
"group_partial_credit": 2,   # Team korrekt im Top-2, aber falsche Position
```

In `DEFAULT_RULES` den Abschnitt „Langfrist-Tipps" (wird in Task 3 zu „Bonus Tipps") — die Zeilen für Gruppensieger/zweiter ersetzen:

```
- Gruppensieger (exakt 1. Platz): {group_first} Punkte je Gruppe
- Gruppenzweiter (exakt 2. Platz): {group_second} Punkte je Gruppe
- Team auf Platz 2 getippt, wird Gruppensieger: {group_partial_credit} Punkte je Gruppe
- Team auf Platz 1 getippt, wird Gruppenzweiter: {group_partial_credit} Punkte je Gruppe
```

- [ ] **Schritt 2: `scoring.py` — `recalculate_group_predictions()` ersetzen**

Die komplette Funktion `recalculate_group_predictions` ersetzen:

```python
def recalculate_group_predictions() -> None:
    """Bewertet alle Gruppen-Tipps anhand der tatsächlichen Platzierungen."""
    s = get_scoring()
    with get_session() as session:
        results = {gr.group_letter: gr for gr in session.scalars(select(GroupResult)).all()}
        preds = session.scalars(select(GroupPrediction)).all()
        for gp in preds:
            res = results.get(gp.group_letter)
            pts = 0
            if res:
                if res.actual_1st is not None:
                    if gp.predicted_1st == res.actual_1st:
                        pts += s["group_first"]
                    elif gp.predicted_2nd == res.actual_1st:
                        pts += s["group_partial_credit"]
                if res.actual_2nd is not None:
                    if gp.predicted_2nd == res.actual_2nd:
                        pts += s["group_second"]
                    elif gp.predicted_1st == res.actual_2nd:
                        pts += s["group_partial_credit"]
            gp.points_awarded = pts
```

- [ ] **Schritt 3: Schnell-Test über Python-REPL**

```bash
python -c "
from scoring import recalculate_group_predictions
from config import DEFAULT_SCORING
s = DEFAULT_SCORING
print('group_first:', s['group_first'])
print('group_second:', s['group_second'])
print('group_partial_credit:', s['group_partial_credit'])
print('OK')
"
```

Erwartet: `group_first: 3`, `group_second: 3`, `group_partial_credit: 2`, `OK`

- [ ] **Schritt 4: Commit**

```bash
git add config.py scoring.py
git commit -m "feat: neue Gruppen-Scoring-Logik (beide Positionen 3 Pkt, Kreuzposition 2 Pkt)"
```

---

## Task 2: Pott-Anmeldung dauerhaft offen

**Files:**
- Modify: `routes/profil.py`
- Modify: `templates/profil.html`

- [ ] **Schritt 1: `routes/profil.py` — `_pool_locked()` entfernen**

Die Funktion `_pool_locked()` (Zeilen 15–19) vollständig löschen.

Im `profil_get` Handler den Parameter `pool_locked` entfernen:
```python
# Alt:
return templates.TemplateResponse(request, "profil.html", {
    "user": user, "active": "profil",
    "in_pool": in_pool,
    "has_paid": has_paid,
    "pool": pool,
    "pool_locked": _pool_locked(),   # <-- entfernen
    "flash": request.session.pop("flash", None),
})

# Neu:
return templates.TemplateResponse(request, "profil.html", {
    "user": user, "active": "profil",
    "in_pool": in_pool,
    "has_paid": has_paid,
    "pool": pool,
    "flash": request.session.pop("flash", None),
})
```

Im `update_pool` POST-Handler die Lock-Prüfung (ca. Zeilen 51–54) entfernen:
```python
# Diese Zeilen löschen:
if _pool_locked():
    request.session["flash"] = {"message": "Pott-Anmeldung ist nach Turnierbeginn nicht mehr möglich.", "type": "danger"}
    return RedirectResponse("/profil", status_code=303)
```

Auch den `import Match` und `select` (falls nicht anderweitig genutzt) prüfen — `Match` wird nach dem Entfernen nicht mehr benötigt, die zweite `from sqlalchemy import select`-Zeile (Duplikat, Zeile 12) ebenfalls löschen.

- [ ] **Schritt 2: `templates/profil.html` — `pool_locked`-Referenzen entfernen**

Zeile 35: `{% if has_paid or pool_locked %}disabled{% endif %}` → `{% if has_paid %}disabled{% endif %}`

Zeile 40: `{% if not has_paid and not pool_locked %}` → `{% if not has_paid %}`

Zeile 46–48: Den `elif pool_locked`-Block komplett entfernen:
```html
{# LÖSCHEN: %}
{% elif pool_locked %}
<p class="text-muted small mt-1">Turnier läuft – Pott-Anmeldung nicht mehr möglich.</p>
{# LÖSCHEN Ende #}
```

- [ ] **Schritt 3: Verify**

```bash
python -m uvicorn main:app --port 8080
```
Profil-Seite aufrufen → Pott-Toggle muss sichtbar und bedienbar sein. Kein `pool_locked`-Fehler in den Logs.

- [ ] **Schritt 4: Commit**

```bash
git add routes/profil.py templates/profil.html
git commit -m "feat: Pott-Anmeldung dauerhaft offen (kein Turnier-Lock mehr)"
```

---

## Task 3: Umbenennung „Langfrist-Tipps" → „Bonus Tipps"

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/langfrist.html`
- Modify: `templates/uebersicht.html`
- Modify: `templates/regeln.html`
- Modify: `config.py` (DEFAULT_RULES)
- Modify: `routes/langfrist.py`

- [ ] **Schritt 1: `templates/base.html`**

Zeile 39: `<i class="bi bi-trophy me-2"></i>Langfrist-Tipps` → `<i class="bi bi-trophy me-2"></i>Bonus Tipps`

- [ ] **Schritt 2: `templates/langfrist.html`**

Zeile 3: `<h1 class="mb-2">Langfrist-Tipps</h1>` → `<h1 class="mb-2">Bonus Tipps</h1>`

Zeile 87: `Langfrist-Tipps speichern` → `Bonus Tipps speichern`

- [ ] **Schritt 3: `templates/uebersicht.html`**

Tab-Label (Zeile ~150–151): `Langfrist & Gesamt` → `Bonus & Gesamt`

Zeile ~5: `Gesperrte Spiele · Langfrist-Tipps · Punkte` → `Gesperrte Spiele · Bonus Tipps · Punkte`

Zeile ~267: `Langfrist-Punkte` → `Bonus-Punkte`

- [ ] **Schritt 4: `templates/regeln.html`**

Zeile ~37: `<td colspan="2" class="fw-semibold small">Langfrist</td>` → `Bonus Tipps`

Zeilen 38–39: Gruppen-Scoring-Werte aus Schritt 1 von Task 1 sind hier schon eingebaut via `{{ scoring.group_first }}` etc. — kein Handlungsbedarf außer dem Tabellenheader.

Neue Zeilen für `group_partial_credit` nach `Gruppenzweiter` einfügen (im Scoring-Table, falls vorhanden). Prüfen wie die Regeln-Tabelle aufgebaut ist und entsprechend anpassen.

- [ ] **Schritt 5: `config.py` DEFAULT_RULES**

Abschnittsüberschrift `**Langfrist-Tipps (vor Turnierstart)**` → `**Bonus Tipps (vor Turnierstart)**`

Die zwei Gruppen-Zeilen (aus Task 1) sind schon angepasst.

- [ ] **Schritt 6: `routes/langfrist.py`**

Zeile 109: `"Langfrist-Tipps gespeichert."` → `"Bonus Tipps gespeichert."`

- [ ] **Schritt 7: Commit**

```bash
git add templates/base.html templates/langfrist.html templates/uebersicht.html templates/regeln.html config.py routes/langfrist.py
git commit -m "feat: Langfrist-Tipps in Bonus Tipps umbenannt (URL bleibt /langfrist)"
```

---

## Task 4: Trefferquote – 2 Dezimalstellen + zentriert

**Files:**
- Modify: `templates/leaderboard.html`

- [ ] **Schritt 1: Drei Änderungen in `leaderboard.html`**

Zeile ~241 (TH-Header): `class="text-end fw-bold"` → `class="text-center fw-bold"`

Zeile ~254 (Datenzelle):
```html
<!-- Alt: -->
<td class="text-end fw-bold" style="color:#1E4E8C">{{ "%.1f"|format(tq) }}</td>

<!-- Neu: -->
<td class="text-center fw-bold" style="color:#1E4E8C">{{ "%.2f"|format(tq) }}</td>
```

- [ ] **Schritt 2: Commit**

```bash
git add templates/leaderboard.html
git commit -m "fix: Trefferquote auf 2 Dezimalstellen, zentriert unter Pkt/Spiel"
```

---

## Task 5: Countdown bei Bonus Tipps

**Files:**
- Modify: `routes/langfrist.py`
- Modify: `templates/langfrist.html`

- [ ] **Schritt 1: `routes/langfrist.py` — `deadline_iso` übergeben**

Im `langfrist_get` Handler den Template-Context ergänzen:

```python
# Nach: locked = _is_locked()
deadline_iso = _deadline().isoformat() if not locked else None

# Im return:
return templates.TemplateResponse(request, "langfrist.html", {
    "user": user, "active": "langfrist",
    "locked": locked, "deadline": dl,
    "deadline_iso": deadline_iso,   # NEU
    "special": special, "gpreds": gpreds,
    "teams": _all_teams(),
    "teams_by_group": _teams_by_group(),
    "groups": sorted(GROUPS.keys()),
    "scorer_opts": dropdown_options(),
    "flash": request.session.pop("flash", None),
})
```

- [ ] **Schritt 2: `templates/langfrist.html` — Countdown-Span und JS**

Im unlocked-Alert (Zeile ~8) den Countdown-Span ergänzen:

```html
{% else %}
<div class="alert alert-info">
  Editierbar bis <strong>{{ deadline }}</strong>. Danach gesperrt.
  {% if deadline_iso %}
  &nbsp;·&nbsp; <span id="bonus-countdown" style="font-weight:600"></span>
  {% endif %}
</div>
{% endif %}
```

Am Ende des Templates (vor `{% endblock %}`):

```html
{% if deadline_iso %}
<script>
(function() {
  const target = new Date({{ deadline_iso | tojson }});
  const el = document.getElementById('bonus-countdown');
  if (!el) return;
  function update() {
    const diff = target - Date.now();
    if (diff <= 0) { el.textContent = 'Abgelaufen!'; return; }
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    el.textContent = d > 0
      ? `${d}T ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
      : `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  }
  update();
  setInterval(update, 1000);
})();
</script>
{% endif %}
```

- [ ] **Schritt 3: Commit**

```bash
git add routes/langfrist.py templates/langfrist.html
git commit -m "feat: Live-Countdown bis Bonus-Tipps-Deadline in Langfrist-Seite"
```

---

## Task 6: Goldenes Aufleuchten im Menü

**Files:**
- Modify: `deps.py`
- Modify: `static/css/style.css`
- Modify: `templates/base.html`

- [ ] **Schritt 1: `deps.py` — neue Funktion + Jinja2-Global**

Nach `get_pot_info()` die neue Funktion einfügen:

```python
def get_bonus_tips_incomplete(user_id: int | None) -> bool:
    """True wenn Turnier noch nicht gestartet UND User noch keine Bonus Tipps hat."""
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
```

Direkt nach `_env.globals["get_live_scores"] = _get_live_scores` ergänzen:

```python
_env.globals["get_bonus_tips_incomplete"] = get_bonus_tips_incomplete
```

- [ ] **Schritt 2: `static/css/style.css` — Animation ergänzen**

Am Ende der Datei (nach allen bestehenden Regeln) einfügen:

```css
@keyframes bonus-glow {
  0%, 100% { box-shadow: none; color: inherit; }
  50% { box-shadow: 0 0 10px rgba(192,138,18,.6); color: var(--gold) !important; }
}
.nav-glow-gold {
  animation: bonus-glow 1.8s ease-in-out infinite;
  border-radius: 8px;
}
```

- [ ] **Schritt 3: `templates/base.html` — Glow-Klasse auf Nav-Link**

Den Langfrist/Bonus-Tipps-Nav-Link (Zeile ~38–40) ergänzen:

```html
<a href="/langfrist" class="nav-link {% if active == 'langfrist' %}active{% endif %} {% if user and get_bonus_tips_incomplete(user.id) %}nav-glow-gold{% endif %}">
  <i class="bi bi-trophy me-2"></i>Bonus Tipps
</a>
```

- [ ] **Schritt 4: Service Worker Cache-Version erhöhen**

In `static/sw.js` die Cache-Version um 1 erhöhen (z.B. `wm2026-v6` → `wm2026-v7`).

- [ ] **Schritt 5: Commit**

```bash
git add deps.py static/css/style.css templates/base.html static/sw.js
git commit -m "feat: goldenes Nav-Glow für Bonus Tipps wenn noch nicht ausgefüllt"
```

---

## Task 7: Siegerurkunden Redesign

**Files:**
- Modify: `routes/admin.py`
- Modify: `templates/urkunden.html`

- [ ] **Schritt 1: `routes/admin.py` — neue Felder berechnen**

In `urkunden_get()` nach der `tip_counts`-Berechnung und dem `for r in rows`-Loop:

```python
KO_PHASES = {"round32", "round16", "quarter", "semi", "third_place", "final"}

for r in rows:
    r.tips_total = tip_counts.get(r.user_id, 0)
    match_pts = sum(r.phase_points.values())
    r.pts_per_game = round(match_pts / r.tips_total, 2) if r.tips_total > 0 else 0.0

# group_rank: Platz nach Gruppenphase-Punkten
sorted_group = sorted(rows, key=lambda r: -(r.phase_points.get("group", 0)))
for i, r in enumerate(sorted_group, 1):
    r.group_rank = i

# ko_rank: Platz nach K.o.-Phasen-Punkten
sorted_ko = sorted(rows, key=lambda r: -sum(r.phase_points.get(p, 0) for p in KO_PHASES))
for i, r in enumerate(sorted_ko, 1):
    r.ko_rank = i
```

- [ ] **Schritt 2: `templates/urkunden.html` — CSS anpassen**

Im `<style>`-Block folgende Änderungen:

**Logo größer:**
```css
.cert-logo {
  height: 8%;          /* war 4% */
  min-height: 56px;    /* war 28px */
  opacity: .85;
  margin-bottom: 2%;
  filter: brightness(0) invert(1);
  clip-path: inset(10% 0 0 0);
  margin-top: -10%;
}
```

**Turnier-Schriftzug doppelt so groß:**
```css
.cert-tournament {
  font-size: clamp(1.1rem, 2.4vw, 1.56rem);  /* war clamp(.55rem, 1.2vw, .78rem) */
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: #e8c060;
  margin-bottom: 1.5%;
  line-height: 1.35;
  text-align: center;
}
```

**Neue Rang-Anzeige (3-spaltig):**
```css
.cert-ranks {
  display: flex;
  gap: clamp(.5rem, 1.5vw, 1rem);
  justify-content: center;
  margin-bottom: 3%;
}
.rank-box {
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 10px;
  padding: clamp(.3rem, 1vw, .6rem) clamp(.5rem, 1.2vw, .9rem);
  min-width: clamp(55px, 9vw, 80px);
  text-align: center;
}
.rank-box-highlight {
  background: rgba(192,138,18,.12);
  border: 1px solid rgba(192,138,18,.4);
}
.rank-box-num {
  font-family: 'Bricolage Grotesque', sans-serif;
  font-weight: 800;
  display: block;
  line-height: 1;
  margin-bottom: 3px;
}
.rank-box-num-main {
  font-size: clamp(1.8rem, 5vw, 3.5rem);
}
.rank-box-num-side {
  font-size: clamp(1rem, 2.5vw, 1.8rem);
  color: rgba(255,255,255,.8);
}
.rank-box-lbl {
  font-size: clamp(.4rem, .82vw, .58rem);
  color: rgba(255,255,255,.5);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.rank-box-highlight .rank-box-lbl { color: rgba(240,192,64,.7); }
```

**Experten-Koeffizient-Zeile:**
```css
.cert-expert {
  font-size: clamp(.48rem, .95vw, .68rem);
  color: rgba(255,255,255,.55);
  letter-spacing: .04em;
  margin-bottom: 3%;
}
.cert-expert strong {
  color: rgba(255,255,255,.8);
}
```

**`cert-rank` (bisherige große Zahl) und `.cert-content justify-content: center` beibehalten** — die `.cert-rank`-Klasse wird durch `cert-ranks` ersetzt, also kann die alte Definition bleiben oder entfernt werden.

- [ ] **Schritt 3: `templates/urkunden.html` — HTML-Struktur ersetzen**

Den kompletten `cert-content`-Div (`<div class="cert-content">` bis `</div>`) für jede Urkunde ersetzen:

```html
<div class="cert-content">

  <img src="/static/img/lew_logo.png" class="cert-logo" alt="LEW Automotive">

  <div class="cert-tournament">
    FIFA Weltmeisterschaft 2026<br>
    Tippspiel der LEW Automotive GmbH
  </div>

  <div class="cert-title">Siegerurkunde</div>

  <div class="cert-name">{{ row.display_name }}</div>

  <!-- Rang-Anzeige 3-spaltig -->
  <div class="cert-ranks">
    <div class="rank-box">
      <span class="rank-box-num rank-box-num-side">{{ row.group_rank }}.</span>
      <div class="rank-box-lbl">Gruppenphase</div>
    </div>
    <div class="rank-box rank-box-highlight">
      <span class="rank-box-num rank-box-num-main {% if row.rank == 1 %}rank-1{% elif row.rank == 2 %}rank-2{% elif row.rank == 3 %}rank-3{% else %}rank-other{% endif %}">{{ row.rank }}.</span>
      <div class="rank-box-lbl">Gesamt</div>
    </div>
    <div class="rank-box">
      <span class="rank-box-num rank-box-num-side">{{ row.ko_rank }}.</span>
      <div class="rank-box-lbl">K.o.-Phase</div>
    </div>
  </div>

  <!-- Statistiken -->
  <div class="cert-stats">
    <div class="stat-box">
      <span class="stat-num gold">{{ row.total_points }}</span>
      <div class="stat-lbl">Punkte</div>
    </div>
    <div class="stat-box">
      <span class="stat-num">{{ row.tips_total }} / {{ total_matches }}</span>
      <div class="stat-lbl">Tipps</div>
    </div>
    <div class="stat-box">
      <span class="stat-num">{{ row.exact_count }}</span>
      <div class="stat-lbl">Exakt</div>
    </div>
    <div class="stat-box">
      <span class="stat-num">{{ row.goal_diff_count }}</span>
      <div class="stat-lbl">Tordiff.</div>
    </div>
    <div class="stat-box">
      <span class="stat-num">{{ row.tendency_count }}</span>
      <div class="stat-lbl">Tendenz</div>
    </div>
    <div class="stat-box">
      <span class="stat-num">{{ row.longterm_points }}</span>
      <div class="stat-lbl">Bonus</div>
    </div>
  </div>

  <!-- Experten-Koeffizient -->
  <div class="cert-expert">
    <strong>Experten-Koeffizient:</strong> {{ "%.2f"|format(row.pts_per_game) }} Pkt/Spiel
  </div>

  <div class="cert-divider"></div>

  <div class="cert-footer">
    Kanada · Mexiko · USA &nbsp;·&nbsp; 11. Juni – 19. Juli 2026
  </div>

</div>
```

- [ ] **Schritt 4: Commit**

```bash
git add routes/admin.py templates/urkunden.html
git commit -m "feat: Urkunden-Redesign – Logo doppelt, 3-facher Rang, Experten-Koeffizient, Bonus-Label"
```

---

## Abschluss

- [ ] **App starten und alle Seiten prüfen**

```bash
python -m uvicorn main:app --reload --port 8080
```

Prüfliste:
- Navigation zeigt „Bonus Tipps"
- Glow erscheint wenn keine Bonus Tipps abgegeben (und Turnier noch nicht gestartet)
- `/langfrist` zeigt Countdown
- `/leaderboard` → Zahlen & Fakten → Pkt/Spiel mit 2 Nachkommastellen, zentriert
- `/profil` → Pott-Toggle jederzeit bedienbar
- `/admin/urkunden` → Logo größer, 2-zeiliger Turniertitel, 3-Rang-Anzeige, Experten-Koeffizient

- [ ] **Service Worker in Browser zurücksetzen falls CSS-Änderungen nicht sichtbar**

Edge/Chrome: F12 → Anwendung → Service Worker → Registrierung aufheben → Strg+Shift+R
