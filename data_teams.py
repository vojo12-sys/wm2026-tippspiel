"""
data_teams.py
=============
Die 48 Teilnehmer der FIFA WM 2026 nach Gruppen.

Stand: finale Auslosung vom 5.12.2025 plus die in den Playoffs (26./31.3.2026)
ermittelten letzten sechs Teilnehmer:
  UEFA-Playoffs: Tschechien (A), Bosnien und Herzegowina (B), Türkei (D), Schweden (F)
  Interkontinentale Playoffs: Irak (I), DR Kongo (K)

Format je Eintrag: (deutscher Name, englischer Name, flagcdn-Code)
flagcdn nutzt ISO-3166-1-alpha-2 (klein); Sonderfälle: England=gb-eng, Schottland=gb-sct.
"""

from __future__ import annotations

# group_letter -> Liste der 4 Teams
GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "A": [
        ("Mexiko", "Mexico", "mx"),
        ("Südafrika", "South Africa", "za"),
        ("Südkorea", "South Korea", "kr"),
        ("Tschechien", "Czechia", "cz"),
    ],
    "B": [
        ("Kanada", "Canada", "ca"),
        ("Bosnien und Herzegowina", "Bosnia and Herzegovina", "ba"),
        ("Katar", "Qatar", "qa"),
        ("Schweiz", "Switzerland", "ch"),
    ],
    "C": [
        ("Brasilien", "Brazil", "br"),
        ("Marokko", "Morocco", "ma"),
        ("Haiti", "Haiti", "ht"),
        ("Schottland", "Scotland", "gb-sct"),
    ],
    "D": [
        ("USA", "United States", "us"),
        ("Paraguay", "Paraguay", "py"),
        ("Australien", "Australia", "au"),
        ("Türkei", "Türkiye", "tr"),
    ],
    "E": [
        ("Deutschland", "Germany", "de"),
        ("Curaçao", "Curaçao", "cw"),
        ("Elfenbeinküste", "Ivory Coast", "ci"),
        ("Ecuador", "Ecuador", "ec"),
    ],
    "F": [
        ("Niederlande", "Netherlands", "nl"),
        ("Japan", "Japan", "jp"),
        ("Schweden", "Sweden", "se"),
        ("Tunesien", "Tunisia", "tn"),
    ],
    "G": [
        ("Belgien", "Belgium", "be"),
        ("Ägypten", "Egypt", "eg"),
        ("Iran", "Iran", "ir"),
        ("Neuseeland", "New Zealand", "nz"),
    ],
    "H": [
        ("Spanien", "Spain", "es"),
        ("Kap Verde", "Cape Verde", "cv"),
        ("Saudi-Arabien", "Saudi Arabia", "sa"),
        ("Uruguay", "Uruguay", "uy"),
    ],
    "I": [
        ("Frankreich", "France", "fr"),
        ("Senegal", "Senegal", "sn"),
        ("Irak", "Iraq", "iq"),
        ("Norwegen", "Norway", "no"),
    ],
    "J": [
        ("Argentinien", "Argentina", "ar"),
        ("Algerien", "Algeria", "dz"),
        ("Österreich", "Austria", "at"),
        ("Jordanien", "Jordan", "jo"),
    ],
    "K": [
        ("Portugal", "Portugal", "pt"),
        ("DR Kongo", "DR Congo", "cd"),
        ("Usbekistan", "Uzbekistan", "uz"),
        ("Kolumbien", "Colombia", "co"),
    ],
    "L": [
        ("England", "England", "gb-eng"),
        ("Kroatien", "Croatia", "hr"),
        ("Ghana", "Ghana", "gh"),
        ("Panama", "Panama", "pa"),
    ],
}


def all_teams() -> list[tuple[str, str, str, str]]:
    """Flache Liste: (name_de, name_en, flag_code, group_letter)."""
    out = []
    for letter, teams in GROUPS.items():
        for name_de, name_en, code in teams:
            out.append((name_de, name_en, code, letter))
    return out
