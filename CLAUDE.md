# WM 2026 Tippspiel – Projektkontext für Claude

## Start

```bash
python -m uvicorn main:app --reload --port 8080   # App → http://localhost:8080
python seed.py                                     # DB initialisieren (einmalig)
python import_schedule.py                          # Spielplan laden (104 Spiele)
python demo_data.py 10                             # Testdaten: 10 Spiele simulieren
python demo_data.py reset                          # Testdaten zurücksetzen
```

## Stack

**Python · FastAPI · Jinja2 · SQLAlchemy · SQLite (lokal) / PostgreSQL (Render)**

---

## Dateistruktur

| Datei/Ordner | Zweck |
|---|---|
| `main.py` | FastAPI-App, alle Router registriert, APScheduler (Ergebnis-Sync alle 5 Min.) |
| `models.py` | DB-Schema: User, Match, Prediction, GroupPrediction, SpecialTip, GroupResult, TournamentResult, TopScorer |
| `database.py` | SQLAlchemy Engine + Session-Kontextmanager (autocommit on exit) |
| `deps.py` | Jinja2-Templates, Auth-Helpers, Jinja2-Globals (get_pool, get_pot_info, get_live_scores) |
| `config.py` | Konstanten: Punkte, Kasse, Tippsperre (10 Min. vor Anpfiff), Turnier-Daten |
| `settings.py` | Laufzeit-Konfiguration (überschreibt config.py via Admin-UI) |
| `scoring.py` | Punkte-Engine: recalculate_match(), recalculate_all() |
| `standings.py` | Rangliste (Standing-Dataclass mit exact_count, goal_diff_count, tendency_count) + Topf |
| `auth.py` | Login, Passwort-Hashing (PBKDF2) |
| `results_sync.py` | football-data.org API: FINISHED→DB+Punkte, IN_PLAY/PAUSED→Live-Cache (_live_scores) |
| `api_sports.py` | TheSportsDB optional für Spielerfotos (SPORTSDB_API_KEY) |
| `data_teams.py` | 48 Teams nach Gruppen (A–L), flag-codes |
| `data_players.py` | Torschützenkönig-Dropdown, automatisch aus data_squads.py generiert |
| `data_squads.py` | Offizielle FIFA-Kader aller 48 Teams (Stand: 5. Juni 2026) |
| `data_schedule.py` | 104 Spiele mit Kickoff, Venue, Gruppen |
| `data_venues.py` | 16 Spielorte mit Koordinaten |
| `demo_data.py` | Testdaten-Script: simuliert Ergebnisse und Tipps |
| `static/css/style.css` | Bootstrap-Overrides, CSS-Variablen |
| `static/img/lew_logo.png` | LEW Automotive Logo (512×346px) |
| `static/img/landing.jpg` | Landing Page Hintergrundbild |
| `static/sw.js` | Service Worker (Cache-Version bei CSS-Änderungen hochzählen!) |
| `templates/` | Jinja2-Templates für alle Seiten |

## Routes

| Route | Template | Auth |
|---|---|---|
| `GET /` | `landing.html` | nein |
| `GET /login` / `POST /login` | `login.html` | nein |
| `GET /register` / `POST /register` | `register.html` | nein |
| `GET /tipps` | `tipps.html` | ja |
| `GET /langfrist` | `langfrist.html` | ja |
| `GET /spielplan` | `spielplan.html` | ja |
| `GET /leaderboard` | `leaderboard.html` | ja |
| `GET /uebersicht` | `uebersicht.html` | ja |
| `GET /torschuetzen` | `torschuetzen.html` | ja |
| `GET /stats` | `stats.html` | ja |
| `GET /profil` | `profil.html` | ja |
| `GET /regeln` | `regeln.html` | ja |
| `GET /teams` | `teams.html` | ja |
| `GET /admin` | `admin.html` | Admin |
| `GET /admin/urkunden` | `urkunden.html` | Admin |

---

## Design-System

### Farben
- **Akzent:** `#7EC8E3` (hellblau) · dunkel: `#4aaec8`
- **Highlight/Tabellen:** `#1E4E8C` (dunkelblau) — ersetzt Bootstrap-Grün
- **Gold:** `#c08a12` · **Silber:** `#8794a3` · **Bronze:** `#ad6a34`
- **Joker:** `#dc3545` (rot) — Icon: `bi-suit-diamond-fill text-danger`
- **Live-Anzeige:** `#dc3545` (rot) mit `livepulse`-Animation

### Schriften
- **Bricolage Grotesque** (Überschriften, weight 800)
- **Hanken Grotesk** (Fließtext)

### CSS-Variablen (`static/css/style.css`)
```css
--accent: #7EC8E3;
--accent-dk: #4aaec8;
--gold: #c08a12;
```
Bootstrap-Grün (table-success etc.) wird per CSS-Variablen auf `#1E4E8C` überschrieben.

### Service Worker Cache
Bei jeder CSS-Änderung die Version in `static/sw.js` hochzählen:
```js
const CACHE = 'wm2026-v5';  // bei Änderung: v6, v7, ...
```
Danach in Edge: Rechtsklick → Untersuchen → Anwendung → Service Worker → Registrierung aufheben → Strg+Shift+R

---

## Wichtige Implementierungsdetails

### Tippsperre
- Tipps werden **10 Minuten vor Anpfiff** gesperrt (`models.py: is_locked`)
- Steht so in den Spielregeln (`config.py: DEFAULT_RULES`)

### Joker
- Jeder Nutzer hat einen einmaligen Joker (verdoppelt Punkte für ein Spiel)
- **Bug-Fix**: Joker-Form darf NICHT in die Tipp-Form verschachtelt sein (HTML5 `form`-Attribut verwenden)
- Joker-Button: `<button form="joker-form-{m.id}">` + externe `<form id="joker-form-{m.id}">`

### Live-Scores
- `results_sync.py` holt alle 5 Min. Daten von football-data.org
- `FINISHED` → DB + Punkte-Neuberechnung
- `IN_PLAY` / `PAUSED` → nur `_live_scores`-Dict (kein DB-Commit, keine Punkte)
- In Templates via `get_live_scores()` (Jinja2-Global aus `deps.py`) abrufbar
- Zeigt roten ● LIVE-Badge mit Minute und Zwischenstand

### Leaderboard
- Tabs: Gesamt / Gruppenphase / K.o.-Phase
- Spalten: Exakt / Tordiff. / Tendenz (aus `standings.py: exact_count` etc.)
- Eigene Zeile wird mit `#1E4E8C` hinterlegt (Bootstrap `table-success` überschrieben)

### Spielplan
- Gruppentabellen werden immer angezeigt (auch ohne Ergebnisse, alle Teams mit 0)
- Tabellen berechnet aus `_group_tables()` in `routes/spielplan.py`
- Live-Score-Anzeige in Gruppen- und Bracket-Ansicht

### Tipp-Übersicht (`/uebersicht`)
- Tabs nach **Datum** (nicht Phase) — ein Tab pro Spieltag
- Ergebnisse in `#1E4E8C`, positive Punkte in Rot (`#dc3545`), 0 Punkte in `#1E4E8C`
- Langfrist-Tab: Gruppensieger-Tipps + Sonder-Tipps + Gesamtpunkte
- Gesamt-Tab: Spiel + Langfrist + Summe

### Kader & Teams (`/teams`)
- Offizielle FIFA-Kader aus `data_squads.py` (alle 48 Teams, 26 Spieler je)
- Kader-Modal öffnet bei Klick auf Team-Karte
- Spielerfotos via TheSportsDB wenn `SPORTSDB_API_KEY` gesetzt
- Teams klickbar → Wikipedia (deutsch)
- Spielorte: Wikipedia + Google Maps Links

### Siegerurkunden (`/admin/urkunden`)
- A4 Hochformat mit Landing-Page-Hintergrundbild
- Print-CSS: `@page { size: A4 portrait; margin: 0 }`
- Drucken: Browser → Drucken → Als PDF → **Hintergrundgrafiken aktivieren**

### Encodings (WICHTIG)
- **Nie PowerShell `Get-Content`** für UTF-8-Dateien nutzen → zerstört Umlaute
- Für Datei-Operationen immer Python: `open(f, encoding='utf-8')`
- Bei Batch-Ersetzungen: Python-Script schreiben, nicht PowerShell

---

## Datenbank

- Lokal: `wm2026.db` (SQLite)
- Online: `DATABASE_URL` Umgebungsvariable → Postgres
- Schema-Änderungen: manuell via SQL oder neu initialisieren (`seed.py`)
- `get_session()` committet automatisch am Ende des `with`-Blocks

## Umgebungsvariablen

| Variable | Zweck |
|---|---|
| `DATABASE_URL` | Postgres-URL (leer = SQLite) |
| `SECRET_KEY` | Session-Signing (Pflicht in Produktion) |
| `FOOTBALL_API_KEY` | football-data.org für Ergebnis-Sync + Torschützenliste |
| `SPORTSDB_API_KEY` | TheSportsDB für Spielerfotos im Kader-Modal |

## Kassen-Modell

- Teilnahme ohne Geldeinsatz möglich (`in_pool = False`)
- Topf nur unter Einzahlern aufgeteilt
- Nicht-Zahler kann sportlich gewinnen → Geld an bestplatzierten Zahler
- Topf-Anzeige in der Sidebar für alle eingeloggten Nutzer (via `get_pot_info()` Jinja2-Global)
