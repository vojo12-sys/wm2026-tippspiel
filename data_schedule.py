"""
data_schedule.py
================
Offizieller Spielplan der FIFA WM 2026 (Quelle: FIFA-Spielplan, Stand nach
Auslosung + Playoffs). 104 Spiele.

GRUPPENSPIELE: echte Paarungen, Städte, Termine und Anstoßzeiten.
  Alle Zeiten in US-Ostzeit (ET = EDT = UTC-4). Der Import rechnet sie nach UTC.
K.-o.-SPIELE: Termine, Städte und die komplette Zubringer-Struktur
  (welcher Gruppenplatz / welcher Spielsieger in welches Spiel führt).
  HINWEIS: Die Anstoßzeiten der K.-o.-Spiele sind hier vorläufig gesetzt und
  im Admin anpassbar; die Gruppen-Zeiten sind exakt.

Format Gruppenspiel: (nr, gruppe, heim_en, gast_en, stadt, "MM-DD", "HH:MM" ET)
"""

from __future__ import annotations

# Englische Quellnamen, die von unseren Team-Namen (name_en) abweichen:
NAME_ALIASES = {
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "USA": "United States",
}

YEAR = 2026

# ---------------------------------------------------------------------------
# Gruppenphase (Spiele 1–72) – Zeiten in ET
# ---------------------------------------------------------------------------
GROUP_FIXTURES = [
    (1,  "A", "Mexico", "South Africa", "Mexico City", "06-11", "15:00"),
    (2,  "A", "Korea Republic", "Czechia", "Guadalajara", "06-11", "22:00"),
    (3,  "B", "Canada", "Bosnia and Herzegovina", "Toronto", "06-12", "15:00"),
    (4,  "D", "USA", "Paraguay", "Los Angeles", "06-12", "21:00"),
    (5,  "D", "Australia", "Türkiye", "Vancouver", "06-14", "00:00"),
    (6,  "B", "Qatar", "Switzerland", "San Francisco", "06-13", "15:00"),
    (7,  "C", "Brazil", "Morocco", "NY-New Jersey", "06-13", "18:00"),
    (8,  "C", "Haiti", "Scotland", "Boston", "06-13", "21:00"),
    (9,  "E", "Germany", "Curaçao", "Houston", "06-14", "13:00"),
    (10, "F", "Netherlands", "Japan", "Dallas", "06-14", "16:00"),
    (11, "E", "Côte d'Ivoire", "Ecuador", "Philadelphia", "06-14", "19:00"),
    (12, "F", "Sweden", "Tunisia", "Monterrey", "06-14", "22:00"),
    (13, "H", "Spain", "Cabo Verde", "Atlanta", "06-15", "12:00"),
    (14, "G", "Belgium", "Egypt", "Seattle", "06-15", "15:00"),
    (15, "H", "Saudi Arabia", "Uruguay", "Miami", "06-15", "18:00"),
    (16, "G", "Iran", "New Zealand", "Los Angeles", "06-15", "21:00"),
    (17, "I", "France", "Senegal", "NY-New Jersey", "06-16", "15:00"),
    (18, "I", "Iraq", "Norway", "Boston", "06-16", "18:00"),
    (19, "J", "Argentina", "Algeria", "Kansas City", "06-16", "21:00"),
    (20, "J", "Austria", "Jordan", "San Francisco", "06-17", "00:00"),
    (21, "K", "Portugal", "DR Congo", "Houston", "06-17", "13:00"),
    (22, "L", "England", "Croatia", "Dallas", "06-17", "16:00"),
    (23, "L", "Ghana", "Panama", "Toronto", "06-17", "19:00"),
    (24, "K", "Uzbekistan", "Colombia", "Mexico City", "06-17", "22:00"),
    (25, "A", "Czechia", "South Africa", "Atlanta", "06-18", "12:00"),
    (26, "B", "Switzerland", "Bosnia and Herzegovina", "Los Angeles", "06-18", "15:00"),
    (27, "B", "Canada", "Qatar", "Vancouver", "06-18", "18:00"),
    (28, "A", "Mexico", "Korea Republic", "Guadalajara", "06-18", "21:00"),
    (29, "D", "Türkiye", "Paraguay", "San Francisco", "06-19", "23:00"),
    (30, "D", "USA", "Australia", "Seattle", "06-19", "15:00"),
    (31, "C", "Scotland", "Morocco", "Boston", "06-19", "18:00"),
    (32, "C", "Brazil", "Haiti", "Philadelphia", "06-19", "20:30"),
    (33, "F", "Netherlands", "Sweden", "Houston", "06-20", "13:00"),
    (34, "E", "Germany", "Côte d'Ivoire", "Toronto", "06-20", "16:00"),
    (35, "E", "Curaçao", "Ecuador", "Kansas City", "06-20", "20:00"),
    (36, "F", "Tunisia", "Japan", "Monterrey", "06-21", "00:00"),
    (37, "H", "Spain", "Saudi Arabia", "Atlanta", "06-21", "12:00"),
    (38, "G", "Belgium", "Iran", "Los Angeles", "06-21", "15:00"),
    (39, "H", "Uruguay", "Cabo Verde", "Miami", "06-21", "18:00"),
    (40, "G", "New Zealand", "Egypt", "Vancouver", "06-21", "21:00"),
    (41, "J", "Argentina", "Austria", "Dallas", "06-22", "13:00"),
    (42, "I", "France", "Iraq", "Philadelphia", "06-22", "17:00"),
    (43, "I", "Norway", "Senegal", "NY-New Jersey", "06-22", "20:00"),
    (44, "J", "Jordan", "Algeria", "San Francisco", "06-22", "23:00"),
    (45, "K", "Portugal", "Uzbekistan", "Houston", "06-23", "13:00"),
    (46, "L", "England", "Ghana", "Boston", "06-23", "16:00"),
    (47, "L", "Panama", "Croatia", "Toronto", "06-23", "19:00"),
    (48, "K", "Colombia", "DR Congo", "Guadalajara", "06-23", "22:00"),
    (49, "B", "Switzerland", "Canada", "Vancouver", "06-24", "15:00"),
    (50, "B", "Bosnia and Herzegovina", "Qatar", "Seattle", "06-24", "15:00"),
    (51, "C", "Scotland", "Brazil", "Miami", "06-24", "18:00"),
    (52, "C", "Morocco", "Haiti", "Atlanta", "06-24", "18:00"),
    (53, "A", "Czechia", "Mexico", "Mexico City", "06-24", "21:00"),
    (54, "A", "South Africa", "Korea Republic", "Monterrey", "06-24", "21:00"),
    (55, "E", "Ecuador", "Germany", "NY-New Jersey", "06-25", "16:00"),
    (56, "E", "Curaçao", "Côte d'Ivoire", "Philadelphia", "06-25", "16:00"),
    (57, "F", "Japan", "Sweden", "Dallas", "06-25", "19:00"),
    (58, "F", "Tunisia", "Netherlands", "Kansas City", "06-25", "19:00"),
    (59, "D", "Türkiye", "USA", "Los Angeles", "06-25", "22:00"),
    (60, "D", "Paraguay", "Australia", "San Francisco", "06-25", "22:00"),
    (61, "I", "Norway", "France", "Boston", "06-26", "15:00"),
    (62, "I", "Senegal", "Iraq", "Toronto", "06-26", "15:00"),
    (63, "H", "Cabo Verde", "Saudi Arabia", "Houston", "06-26", "20:00"),
    (64, "H", "Uruguay", "Spain", "Guadalajara", "06-26", "20:00"),
    (65, "G", "Egypt", "Iran", "Seattle", "06-26", "23:00"),
    (66, "G", "New Zealand", "Belgium", "Vancouver", "06-26", "23:00"),
    (67, "L", "Panama", "England", "NY-New Jersey", "06-27", "17:00"),
    (68, "L", "Croatia", "Ghana", "Philadelphia", "06-27", "17:00"),
    (69, "K", "Colombia", "Portugal", "Miami", "06-27", "19:30"),
    (70, "K", "DR Congo", "Uzbekistan", "Atlanta", "06-27", "19:30"),
    (71, "J", "Algeria", "Austria", "Kansas City", "06-27", "22:00"),
    (72, "J", "Jordan", "Argentina", "Dallas", "06-27", "22:00"),
]

# ---------------------------------------------------------------------------
# K.-o.-Phase (Spiele 73–104)
# Zubringer-Codes:
#   "1X"  = Sieger Gruppe X        "2X" = Zweiter Gruppe X
#   "3[ABCDF]" = bester Dritter aus einem der genannten Gruppen
#   "W73" = Sieger Spiel 73        "L101" = Verlierer Spiel 101
# (nr, phase, stadt, "MM-DD", "HH:MM" ET vorläufig, heim_code, gast_code)
# ---------------------------------------------------------------------------
KO_FIXTURES = [
    (73, "round32", "Los Angeles", "06-28", "15:00", "2A", "2B"),
    (74, "round32", "Boston", "06-29", "16:30", "1E", "3[ABCDF]"),
    (75, "round32", "Monterrey", "06-29", "21:00", "1F", "2C"),
    (76, "round32", "Houston", "06-29", "13:00", "1C", "2F"),
    (77, "round32", "NY-New Jersey", "06-30", "17:00", "1I", "3[CDFGH]"),
    (78, "round32", "Dallas", "06-30", "13:00", "2E", "2I"),
    (79, "round32", "Mexico City", "06-30", "21:00", "1A", "3[CEFHI]"),
    (80, "round32", "Atlanta", "07-01", "12:00", "1L", "3[EHIJK]"),
    (81, "round32", "San Francisco", "07-01", "20:00", "1D", "3[BEFIJ]"),
    (82, "round32", "Seattle", "07-01", "16:00", "1G", "3[AEHIJ]"),
    (83, "round32", "Toronto", "07-02", "19:00", "2K", "2L"),
    (84, "round32", "Los Angeles", "07-02", "15:00", "1H", "2J"),
    (85, "round32", "Vancouver", "07-02", "23:00", "1B", "3[EFGIJ]"),
    (86, "round32", "Miami", "07-03", "18:00", "1J", "2H"),
    (87, "round32", "Kansas City", "07-03", "21:30", "1K", "3[DEIJL]"),
    (88, "round32", "Dallas", "07-03", "14:00", "2D", "2G"),
    (89, "round16", "Philadelphia", "07-04", "17:00", "W74", "W77"),
    (90, "round16", "Houston", "07-04", "13:00", "W73", "W75"),
    (91, "round16", "NY-New Jersey", "07-05", "16:00", "W76", "W78"),
    (92, "round16", "Mexico City", "07-05", "20:00", "W79", "W80"),
    (93, "round16", "Dallas", "07-06", "15:00", "W83", "W84"),
    (94, "round16", "Seattle", "07-06", "20:00", "W81", "W82"),
    (95, "round16", "Atlanta", "07-07", "12:00", "W86", "W88"),
    (96, "round16", "Vancouver", "07-07", "16:00", "W85", "W87"),
    (97, "quarter", "Boston", "07-09", "16:00", "W89", "W90"),
    (98, "quarter", "Los Angeles", "07-10", "15:00", "W93", "W94"),
    (99, "quarter", "Miami", "07-11", "17:00", "W91", "W92"),
    (100, "quarter", "Kansas City", "07-11", "21:00", "W95", "W96"),
    (101, "semi", "Dallas", "07-14", "15:00", "W97", "W98"),
    (102, "semi", "Atlanta", "07-15", "15:00", "W99", "W100"),
    (103, "third_place", "Miami", "07-18", "17:00", "L101", "L102"),
    (104, "final", "NY-New Jersey", "07-19", "15:00", "W101", "W102"),
]
