"""
test_qualification.py
======================
Eigenständiges Test-Skript (kein pytest im Projekt) für die
Clinch-Erkennung in qualification.py.

Ausführen mit: python test_qualification.py
"""

from qualification import TeamStanding, clinched_from_table


def _team(team_id, name, points, goal_diff=0, goals_for=0, remaining=0):
    return TeamStanding(
        team_id=team_id, name=name, points=points,
        goal_diff=goal_diff, goals_for=goals_for, remaining=remaining,
    )


def test_frueher_in_der_gruppe_nichts_entschieden():
    table = [
        _team(1, "A", points=0, remaining=3),
        _team(2, "B", points=0, remaining=3),
        _team(3, "C", points=0, remaining=3),
        _team(4, "D", points=0, remaining=3),
    ]
    winner, runner_up = clinched_from_table(table)
    assert (winner, runner_up) == (None, None), (winner, runner_up)
    print("OK: test_frueher_in_der_gruppe_nichts_entschieden")


def test_sieger_klar_platz_2_noch_offen():
    # A: 2 Siege (6 Pkt), kann von niemandem mehr eingeholt werden.
    # B/C/D liegen so dicht beieinander, dass Platz 2 noch offen ist.
    table = [
        _team(1, "A", points=6, remaining=1),
        _team(2, "B", points=2, remaining=1),
        _team(3, "C", points=1, remaining=1),
        _team(4, "D", points=0, remaining=1),
    ]
    winner, runner_up = clinched_from_table(table)
    assert winner == 1, winner
    assert runner_up is None, runner_up
    print("OK: test_sieger_klar_platz_2_noch_offen")


def test_sieger_und_platz_2_beide_klar_vor_gruppenende():
    # A hat alle 3 Spiele gespielt und uneinholbar viele Punkte.
    # B hat noch 1 Spiel offen, kann aber von C/D nicht mehr eingeholt werden.
    table = [
        _team(1, "A", points=9, remaining=0),
        _team(2, "B", points=4, remaining=1),
        _team(3, "C", points=0, remaining=1),
        _team(4, "D", points=0, remaining=1),
    ]
    winner, runner_up = clinched_from_table(table)
    assert winner == 1, winner
    assert runner_up == 2, runner_up
    print("OK: test_sieger_und_platz_2_beide_klar_vor_gruppenende")


def test_gruppe_komplett_klare_reihenfolge():
    table = [
        _team(1, "A", points=9, remaining=0),
        _team(2, "B", points=6, remaining=0),
        _team(3, "C", points=3, remaining=0),
        _team(4, "D", points=0, remaining=0),
    ]
    winner, runner_up = clinched_from_table(table)
    assert (winner, runner_up) == (1, 2), (winner, runner_up)
    print("OK: test_gruppe_komplett_klare_reihenfolge")


def test_gruppe_komplett_gleichstand_per_tordifferenz_entschieden():
    # A und B beide 6 Punkte, A hat die bessere Tordifferenz.
    table = [
        _team(1, "A", points=6, goal_diff=5, goals_for=7, remaining=0),
        _team(2, "B", points=6, goal_diff=2, goals_for=4, remaining=0),
        _team(3, "C", points=3, remaining=0),
        _team(4, "D", points=0, remaining=0),
    ]
    winner, runner_up = clinched_from_table(table)
    assert (winner, runner_up) == (1, 2), (winner, runner_up)
    print("OK: test_gruppe_komplett_gleichstand_per_tordifferenz_entschieden")


if __name__ == "__main__":
    test_frueher_in_der_gruppe_nichts_entschieden()
    test_sieger_klar_platz_2_noch_offen()
    test_sieger_und_platz_2_beide_klar_vor_gruppenende()
    test_gruppe_komplett_klare_reihenfolge()
    test_gruppe_komplett_gleichstand_per_tordifferenz_entschieden()
    print("\nAlle Tests bestanden.")
