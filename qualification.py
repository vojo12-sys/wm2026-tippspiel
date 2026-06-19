"""
qualification.py
=================
Automatische Erkennung von Gruppensieger/-zweitem und den acht besten
Drittplatzierten, sobald sie rechnerisch feststehen – auch bevor eine
Gruppe komplett durchgespielt ist.

Clinch-Logik (Gruppensieger/-zweiter): rein punktebasiert. Ein Team gilt
als sicher in einem Platz, wenn niemand anderes diesen Platz noch
einholen kann, selbst wenn er/sie alle Restspiele gewinnt. Das ist
wasserdicht (Tordifferenz kann theoretisch durch beliebig hohe Siege noch
drehen, Punkte nicht) – erkennt manche Fälle aber etwas später, als es
ein Tordifferenz-Vergleich theoretisch könnte. Bewusst in Kauf genommen:
lieber spät und richtig als früh und falsch. Siehe
docs/superpowers/specs/2026-06-20-auto-qualifikation-design.md.

Gruppensieger und -zweiter werden UNABHÄNGIG voneinander ermittelt: ein
klarer Gruppensieger kann feststehen, auch wenn der Kampf um Platz 2
noch offen ist (genau der Fall, den dieses Feature abdecken soll).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Match, Team

_MATCHES_PER_TEAM = 3  # Round-Robin zu 4 Teams je Gruppe


@dataclass
class TeamStanding:
    team_id: int
    name: str
    points: int = 0
    goal_diff: int = 0
    goals_for: int = 0
    played: int = 0
    remaining: int = _MATCHES_PER_TEAM


def _sort_key(st: TeamStanding):
    return (-st.points, -st.goal_diff, -st.goals_for, st.name)


def compute_group_table(session: Session, group_letter: str) -> list[TeamStanding]:
    """Tabelle einer Gruppe aus den bereits beendeten Spielen (Live-
    Zwischenstände zählen bewusst nicht – nur abgeschlossene Ergebnisse)."""
    teams = session.scalars(select(Team).where(Team.group_letter == group_letter)).all()
    standings = {t.id: TeamStanding(team_id=t.id, name=t.name) for t in teams}

    matches = session.scalars(
        select(Match).where(Match.phase == "group", Match.group_letter == group_letter)
    ).all()
    for m in matches:
        if not m.has_result or m.home_team_id not in standings or m.away_team_id not in standings:
            continue
        home, away = standings[m.home_team_id], standings[m.away_team_id]
        home.played += 1
        away.played += 1
        home.goals_for += m.result_home
        away.goals_for += m.result_away
        home.goal_diff += m.result_home - m.result_away
        away.goal_diff += m.result_away - m.result_home
        if m.result_home > m.result_away:
            home.points += 3
        elif m.result_home < m.result_away:
            away.points += 3
        else:
            home.points += 1
            away.points += 1

    for st in standings.values():
        st.remaining = _MATCHES_PER_TEAM - st.played

    return sorted(standings.values(), key=_sort_key)


def _clinched_winner(table: list[TeamStanding], all_done: bool) -> int | None:
    if all_done:
        return table[0].team_id

    def max_possible(st: TeamStanding) -> int:
        return st.points + 3 * st.remaining

    for st in table:
        if all(max_possible(o) < st.points for o in table if o.team_id != st.team_id):
            return st.team_id
    return None


def _clinched_runner_up(table: list[TeamStanding], winner_id: int, all_done: bool) -> int | None:
    rest = [st for st in table if st.team_id != winner_id]

    if all_done:
        return rest[0].team_id

    def max_possible(st: TeamStanding) -> int:
        return st.points + 3 * st.remaining

    for st in rest:
        others = [o for o in rest if o.team_id != st.team_id]
        if all(max_possible(o) < st.points for o in others):
            return st.team_id
    return None


def clinched_from_table(table: list[TeamStanding]) -> tuple[int | None, int | None]:
    """Reine Entscheidungslogik ohne DB-Zugriff (gut testbar). Gibt
    (team_id_1st, team_id_2nd) zurück; jeweils None, wenn (noch) nicht
    sicher feststellbar."""
    table = sorted(table, key=_sort_key)
    if len(table) < 2:
        return None, None

    all_done = all(st.remaining == 0 for st in table)
    winner = _clinched_winner(table, all_done)
    if winner is None:
        return None, None
    runner_up = _clinched_runner_up(table, winner, all_done)
    return winner, runner_up


def clinched_winner_and_runner_up(session: Session, group_letter: str) -> tuple[int | None, int | None]:
    return clinched_from_table(compute_group_table(session, group_letter))


from data_teams import GROUPS
from database import get_session
from knockout import get_thirds_state, propagate, set_third_slot, third_place_slots
from models import GroupResult


def third_place_candidates(
    session: Session, results: dict[str, GroupResult] | None = None
) -> dict[str, TeamStanding]:
    """{Gruppenbuchstabe: TeamStanding des Dritten} – nur für Gruppen, die
    bereits Sieger UND Zweiten feststehen haben. Leeres Dict, solange nicht
    alle 12 Gruppen entschieden sind."""
    if results is None:
        results = {gr.group_letter: gr for gr in session.scalars(select(GroupResult)).all()}

    candidates: dict[str, TeamStanding] = {}
    for letter in GROUPS.keys():
        gr = results.get(letter)
        if not gr or gr.actual_1st is None or gr.actual_2nd is None:
            return {}
        table = compute_group_table(session, letter)
        third = next(
            (st for st in table if st.team_id not in (gr.actual_1st, gr.actual_2nd)), None
        )
        if third:
            candidates[letter] = third
    return candidates


def _match_thirds_to_slots(
    qualified: dict[str, int], slots: list[tuple[int, list[str]]]
) -> dict[int, int]:
    """Verteilt die qualifizierten Dritten (Gruppe -> team_id) per
    Backtracking auf die K.o.-Slots, deren erlaubte Gruppen-Liste eine der
    qualifizierten Gruppen enthält (8 Slots – trivial schnell). Gibt {}
    zurück, wenn keine gültige Zuordnung existiert."""
    used_groups: set[str] = set()
    assignment: dict[int, str] = {}

    def backtrack(i: int) -> bool:
        if i == len(slots):
            return True
        match_no, allowed = slots[i]
        for letter in allowed:
            if letter in qualified and letter not in used_groups:
                used_groups.add(letter)
                assignment[match_no] = letter
                if backtrack(i + 1):
                    return True
                used_groups.remove(letter)
                del assignment[match_no]
        return False

    if not backtrack(0):
        return {}
    return {match_no: qualified[letter] for match_no, letter in assignment.items()}


def _assign_best_thirds(session: Session, results: dict[str, GroupResult]) -> None:
    candidates = third_place_candidates(session, results)
    if len(candidates) < 12:
        return

    ranked_letters = sorted(candidates, key=lambda l: _sort_key(candidates[l]))
    qualified = {letter: candidates[letter].team_id for letter in ranked_letters[:8]}

    state = get_thirds_state()
    assignment = _match_thirds_to_slots(qualified, third_place_slots())
    for match_no, team_id in assignment.items():
        if state.get(match_no, {}).get("manual"):
            continue
        set_third_slot(match_no, team_id, manual=False)


def update_qualifications() -> None:
    """Hauptfunktion: berechnet Gruppensieger/-zweite (sofern nicht
    manuell überschrieben), danach – falls alle 12 Gruppen entschieden
    sind – die acht besten Dritten, und trägt alles in die K.-o.-Spiele
    ein. Idempotent, beliebig oft aufrufbar."""
    with get_session() as session:
        results = {gr.group_letter: gr for gr in session.scalars(select(GroupResult)).all()}
        for letter in GROUPS.keys():
            gr = results.get(letter)
            if gr is None:
                gr = GroupResult(group_letter=letter)
                session.add(gr)
                results[letter] = gr
            if gr.manual_1st and gr.manual_2nd:
                continue
            winner, runner_up = clinched_winner_and_runner_up(session, letter)
            if not gr.manual_1st and winner is not None:
                gr.actual_1st = winner
            if not gr.manual_2nd and runner_up is not None:
                gr.actual_2nd = runner_up

        _assign_best_thirds(session, results)

    propagate()
