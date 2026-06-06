# WM 2026 Tippspiel – Fundament (Block 1)

Datenbankschema, Punkte-Engine und Kassen-Logik für das FIFA-WM-2026-Tippspiel.
Läuft mit **Streamlit** + **SQLAlchemy**; dieselbe Codebasis funktioniert lokal
auf **SQLite** und online auf **Postgres/Supabase**.

## Aufbau

| Datei | Inhalt |
|-------|--------|
| `config.py` | Standardwerte: Punktesystem, Kasse, Turnier-Eckdaten, DB-URL |
| `database.py` | SQLAlchemy-Engine + Session (SQLite **und** Postgres) |
| `models.py` | Komplettes Schema (users, teams, matches, predictions, group_predictions, special_tips, Kasse, Ergebnisse, settings) |
| `settings.py` | Laufzeit-Konfiguration (überschreibt `config.py` per Admin) |
| `scoring.py` | Punkte-Engine: bewertet alle Tipps automatisch nach Ergebniseintrag |
| `standings.py` | Rangliste (alle) + Topf-Berechnung/Auszahlung (nur Einzahler) |
| `auth.py` | Login + sicheres Passwort-Hashing (PBKDF2, ohne Zusatzpaket) |
| `data_teams.py` | Die 48 Teams nach Gruppen, mit Flaggen-Codes |
| `seed.py` | Legt Tabellen an und befüllt die Stammdaten |

## Erste Schritte (lokal)

```bash
pip install -r requirements.txt
python seed.py             # Tabellen anlegen + 48 Teams einspielen
python import_schedule.py  # offiziellen Spielplan laden (104 Spiele)
streamlit run app.py       # Start; beim ersten Mal Admin-Konto anlegen
```

`import_schedule.py` spielt alle 104 Spiele mit echten Anstoßzeiten (Gruppenphase,
ET→UTC umgerechnet) und Spielorten ein und ersetzt die vorläufigen Fixtures.
Die K.-o.-Spiele werden mit Platzhaltern angelegt und über den Admin-Tab
„K.o.-Phase" sowie automatisch nach Ergebniseintrag freigeschaltet.

## Wechsel auf Online-Betrieb (Supabase)

Nur die Verbindungs-URL setzen – **kein Code ändert sich**:

```bash
export DATABASE_URL="postgresql+psycopg://USER:PASS@HOST:6543/postgres"
python seed.py
```

## Das Kassen-Modell (Geld setzen ist freiwillig)

- Alle Teilnehmer spielen in der sportlichen **Gesamtwertung** mit – egal ob sie Geld setzen.
- Wer mitsetzt, markiert das (`in_pool`) und zahlt seinen Einsatz (`buy_in`).
- Der **Topf wird nur unter den Einzahlern** aufgeteilt, nach deren Platzierung
  innerhalb der Zahler-Gruppe.
- Ein Nicht-Zahler kann die Gesamtwertung gewinnen → das Geld geht an den
  bestplatzierten Zahler (wird transparent angezeigt).
- Auszahlungsschlüssel skaliert automatisch mit der Zahl der Einzahler.
- **Die App verbucht nur** – das echte Geld fließt offline.

Punktesystem und Kasse sind über die Admin-Ansicht (settings-Tabelle) frei änderbar.

## Punktesystem (Standard, anpassbar)

| Tipp | Punkte |
|------|--------|
| Exaktes Ergebnis | 4 |
| Richtige Tordifferenz | 3 |
| Richtige Tendenz | 2 |
| K.-o.: richtiges weiterkommendes Team | +1 |
| Gruppensieger korrekt | 3 / Gruppe |
| Gruppenzweiter korrekt | 2 / Gruppe |
| Weltmeister | 15 |
| Torschützenkönig | 10 |
| Gesamttore (±5) | 5 |

## Nächster Schritt (Block 2)

Spielplan-Import: die 104 Spiele mit Anstoßzeiten (UTC) und Veranstaltungsorten,
inklusive der Platzhalter-Logik für die K.-o.-Runde (stufenweises Freischalten).
Danach die Streamlit-Oberfläche („Tipps abgeben", „Langfrist-Tipps", Leaderboard).
