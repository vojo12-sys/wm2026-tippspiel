# WM 2026 Tippspiel

Tippspiel-Webapp zur FIFA-Weltmeisterschaft 2026 (LEW Automotive). Nutzer tippen
alle 104 WM-Spiele, dazu Langfrist-Tipps (Weltmeister, Torschützenkönig,
Gesamttore, Gruppen-Platzierungen). Ergebnisse werden automatisch von
football-data.org synchronisiert und bepunktet; eine freiwillige Kasse verbucht
die Gewinnaufteilung.

> **Turnier abgeschlossen (Juli 2026).** Die WM 2026 ist vorbei, die App läuft im
> Abschlusszustand. Wer die Codebasis für ein neues Turnier (z. B. **EM 2028**)
> wiederverwenden will, findet die vollständige Umstell-Anleitung in
> [`docs/EM2028-Umstellung.md`](docs/EM2028-Umstellung.md).

## Stack

**Python · FastAPI · Jinja2 · SQLAlchemy · Uvicorn** — lokal auf **SQLite**,
online (Render) auf **PostgreSQL**. Dieselbe Codebasis läuft ohne Code-Änderung
auf beiden; es entscheidet allein die `DATABASE_URL`.

## Erste Schritte (lokal)

```bash
pip install -r requirements.txt
python seed.py                                     # DB + Stammdaten anlegen (einmalig)
python import_schedule.py                          # Spielplan laden (104 Spiele)
python -m uvicorn main:app --reload --port 8080    # Start → http://localhost:8080
```

Testdaten zum Ausprobieren:

```bash
python demo_data.py 10       # 10 Spiele + Tipps simulieren
python demo_data.py reset    # Testdaten zurücksetzen (Tipps, Joker, Ergebnisse)
```

`import_schedule.py` spielt alle 104 Spiele mit echten Anstoßzeiten (UTC) und
Spielorten ein. Die K.-o.-Spiele werden mit Platzhaltern angelegt und
automatisch nach jedem Ergebnis-Sync sowie über den Admin-Tab „K.o.-Phase"
freigeschaltet.

## Online-Betrieb (Postgres)

Nur die Verbindungs-URL setzen – **kein Code ändert sich**. `database.py`
konvertiert `postgresql://` automatisch zu `postgresql+psycopg://`:

```bash
export DATABASE_URL="postgresql+psycopg://USER:PASS@HOST:6543/postgres"
python seed.py
python import_schedule.py
```

Produktion läuft auf **Render** (Auto-Deploy bei `git push origin main`).
Details und Betriebs-Hinweise: siehe [`CLAUDE.md`](CLAUDE.md).

## Dateiübersicht (Kern)

| Datei | Inhalt |
|-------|--------|
| `main.py` | FastAPI-App, Router-Registrierung, APScheduler (Ergebnis-Sync alle 5 Min.) |
| `config.py` | Standardwerte: Turnier-Eckdaten, Punktesystem, Kasse, Phasen, DB-URL |
| `settings.py` | Laufzeit-Konfiguration (überschreibt `config.py` per Admin-UI) |
| `models.py` | DB-Schema (User, Match, Prediction, GroupPrediction, SpecialTip, GroupResult, TournamentResult, TopScorer …) |
| `database.py` | SQLAlchemy-Engine + Session-Kontextmanager (SQLite **und** Postgres) |
| `scoring.py` | Punkte-Engine: bewertet alle Tipps automatisch nach Ergebniseintrag |
| `standings.py` | Rangliste (alle) + Topf-Berechnung/Auszahlung (nur Einzahler) |
| `qualification.py` | Automatische Erkennung Gruppensieger/-zweiter + beste Dritte |
| `knockout.py` | K.-o.-Baum: löst Zubringer auf und schaltet Spiele frei |
| `results_sync.py` | football-data.org: Ergebnisse + Live-Scores + Torschützenliste |
| `auth.py` | Login + Passwort-Hashing (PBKDF2) |
| `data_teams.py` · `data_schedule.py` · `data_squads.py` · `data_venues.py` · `data_players.py` | Turnier-Stammdaten (Teams, Spielplan, Kader, Orte, Torschützen-Dropdown) |
| `routes/` | Alle Seiten-Router (Tipps, Leaderboard, Admin, …) |
| `templates/` · `static/` | Jinja2-Templates und Assets |

Die vollständige Projektdokumentation (Routen, Design-System, Implementierungs-
details, Betrieb) steht in [`CLAUDE.md`](CLAUDE.md).

## Punktesystem (Standard, per Admin anpassbar)

| Tipp | Punkte |
|------|--------|
| Exaktes Ergebnis | 4 |
| Richtige Tordifferenz | 2 |
| Richtige Tendenz | 1 |
| Gruppensieger korrekt (exakt 1. Platz) | 3 / Gruppe |
| Gruppenzweiter korrekt (exakt 2. Platz) | 3 / Gruppe |
| Team Top-2, aber falsche Position | 2 / Gruppe |
| Weltmeister | 15 |
| Torschützenkönig | 10 |
| Gesamttore (±5) | 5 |

Ein einmaliger **Joker** verdoppelt die Punkte für genau ein Spiel. In der
K.-o.-Phase gibt es keine Bonusregel fürs „richtige weiterkommende Team" mehr –
gewertet wird ausschließlich das Ergebnis (nach 90 Min. + Verlängerung; das
Elfmeterschießen wird als offizielles Resultat „n.E." gewertet).

## Kassen-Modell (Geld setzen ist freiwillig)

- Alle Teilnehmer spielen in der sportlichen **Gesamtwertung** mit – egal ob sie Geld setzen.
- Wer mitsetzt, markiert das (`in_pool`) und zahlt seinen Einsatz (`buy_in`).
- Der **Topf wird nur unter den Einzahlern** aufgeteilt, nach deren Platzierung
  innerhalb der Zahler-Gruppe.
- Ein Nicht-Zahler kann die Gesamtwertung gewinnen → das Geld geht an den
  bestplatzierten Zahler (wird transparent angezeigt).
- Der Auszahlungsschlüssel skaliert automatisch mit der Zahl der Einzahler.
- **Die App verbucht nur** – das echte Geld fließt offline.

Punktesystem und Kasse sind zur Laufzeit über die Admin-Ansicht (settings-Tabelle)
frei änderbar, ohne Code anzufassen.
