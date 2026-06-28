"""
config.py
=========
Zentrale Konfiguration für das WM-2026-Tippspiel.

Alle Werte hier sind STANDARDWERTE. Zur Laufzeit können sie über die
Settings-Tabelle in der Datenbank überschrieben werden (Admin-Ansicht),
ohne dass Code angefasst werden muss. Siehe settings.py / get_setting().

Punktesystem, Kassen-Modell und Auszahlungsschlüssel sind damit
vollständig anpassbar – wie mit Wolfgang besprochen.
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Turnier-Eckdaten
# ---------------------------------------------------------------------------

TOURNAMENT_NAME = "FIFA WM 2026"
TOTAL_MATCHES = 104

# Anzeige-Zeitzone für die Teilnehmer (Kickoffs werden intern in UTC
# gespeichert und nur für die Anzeige umgerechnet).
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")

# Deadline für die Langfrist-Tipps (Weltmeister, Torschützenkönig,
# Gesamttore, Gruppen-Platzierungen): Anpfiff des Eröffnungsspiels.
# Mexiko – Südafrika, 11.06.2026, 15:00 ET (EDT = UTC-4) = 19:00 UTC = 21:00 MESZ
TOURNAMENT_START_UTC = "2026-06-11T19:00:00+00:00"

# flagcdn-Bildgröße (laut Prompt: w320)
FLAG_SIZE = "w320"
FLAG_BASE_URL = "https://flagcdn.com"  # -> {base}/{size}/{code}.png


# ---------------------------------------------------------------------------
# Punktesystem (Standardwerte – per Admin überschreibbar)
# ---------------------------------------------------------------------------

DEFAULT_SCORING = {
    # --- Spiel-Tipps (Ergebnis) ---
    "exact": 4,            # exaktes Ergebnis
    "goal_diff": 2,        # richtige Tordifferenz (nicht exakt)
    "tendency": 1,         # richtige Tendenz (Sieger / Unentschieden)
    # --- Gruppen-Platzierungen (Bonus Tipps) ---
    "group_first": 3,           # richtiger Gruppensieger (exakt 1. Platz)
    "group_second": 3,          # richtiger Gruppenzweiter (exakt 2. Platz)
    "group_partial_credit": 2,  # Team korrekt im Top-2, aber falsche Position

    # --- Sonder-Tipps (Langfrist) ---
    "champion": 15,        # Weltmeister
    "top_scorer": 10,      # Torschützenkönig
    "total_goals": 5,      # Gesamttore-Tipp (innerhalb Toleranz)
    "total_goals_tolerance": 5,  # +/- erlaubte Abweichung für die Punkte
}


# ---------------------------------------------------------------------------
# Kasse / Geld-Pool (Standardwerte – per Admin überschreibbar)
# ---------------------------------------------------------------------------
#
# Modell (mit Wolfgang abgestimmt):
#  - Geld setzen ist FREIWILLIG (Opt-in pro Teilnehmer).
#  - Alle spielen in der sportlichen Gesamtwertung mit, egal ob sie setzen.
#  - Der Topf wird NUR unter den Einzahlern aufgeteilt, nach deren
#    Platzierung innerhalb der Zahler-Gruppe.
#  - Empfehlung: einheitlicher Buy-in (faire, eindeutige Aufteilung).
#  - Die App VERBUCHT das Geld nur (wer hat gezahlt, wie groß ist der Topf,
#    wer bekommt was) – das echte Geld fließt offline.

DEFAULT_POOL = {
    "enabled": True,
    "buy_in": 20.0,
    "currency": "EUR",
    # Gestufte Auszahlung je nach Anzahl Einzahler:
    #   bis 14 Einzahler  → Top 3  (60/30/10 %)
    #   15–19 Einzahler   → Top 4  (50/25/15/10 %)
    #   ab 20 Einzahler   → Top 5  (40/25/20/10/5 %)
    "payout_tiers": {
        "3": [0.60, 0.30, 0.10],
        "4": [0.50, 0.25, 0.15, 0.10],
        "5": [0.40, 0.25, 0.20, 0.10, 0.05],
    },
    # Schwellenwerte: ab X Einzahler gilt die nächste Stufe
    "tier_thresholds": [15, 20],   # [ab_4_plätze, ab_5_plätze]
}

DEFAULT_RULES = """Willkommen beim WM 2026 Tippspiel der LEW Automotive!

**Spielprinzip**
Tippe auf die Ergebnisse aller 104 WM-Spiele. Je genauer dein Tipp, desto mehr Punkte bekommst du.

**Tippsperre**
Tipps werden 10 Minuten vor dem jeweiligen Anpfiff automatisch gesperrt. Danach ist keine Änderung mehr möglich. Bitte gib deinen Tipp rechtzeitig ab!

**Punktesystem (Spiel-Tipps)**
- Exaktes Ergebnis: {exact} Punkte
- Richtige Tordifferenz: {goal_diff} Punkte
- Richtige Tendenz (Sieg/Unentschieden/Niederlage): {tendency} Punkte

**Bonus Tipps (vor Turnierstart)**
- Weltmeister: {champion} Punkte
- Torschützenkönig: {top_scorer} Punkte
- Team richtig auf Position (1. oder 2. Platz): {group_first} Punkte je Gruppe
- Team richtig Top-2, aber auf falscher Position: {group_partial_credit} Punkte je Gruppe
- Gesamttore (±{total_goals_tolerance}): {total_goals} Punkte

**Joker**
Jeder Teilnehmer hat einen einmaligen Joker, den er auf genau ein Spiel setzen kann. Der Joker verdoppelt die Punkte für dieses Spiel – egal ob exaktes Ergebnis, Tordifferenz oder Tendenz.
- Der Joker kann nur auf ein noch nicht gesperrtes Spiel gesetzt werden
- Der Joker kann bis 10 Minuten vor dem Anstoß des gewählten Spiels noch geändert werden
- Nach dem Tippschluss des Joker-Spiels ist er unwiderruflich
- Werden im Joker-Spiel 0 Punkte erzielt, bringt der Joker ebenfalls 0 Punkte

**Gleichstand / Tiebreaker**
Bei gleicher Punktzahl entscheiden folgende Kriterien in dieser Reihenfolge:
- 1. Anzahl der exakt getippten Ergebnisse
- 2. Anzahl der richtig getippten Tordifferenzen
- 3. Anzahl der richtig getippten Tendenzen

**Verlängerung & Elfmeterschießen**
Ab dem Sechzehntelfinale gilt bei Unentschieden nach 90 Minuten: zuerst 2 × 15 Minuten Verlängerung, danach bei Bedarf Elfmeterschießen. In der Gruppenphase gibt es weder Verlängerung noch Elfmeterschießen – ein Remis bleibt ein Remis.
- Gewertet wird das Ergebnis nach 90 Minuten + Verlängerung (offizielle FIFA-Regelung)
- Tore aus dem Elfmeterschießen zählen nicht – weder für den Spieltipp noch für den Gesamttore-Bonus
- Beispiel: Ein Spiel endet 1:1 nach Verlängerung, dann 5:3 n.E. → Wertung als 1:1 (n.E.) – wer 1:1 tippt, bekommt das exakte Ergebnis
- Das Ergebnis wird als "1:1 n.E." angezeigt, um das Elfmeterschießen als Entscheidung kenntlich zu machen
- In der K.o.-Phase gibt es immer einen Sieger – wer auf Unentschieden tippt, bekommt 0 Punkte

**Gesamttore (Bonus Tipp)**
Die Gesamtanzahl aller Turniertore wird nach offizieller FIFA-Zählweise ermittelt: Es zählen alle Tore aus der regulären Spielzeit (90 Min.) und der Verlängerung. Tore aus dem Elfmeterschießen zählen nicht. Eigentore werden normal mitgezählt. Der aktuelle Stand wird automatisch nach jedem Spieltag aktualisiert.

**Kasse**
Die Teilnahme am Tippspiel ist kostenlos. Wer möchte, kann freiwillig {buy_in} € in den Pott einzahlen. Der Pott wird unter den zahlenden Tippern aufgeteilt – nach ihrer Platzierung untereinander. Nicht-Zahler können das Tippspiel sportlich gewinnen, erhalten aber kein Geld.

**So zahlst du ein**
1. Melde dich unter "Profil" für den Pott an (Toggle "Ich möchte am Pott teilnehmen")
2. Gib {buy_in} € bar beim Organisator ab
3. Der Admin bestätigt deine Einzahlung – danach erscheinst du in der Kassen-Übersicht

Bei Fragen wende dich an den Organisator.
"""


# ---------------------------------------------------------------------------
# Datenbank-Verbindung
# ---------------------------------------------------------------------------
#
# Lokal (Entwicklung):  SQLite-Datei -> keine Einrichtung nötig.
# Online (Produktion):  Postgres/Supabase -> DATABASE_URL als Umgebungs-
#                       variable setzen (.env oder Streamlit-Secrets).
#
# Beispiel Supabase:
#   DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:6543/postgres
#
# Wird keine DATABASE_URL gefunden, wird automatisch SQLite verwendet.

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///wm2026.db")


# ---------------------------------------------------------------------------
# Phasen des Turniers (interne Schlüssel -> Anzeigename)
# ---------------------------------------------------------------------------

PHASES = {
    "group": "Gruppenphase",
    "round32": "Sechzehntelfinale",
    "round16": "Achtelfinale",
    "quarter": "Viertelfinale",
    "semi": "Halbfinale",
    "third_place": "Spiel um Platz 3",
    "final": "Finale",
}

# Reihenfolge der K.-o.-Phasen (für das stufenweise Freischalten der Tipps)
KO_PHASE_ORDER = ["round32", "round16", "quarter", "semi", "third_place", "final"]
