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


def test_kein_klarer_sieger_zwei_rivalen_koennen_noch_einholen():
    # A fuehrt mit 4 Punkten, aber B (1 Pkt, 2 Restspiele, max 7) UND
    # C (1 Pkt, 2 Restspiele, max 7) koennen A jeweils noch einholen/ueberholen.
    table = [
        _team(1, "A", points=4, remaining=1),
        _team(2, "B", points=1, remaining=2),
        _team(3, "C", points=1, remaining=2),
        _team(4, "D", points=0, remaining=2),
    ]
    winner, runner_up = clinched_from_table(table)
    assert (winner, runner_up) == (None, None), (winner, runner_up)
    print("OK: test_kein_klarer_sieger_zwei_rivalen_koennen_noch_einholen")


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


def test_match_thirds_to_slots_findet_gueltige_zuordnung():
    from qualification import _match_thirds_to_slots

    qualified = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8}
    slots = [
        (74, ["A", "B", "C", "D", "F"]),
        (77, ["C", "D", "F", "G", "H"]),
        (79, ["C", "E", "F", "H"]),
        (80, ["E", "H"]),
        (81, ["B", "E", "F"]),
        (82, ["A", "E", "H"]),
        (85, ["E", "F", "G"]),
        (87, ["D", "E"]),
    ]
    assignment = _match_thirds_to_slots(qualified, slots)
    assert len(assignment) == 8, assignment
    assert len(set(assignment.values())) == 8, "jede Gruppe darf nur einmal vorkommen"
    for match_no, allowed in slots:
        letter = next(l for l, tid in qualified.items() if tid == assignment[match_no])
        assert letter in allowed, f"Slot {match_no}: {letter} nicht erlaubt ({allowed})"
    print("OK: test_match_thirds_to_slots_findet_gueltige_zuordnung")


def test_match_thirds_to_slots_unloesbar_gibt_leeres_dict():
    from qualification import _match_thirds_to_slots

    # Zwei Slots erlauben nur Gruppe A, aber nur eine A-Gruppe ist qualifiziert.
    qualified = {"A": 1, "B": 2}
    slots = [(74, ["A"]), (77, ["A"])]
    assignment = _match_thirds_to_slots(qualified, slots)
    assert assignment == {}, assignment
    print("OK: test_match_thirds_to_slots_unloesbar_gibt_leeres_dict")


if __name__ == "__main__":
    test_frueher_in_der_gruppe_nichts_entschieden()
    test_kein_klarer_sieger_zwei_rivalen_koennen_noch_einholen()
    test_sieger_klar_platz_2_noch_offen()
    test_sieger_und_platz_2_beide_klar_vor_gruppenende()
    test_gruppe_komplett_klare_reihenfolge()
    test_gruppe_komplett_gleichstand_per_tordifferenz_entschieden()
    test_match_thirds_to_slots_findet_gueltige_zuordnung()
    test_match_thirds_to_slots_unloesbar_gibt_leeres_dict()
    print("\nAlle Tests bestanden.")
