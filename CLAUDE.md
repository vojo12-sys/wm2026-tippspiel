# WM 2026 Tippspiel – Projektkontext für Claude

## Start

```bash
python -m uvicorn main:app --reload --port 8080   # App → http://localhost:8080
python seed.py                                     # DB initialisieren (einmalig)
python import_schedule.py                          # Spielplan laden (104 Spiele)
python demo_data.py 10                             # Testdaten: 10 Spiele simulieren
python demo_data.py reset                          # Testdaten zurücksetzen (löscht Tipps, Joker, Ergebnisse)
```

## Produktion (Render)

- **URL:** https://wm2026-tippspiel-l9sj.onrender.com
- **Repo:** https://github.com/vojo12-sys/wm2026-tippspiel
- **DB:** PostgreSQL auf Render (günstigster kostenpflichtiger Tarif, kein Free Tier)
- Webservice läuft ebenfalls auf dem günstigsten kostenpflichtigen Tarif
- Deploy: automatisch bei `git push origin main`
- Kein Sleep nach Inaktivität (kostenpflichtiger Tarif), daher auch kein Cold-Start-Delay beim ersten Aufruf

### Remote-DB-Befehle (lokal ausführen)
```powershell
$env:DATABASE_URL="<external-db-url>"; python seed.py
$env:DATABASE_URL="<external-db-url>"; python import_schedule.py
```

## Stack

**Python · FastAPI · Jinja2 · SQLAlchemy · SQLite (lokal) / PostgreSQL (Render)**

---

## Dateistruktur

| Datei/Ordner | Zweck |
|---|---|
| `main.py` | FastAPI-App, alle Router registriert, APScheduler (Ergebnis-Sync alle 5 Min.) |
| `models.py` | DB-Schema: User, Match, Prediction, GroupPrediction, SpecialTip, GroupResult, TournamentResult, TopScorer |
| `database.py` | SQLAlchemy Engine + Session-Kontextmanager (autocommit on exit). Konvertiert `postgresql://` → `postgresql+psycopg://` automatisch. |
| `deps.py` | Jinja2-Templates, Auth-Helpers, Jinja2-Globals (get_pool, get_pot_info, get_live_scores) |
| `config.py` | Konstanten: Punkte, Kasse, Tippsperre (10 Min. vor Anpfiff), Turnier-Daten, DEFAULT_RULES |
| `settings.py` | Laufzeit-Konfiguration (überschreibt config.py via Admin-UI) |
| `scoring.py` | Punkte-Engine: recalculate_match(), recalculate_all() |
| `standings.py` | Rangliste (Standing-Dataclass mit exact_count, goal_diff_count, tendency_count) + Topf |
| `auth.py` | Login, Passwort-Hashing (PBKDF2) |
| `results_sync.py` | football-data.org API: FINISHED→DB+Punkte, IN_PLAY/PAUSED→Live-Cache (_live_scores). Bei Elfmeterschießen wird Penalty-Score als Ergebnis gespeichert. |
| `api_sports.py` | TheSportsDB optional für Spielerfotos (SPORTSDB_API_KEY) |
| `data_teams.py` | 48 Teams nach Gruppen (A–L), flag-codes |
| `data_players.py` | Torschützenkönig-Dropdown, automatisch aus data_squads.py generiert |
| `data_squads.py` | Offizielle FIFA-Kader aller 48 Teams (Stand: 5. Juni 2026) |
| `data_schedule.py` | 104 Spiele mit Kickoff, Venue, Gruppen |
| `data_venues.py` | 16 Spielorte mit Koordinaten |
| `demo_data.py` | Testdaten-Script: simuliert Ergebnisse und Tipps. `reset` löscht alle Predictions, Joker, Ergebnisse. |
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
| `GET /admin/qualifikation` | `admin_qualifikation.html` | Admin |

---

## Design-System

### Farben
- **Akzent:** `#7EC8E3` (hellblau) · dunkel: `#4aaec8`
- **Highlight/Tabellen:** `#1E4E8C` (dunkelblau) — ersetzt Bootstrap-Grün
- **Gold:** `#c08a12` · **Silber:** `#8794a3` · **Bronze:** `#ad6a34`
- **Joker:** `#dc3545` (rot) — Icon: `bi-suit-diamond-fill text-danger`
- **Live-Anzeige:** `#dc3545` (rot) mit `livepulse`-Animation
- **Getippt-Badge:** `#28a745` (grün) · **Kein-Tipp-Badge:** `#ffc107` (gelb)

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
const CACHE = 'wm2026-v6';  // bei Änderung: v7, v8, ...
```
Danach in Edge: Rechtsklick → Untersuchen → Anwendung → Service Worker → Registrierung aufheben → Strg+Shift+R

---

## Wichtige Implementierungsdetails

### Tippsperre
- Tipps werden **10 Minuten vor Anpfiff** gesperrt (`models.py: is_locked`)
- Pott-Anmeldung (`/profil`) ebenfalls gesperrt sobald das erste Spiel gesperrt ist (`routes/profil.py: _pool_locked()`)
- Hinweis „Tippschluss: 10 Minuten vor Anpfiff" auf der Tipp-Seite

### Joker
- Jeder Nutzer hat einen einmaligen Joker (verdoppelt Punkte für ein Spiel)
- **Bug-Fix**: Joker-Form darf NICHT in die Tipp-Form verschachtelt sein (HTML5 `form`-Attribut verwenden)
- Joker-Button: `<button form="joker-form-{m.id}">` + externe `<form id="joker-form-{m.id}">`
- `demo_data.py reset` setzt Joker aller Nutzer zurück

### Tipp-Abgabe (`/tipps`)
- Gruppenphase unterteilt in **Spieltag 1/2/3** (Sub-Tabs): Match 1–24 = ST1, 25–48 = ST2, 49–72 = ST3
- Aktiver Spieltag = Spieltag mit nächstem offenem Spiel (`_active_spieltag()` in `routes/tipps.py`)
- Badges auf jeder Spielkarte: **offen** (blau) / **gesperrt** (rot) / **✓ 2:1** (grün, gespeichert) / **Kein Tipp** (gelb)
- Eingabefelder: grüner Rahmen = gespeichert, gelber Rahmen = noch kein Tipp
- POST-Handler gruppiert home+away vor DB-Write (verhindert UNIQUE-Constraint-Fehler)

### Elfmeterschießen
- Bei K.o.-Spielen mit Elfmeterschießen wird der **Penalty-Score** als offizielles Ergebnis gespeichert (z. B. 5:3 n.E.)
- `Match.went_to_penalties` (Boolean) steuert die „n.E."-Anzeige in allen Templates
- Alle drei Punkteregeln (Exakt / Tordiff. / Tendenz) greifen auf den Penalty-Score
- In der K.o.-Phase gibt es immer einen Sieger → Unentschieden-Tipp = 0 Punkte

### Phasenbezeichnungen
- `round32` → **Sechzehntelfinale** (nicht „Round of 32")
- Definiert in `config.py: PHASES` und `routes/spielplan.py: _KO_LABELS`

### Live-Scores
- `results_sync.py` holt alle 5 Min. Daten von football-data.org
- `FINISHED` → DB + Punkte-Neuberechnung
- `IN_PLAY` / `PAUSED` → nur `_live_scores`-Dict (kein DB-Commit, keine Punkte)
- In Templates via `get_live_scores()` (Jinja2-Global aus `deps.py`) abrufbar
- Zeigt roten ● LIVE-Badge mit Minute und Zwischenstand

### Leaderboard
- Tabs: Gesamt / Gruppenphase / K.o.-Phase
- Spalten: Exakt / Tordiff. / Tendenz (aus `standings.py: exact_count` etc.)
- Eigene Zeile wird mit `#1E4E8C` hinterlegt
- Kasse: Gesamttopf + Teilnehmer für alle sichtbar; Eingezahlt + Noch offen nur für Admins

### Statistik (`/stats`)
- Drei Tabs: **Meine Stats** / **Alle Tipper** (Vergleichstabelle) / **Formkurve** (Chart.js)
- Vergleichstabelle sortiert nach Punkten, eigene Zeile hervorgehoben
- Formkurve: eigene Linie durchgezogen, andere gestrichelt

### Spielplan
- Gruppentabellen werden immer angezeigt (auch ohne Ergebnisse, alle Teams mit 0)
- Tabellen berechnet aus `_group_tables()` in `routes/spielplan.py`
- Live-Score-Anzeige in Gruppen- und Bracket-Ansicht
- Ergebnisse mit „n.E." wenn `went_to_penalties = True`

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

### Admin
- Passwort-Reset: Pro Nutzer „Passwort"-Button → aufklappbares Formular → neues Passwort setzen
- Route: `POST /admin/user/{user_id}/reset-password`

### Turnier-Endergebnis (Bonuspunkte Weltmeister/Torschützenkönig)
- `TournamentResult` (id=1) speichert das **tatsächliche** Endergebnis (`champion_team_id`, `top_scorer`, `total_goals`)
- `total_goals` wird automatisch aus den Spielergebnissen berechnet (`scoring.py: update_total_goals()`)
- `champion_team_id` und `top_scorer` müssen **manuell vom Admin** gesetzt werden – ohne diesen Eintrag bleiben die Bonuspunkte für Weltmeister/Torschützenkönig bei 0, egal was Nutzer getippt haben
- Eingabe: `/admin/qualifikation` → Karte „Turnier-Endergebnis" → Route `POST /admin/qualifikation/tournament-result` (ruft danach `recalculate_everything()` auf)
- Zu unterscheiden von `/admin/bonus`: dort werden nur die **Tipps einzelner Nutzer** (`SpecialTip`) erfasst, nicht das tatsächliche Ergebnis

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
- Online: `DATABASE_URL` Umgebungsvariable → Postgres (Render)
- `database.py` konvertiert `postgresql://` automatisch zu `postgresql+psycopg://` (psycopg3)
- Schema-Änderungen: manuell via `ALTER TABLE` oder neu initialisieren (`seed.py`)
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
- Pott-Anmeldung gesperrt sobald das erste Spiel 10 Min. vor Anpfiff ist
