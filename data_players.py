"""
data_players.py
===============
Spieler für die Torschützenkönig-Auswahl – automatisch aus data_squads.py abgeleitet.
Enthält alle Stürmer (ST) und Mittelfeldspieler (ZM) der offiziellen FIFA-Kader.
"""
from __future__ import annotations
from data_squads import SQUADS
from data_teams import GROUPS

# flag_code → deutscher Teamname
_FLAG_TO_NAME: dict[str, str] = {
    code: name_de
    for teams in GROUPS.values()
    for name_de, _name_en, code in teams
}

# Positionen die für den Torschützenkönig relevant sind
_SCORER_POSITIONS = {"ST", "ZM"}

PLAYERS: dict[str, list[tuple[str, str, str]]] = {}

for flag_code, players in SQUADS.items():
    team_name = _FLAG_TO_NAME.get(flag_code)
    if not team_name:
        continue
    scorer_candidates = [
        (p["name"], "ST" if p["pos"] == "ST" else "MF", p.get("note", ""))
        for p in players
        if p["pos"] in _SCORER_POSITIONS and p.get("note") != "verletzt"
    ]
    if scorer_candidates:
        PLAYERS[team_name] = scorer_candidates


def dropdown_options() -> list[str]:
    """Gibt eine sortierte Liste von Dropdown-Strings zurück."""
    opts: list[str] = []
    for team, players in sorted(PLAYERS.items()):
        for name, pos, note in players:
            label = f"{name} ({team}, {pos})"
            if note:
                label += f" · {note}"
            opts.append(label)
    return opts


def option_to_name(option: str) -> str:
    """Extrahiert den Spielernamen aus dem Dropdown-Wert."""
    if "(" in option:
        return option[:option.rfind("(")].strip()
    return option.strip()
