# Wiederverwendung für EM 2028 (und andere Turniere)

Diese App wurde für die **FIFA WM 2026** gebaut. Der Punkte-, Kassen-, Auth-,
Joker- und Live-Sync-Kern ist turnierneutral – austauschen musst du fast nur die
**Turnier-Stammdaten** und ein paar an das WM-Format (48 Teams / 12 Gruppen)
gebundene Konstanten.

Diese Anleitung ist eine **Checkliste**, kein automatischer Umbau. Arbeite sie in
einem neuen Branch ab und teste lokal mit SQLite, bevor du auf Produktion gehst.

---

## 1. Format-Unterschied WM 2026 → EM 2028 auf einen Blick

| | WM 2026 | EM 2028 |
|---|---|---|
| Teams | 48 | 24 |
| Gruppen | 12 (A–L) | 6 (A–F) |
| Teams je Gruppe | 4 | 4 |
| Spiele Gruppenphase | 72 | 36 |
| Spiele gesamt | 104 | 51 |
| Erste K.-o.-Runde | Sechzehntelfinale (`round32`, 32 Teams) | Achtelfinale (`round16`, 16 Teams) |
| Wer kommt weiter | 1., 2. + **8 beste Dritte** | 1., 2. + **4 beste Dritte** |
| Veranstalter | USA/Kanada/Mexiko | Vereinigtes Königreich/Irland |

**Wichtig:** Das WM-Format hat mit den *8 besten Dritten* eine Sonderlogik, die
bei der EM (nur *4 beste Dritte*) fast identisch, aber mit anderen Zahlen
funktioniert. Beide Turniere haben **Gruppen zu 4 Teams** – das vereinfacht
vieles (die Round-Robin-Annahme `3 Spiele je Team` bleibt gültig).

---

## 2. Was **unverändert** bleibt (nicht anfassen)

Diese Bausteine sind turnierneutral und funktionieren ohne Änderung weiter:

- `scoring.py` – Punkte-Engine
- `standings.py` – Rangliste + Kassen-/Topf-Berechnung
- `auth.py` – Login / Passwörter
- `database.py` – DB-Anbindung (SQLite/Postgres)
- Joker-Logik, Tippsperre (10 Min. vor Anpfiff)
- Live-Score-Mechanik in `results_sync.py` (nur der Competition-Code ändert sich, siehe §4)
- Der Großteil der `templates/` und `static/` (nur Beschriftungen/Branding)

Das Punktesystem und die Kasse sind ohnehin zur Laufzeit über die Admin-UI
(settings-Tabelle) anpassbar – dafür ist **kein** Code-Eingriff nötig.

---

## 3. Turnier-Stammdaten austauschen (der größte Block)

Alle folgenden Dateien enthalten reine Daten. Sie werden mit den EM-2028-Daten
neu befüllt. **Struktur beibehalten, nur Inhalt ersetzen.**

| Datei | Was ersetzen |
|---|---|
| `data_teams.py` | Die 24 EM-Teams, gruppiert A–F, mit Flaggen-Codes. `GROUPS`-Dict von A–L auf A–F reduzieren. |
| `data_schedule.py` | Alle 51 EM-Spiele (Kickoff in UTC, Venue, Gruppe). **`KO_FIXTURES`** komplett neu (siehe §5). |
| `data_squads.py` | Offizielle EM-Kader aller 24 Teams. |
| `data_players.py` | Wird aus `data_squads.py` generiert (Torschützenkönig-Dropdown) – nach Aktualisierung von `data_squads.py` neu erzeugen. |
| `data_venues.py` | Die EM-2028-Spielorte (Stadien im UK/Irland) mit Koordinaten. |

> **Encoding:** Diese Dateien enthalten Umlaute/Sonderzeichen. **Immer** mit
> `open(f, encoding='utf-8')` bzw. den Editor-Tools bearbeiten, **nie** mit
> PowerShell `Get-Content`/`Set-Content` (zerstört Umlaute). Bei Batch-Ersetzungen
> ein Python-Script schreiben.

---

## 4. `config.py` – Turnier-Eckdaten

| Konstante | Ändern auf |
|---|---|
| `TOURNAMENT_NAME` | z. B. `"UEFA EM 2028"` |
| `TOTAL_MATCHES` | `51` |
| `TOURNAMENT_START_UTC` | Anpfiff des EM-Eröffnungsspiels (UTC!) – dies ist die Deadline für alle Langfrist-Tipps |
| `DEFAULT_RULES` | Regeltext: „104 WM-Spiele" → „51 EM-Spiele", „Weltmeister" → „Europameister", „Sechzehntelfinale" → „Achtelfinale" |
| `PHASES` | `round32` (Sechzehntelfinale) **entfernen** – die EM startet die K.-o.-Phase mit `round16` (Achtelfinale) |
| `KO_PHASE_ORDER` | `"round32"` aus der Liste entfernen → `["round16", "quarter", "semi", "third_place", "final"]` |
| `DATABASE_URL` | Default-SQLite-Dateiname (`wm2026.db`) optional umbenennen (kosmetisch) |
| `DEFAULT_SCORING` | Punkt „champion" heißt intern gleich, meint aber jetzt den Europameister – Werte bei Bedarf anpassen |

**Achtung EM ohne Spiel um Platz 3:** Bei der EM gibt es traditionell **kein**
Spiel um Platz 3. Wenn das so bleibt, `third_place` aus `PHASES` /
`KO_PHASE_ORDER` und aus den `KO_FIXTURES` entfernen und alle Templates prüfen,
die `third_place` referenzieren.

`results_sync.py` → Konstante `_COMPETITION`: aktuell `"2000"` (FIFA World Cup).
Für die EM den passenden football-data.org-Wettbewerbscode eintragen (EM 2024
war `"2018"`/`EC`; EM 2028 bekommt eine **neue ID** – bei football-data.org
nachschlagen, sobald verfügbar). Prüfe außerdem, ob dein API-Tarif den
Wettbewerb abdeckt.

---

## 5. K.-o.-Baum umbauen (die anspruchsvollste Stelle)

Der K.-o.-Baum wird über **Zubringer-Codes** in `data_schedule.py: KO_FIXTURES`
definiert. Diese Codes werden von `knockout.py` und `qualification.py`
ausgewertet. Code-Format:

- `1A`, `2B` … → Sieger / Zweiter der jeweiligen Gruppe
- `3[ABCD]` → einer der besten Dritten aus einer der genannten Gruppen
- `W49` → Sieger von Spiel 49, `L61` → Verlierer von Spiel 61

**Zu tun:**

1. **`KO_FIXTURES` neu schreiben** – der EM-Baum: 8 Achtelfinale, 4 Viertelfinale,
   2 Halbfinale, 1 Finale (kein Spiel um Platz 3, siehe §4). Verwende die
   offizielle UEFA-Paarungstabelle für die Zuordnung der besten Dritten zu den
   Achtelfinal-Slots (`3[…]`-Codes).

2. **`knockout.py`** – die Regex `r"1[A-L]"` und `r"2[A-L]"` (an **vier**
   Stellen: `placeholder_text()` und `_resolve()`) auf `r"1[A-F]"` bzw.
   `r"2[A-F]"` ändern. Sonst werden EM-Gruppen zwar erkannt (A–F liegt in A–L),
   aber sauberer ist die enge Form. **Pflicht** wird die Änderung, falls ein
   Turnier je >12 Gruppen oder andere Buchstaben nutzt.

3. **`qualification.py`** – die fest verdrahtete **`12`**:
   - `_assign_best_thirds()`: `if len(candidates) < 12:` → `< 6`
   - Die „8 besten Dritten" werden über `ranked_letters[:8]` ausgewählt →
     bei der EM `[:4]`.
   - `third_place_candidates()`: Docstring „alle 12 Gruppen" ist nur Kommentar,
     die Logik nutzt `GROUPS.keys()` – passt sich automatisch an 6 Gruppen an,
     sobald `data_teams.py` reduziert ist.
   - `_MATCHES_PER_TEAM = 3` bleibt (Gruppen zu 4 Teams → Round-Robin = 3 Spiele).

4. **Gegenprüfen:** `test_qualification.py` an das EM-Format anpassen und laufen
   lassen (`python -m pytest test_qualification.py` bzw. `python test_qualification.py`).
   Dieser Test ist deine Absicherung, dass die Qualifikations-Logik stimmt.

---

## 6. Branding / Texte

- `TOURNAMENT_NAME` (§4) zieht sich durch viele Templates.
- Volltextsuche nach `WM`, `2026`, `Weltmeister`, `FIFA`, `Sechzehntelfinale` in
  `templates/`, `config.py`, `routes/` und die Treffer sinngemäß ersetzen
  (`EM`, `2028`, `Europameister`, `UEFA`, `Achtelfinale`).
- Logo/Bilder: `static/img/` (Vereins-/Turnierlogo, Landing-Hintergrund) bei
  Bedarf tauschen.
- **Service-Worker-Cache:** nach CSS/Asset-Änderungen die Version in
  `static/sw.js` hochzählen (`wm2026-vN` → nächste Zahl), sonst sehen Nutzer alte
  Assets.

---

## 7. Datenbank neu aufsetzen

Die WM-2026-Daten (Spiele, Ergebnisse, Tipps) sollen **nicht** mitgenommen
werden. Sauberste Variante: **frische Datenbank**.

```bash
# Lokal (SQLite): alte DB löschen und neu aufbauen
rm wm2026.db            # oder den in config.py gesetzten Dateinamen
python seed.py          # Tabellen + Stammdaten (EM-Teams)
python import_schedule.py   # EM-Spielplan

# Produktion (Postgres): neue leere DB anlegen und dort seeden
export DATABASE_URL="postgresql+psycopg://USER:PASS@HOST:6543/postgres"
python seed.py
python import_schedule.py
```

**Migrations-Scripts** (`migrate_*.py`) im Repo sind historische Einmal-Migrationen
der WM-2026-Produktion (Penalty-Spalten, Prediction-History, Visits …). Bei einer
**frisch geseedeten** DB sind sie **nicht** nötig – `seed.py`/`models.py` legen das
aktuelle Schema direkt an. Sie können als Referenz bleiben.

---

## 8. Deployment-Checkliste (Render)

- Neuen (oder denselben) Render-Service mit **frischer** Postgres-DB verbinden.
- Umgebungsvariablen prüfen: `DATABASE_URL`, `SECRET_KEY`, `FOOTBALL_API_KEY`
  (Wettbewerb muss im API-Tarif enthalten sein), optional `SPORTSDB_API_KEY`.
- `render.yaml` und `requirements.txt` bleiben unverändert nutzbar.
- Erst-Login legt das Admin-Konto an; danach Punktesystem/Kasse in der Admin-UI
  final einstellen.

---

## 9. Abnahme-Checkliste vor dem Live-Gang

- [ ] `config.py`: Name, `TOTAL_MATCHES`, Startdatum, Phasen, `KO_PHASE_ORDER`
- [ ] `data_teams.py`: 24 Teams, Gruppen A–F
- [ ] `data_schedule.py`: 51 Spiele + neuer `KO_FIXTURES`-Baum
- [ ] `data_squads.py` + `data_players.py` neu generiert
- [ ] `data_venues.py`: EM-Stadien
- [ ] `qualification.py`: `12`→`6`, `[:8]`→`[:4]`
- [ ] `knockout.py`: Regex `A-L`→`A-F`
- [ ] `results_sync.py`: `_COMPETITION`-Code für EM
- [ ] Branding/Texte in `templates/` ersetzt, `static/sw.js`-Cache hochgezählt
- [ ] Frische DB geseedet, Spielplan importiert
- [ ] `test_qualification.py` angepasst und grün
- [ ] Lokal durchgeklickt: Tippabgabe, Leaderboard, Admin, K.-o.-Freischaltung
      (mit `demo_data.py` simuliert)

---

## Kurz gesagt

Der **schwierigste** Teil ist der K.-o.-Baum (`KO_FIXTURES` + die drei Zahlen
`12`/`8`/`A-L`). Alles andere ist Daten-Austausch und Suchen-und-Ersetzen. Wenn
Format-Annahmen (Gruppen zu 4 Teams, beste Dritte kommen weiter) gleich bleiben,
ist die Umstellung an einem konzentrierten Arbeitstag machbar.
