# Design: Bonus Tipps & UI-Verbesserungen

**Datum:** 2026-06-10  
**Status:** Genehmigt

---

## Übersicht

7 unabhängige Änderungen am WM 2026 Tippspiel. Alle bauen auf dem bestehenden FastAPI/Jinja2-Stack auf.

---

## 1. Umbenennung „Langfrist-Tipps" → „Bonus Tipps"

### Betroffene Stellen

| Datei | Stelle |
|---|---|
| `templates/base.html` | Nav-Link-Text (Zeile 39) |
| `templates/langfrist.html` | `<h1>`, Button-Text |
| `templates/uebersicht.html` | Tab-Label, Zeilen mit „Langfrist" |
| `templates/urkunden.html` | `stat-lbl` „Langfrist" |
| `config.py` | `DEFAULT_RULES` Abschnittsüberschrift |
| `routes/langfrist.py` | Flash-Meldung |
| `templates/regeln.html` | Regeltext |

URL `/langfrist`, Dateinamen und Python-Variablen bleiben unverändert.

---

## 2. Goldenes Aufleuchten im Menü (Bonus Tipps)

### Ziel
Teilnehmer, die noch keine Bonus Tipps abgegeben haben, sehen den Nav-Button golden pulsieren. Nach Turnierstart verschwindet der Effekt.

### Implementierung

**`deps.py`**: Neue Funktion `get_bonus_tips_incomplete(user_id: int | None) -> bool`:
- Gibt `True` zurück wenn: `datetime.now(utc) < TOURNAMENT_START_UTC` UND User hat weder `SpecialTip` noch `GroupPrediction` in der DB
- Gibt `False` zurück wenn kein User eingeloggt, Turnier bereits gestartet, oder Tipps vorhanden
- Als Jinja2-Global registriert: `_env.globals["get_bonus_tips_incomplete"] = get_bonus_tips_incomplete`

**`templates/base.html`**: Konditionaler CSS-Class auf den Bonus-Tipps-Link:
```html
<a href="/langfrist" class="nav-link ... {% if user and get_bonus_tips_incomplete(user.id) %}nav-glow-gold{% endif %}">
```

**`static/css/style.css`**: Neue Animation:
```css
@keyframes bonus-glow {
  0%, 100% { box-shadow: 0 0 0 rgba(192,138,18,0); color: inherit; }
  50% { box-shadow: 0 0 10px rgba(192,138,18,.6); color: var(--gold); }
}
.nav-glow-gold { animation: bonus-glow 1.8s ease-in-out infinite; border-radius: 8px; }
```

---

## 3. Countdown bei Bonus Tipps

### Ziel
Neben dem Hinweis „Editierbar bis 11.06.2026 · 21:00 Uhr" läuft ein Live-Countdown bis zur Deadline.

### Implementierung

**`routes/langfrist.py`**: Zusätzlicher Template-Parameter `deadline_iso` (ISO-String, z.B. `"2026-06-11T19:00:00+00:00"`), nur wenn nicht gesperrt.

**`templates/langfrist.html`**: Im unlocked-Alert ein `<span id="bonus-countdown">` direkt hinter dem Deadline-Text, gleiche Schriftfarbe und -größe wie der Alert-Text. Inline-JS `setInterval` analog `tipps.html`:
```js
const target = new Date("{{ deadline_iso }}");
// ... d/h:mm:ss Anzeige
```

---

## 4. Neue Gruppen-Scoring-Logik

### Neue Punkteverteilung

| Tipp | Ergebnis | Punkte |
|---|---|---|
| 1. Platz | Team wird 1. | 3 Pkt |
| 2. Platz | Team wird 2. | 3 Pkt |
| 2. Platz | Team wird 1. | 2 Pkt |
| 1. Platz | Team wird 2. | 2 Pkt |

### Implementierung

**`config.py` `DEFAULT_SCORING`**:
- `group_second: 2` → `group_second: 3`
- Neuer Key: `group_partial_credit: 2`

**`scoring.py` `recalculate_group_predictions()`**:
```python
pts = 0
if res:
    # 1st place
    if res.actual_1st is not None:
        if gp.predicted_1st == res.actual_1st:
            pts += s["group_first"]       # exakt 1. → 3
        elif gp.predicted_2nd == res.actual_1st:
            pts += s["group_partial_credit"]  # auf 2 getippt, aber 1. → 2
    # 2nd place
    if res.actual_2nd is not None:
        if gp.predicted_2nd == res.actual_2nd:
            pts += s["group_second"]       # exakt 2. → 3
        elif gp.predicted_1st == res.actual_2nd:
            pts += s["group_partial_credit"]  # auf 1 getippt, aber 2. → 2
gp.points_awarded = pts
```

**`config.py` `DEFAULT_RULES`**: Abschnitt „Bonus Tipps" anpassen:
```
- Gruppensieger (exakt 1. Platz): 3 Punkte
- Gruppenzweiter (exakt 2. Platz): 3 Punkte
- Team auf Platz 2 getippt, wird aber Gruppensieger: 2 Punkte
- Team auf Platz 1 getippt, wird aber Gruppenzweiter: 2 Punkte
```

---

## 5. Pott-Anmeldung dauerhaft offen

### Ziel
Neue Teilnehmer können sich während des Turniers noch für den Pott anmelden.

### Implementierung

**`routes/profil.py`**:
- Funktion `_pool_locked()` entfernen
- Alle Aufrufe von `_pool_locked()` entfernen (GET und POST Handler)
- Fehlermeldung „Pott-Anmeldung ist nach Turnierbeginn nicht mehr möglich" entfernen
- `pool_locked: False` an Template übergeben (oder Parameter entfernen falls nicht im Template verwendet)

---

## 6. Trefferquote: 2 Dezimalstellen + zentriert

**`templates/leaderboard.html`**:
- Zeile ~254: `"%.1f"|format(tq)` → `"%.2f"|format(tq)`
- Spaltenheader `<th class="text-end fw-bold">Pkt / Spiel</th>` → `text-center`
- Datenzelle `<td class="text-end fw-bold" ...>` → `text-center`

---

## 7. Siegerurkunden

### 7a. Logo (doppelt so groß, oberes Drittel)
```css
.cert-logo {
  height: 8%;      /* war 4% */
  min-height: 56px; /* war 28px */
  /* clip-path und filter bleiben */
}
```
Flex-Layout: `cert-content` wird in zwei Flex-Bereiche aufgeteilt — oberes Drittel (Logo + Turniertitel) und unteres Zweidrittel (Rang, Name, Stats).

### 7b. Turnier-Schriftzug (doppelt, 2 Zeilen)
```css
.cert-tournament {
  font-size: clamp(1.1rem, 2.4vw, 1.56rem); /* verdoppelt */
  line-height: 1.3;
}
```
HTML:
```html
<div class="cert-tournament">
  FIFA Weltmeisterschaft 2026<br>
  Tippspiel der LEW Automotive GmbH
</div>
```

### 7c. Stat-Label Umbenennung
`<div class="stat-lbl">Langfrist</div>` → `<div class="stat-lbl">Bonus</div>`

### 7d. Rang-Anzeige (3-spaltig unter dem Namen)
Neue `.cert-ranks`-Div direkt unter `.cert-name`:
```html
<div class="cert-ranks">
  <div class="rank-box rank-highlight">
    <span class="rank-num">{{ row.rank }}.</span>
    <div class="rank-lbl">Gesamt</div>
  </div>
  <div class="rank-box">
    <span class="rank-num">{{ row.group_rank }}.</span>
    <div class="rank-lbl">Gruppenphase</div>
  </div>
  <div class="rank-box">
    <span class="rank-num">{{ row.ko_rank }}.</span>
    <div class="rank-lbl">K.o.-Phase</div>
  </div>
</div>
```
Gesamt-Box: goldener Rahmen + größere Schrift (hervorgehoben).

### 7e. Experten-Koeffizient
Neue Textzeile unter den Stat-Boxen:
```html
<div class="cert-expert">
  Experten-Koeffizient: {{ "%.2f"|format(row.pts_per_game) }} Pkt/Spiel
</div>
```

**`routes/admin.py` `urkunden_get()`**: Berechnung der neuen Felder:
```python
# pts_per_game aus Spiel-Punkten / getippte Spiele
match_pts = sum(r.phase_points.values())
r.pts_per_game = round(match_pts / r.tips_total, 2) if r.tips_total > 0 else 0.0

# group_rank und ko_rank aus phase_points
```
Für `group_rank` und `ko_rank`: Teilnehmer nach `phase_points["group"]` bzw. Summe K.o.-Phasen ranken.

---

## Reihenfolge der Umsetzung

1. Scoring-Logik (4) — kein UI-Impact, isoliert testbar
2. Pott-Anmeldung (5) — isoliert
3. Umbenennung (1) — rein textuell
4. Trefferquote (6) — kleine Template-Änderung
5. Countdown (3) — Template + Route
6. Goldenes Aufleuchten (2) — deps.py + CSS + Template
7. Urkunden (7) — größte Änderung, nur Admin sichtbar
