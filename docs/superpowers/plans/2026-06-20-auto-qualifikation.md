# Automatische KO-Qualifikation & Live-Bonus-Punkte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sobald ein Team rechnerisch sicher Gruppensieger oder -zweiter ist – auch vor Abschluss der Gruppe – automatisch `GroupResult.actual_1st`/`actual_2nd` setzen, die K.o.-Paarungen befüllen (`knockout.propagate()`) und damit die Bonus-Tipp-Punkte live nachziehen lassen.

**Architecture:** Neues Modul `qualification.py` mit einer rein punktebasierten Clinch-Logik (kein Tordifferenz-Risiko) für Gruppensieger/-zweiten, plus einer gruppenübergreifenden Berechnung der besten 8 Dritten (erst wenn alle 12 Gruppen entschieden sind). `update_qualifications()` wird automatisch nach jedem Ergebnis-Sync aufgerufen und respektiert Admin-Overrides. Ein neuer Admin-Bereich erlaubt manuelles Überschreiben/Zurücksetzen.

**Tech Stack:** Python · FastAPI · SQLAlchemy · SQLite/Postgres · Jinja2 (kein pytest im Projekt – Tests sind eigenständige Skripte nach Vorbild der bestehenden `migrate_*.py`-Konvention)

## Global Constraints

- Clinch-Erkennung für Gruppensieger/-zweiten ausschließlich über Punkte (keine Tordifferenz-Hochrechnung) – siehe `docs/superpowers/specs/2026-06-20-auto-qualifikation-design.md`.
- Beste 8 Dritte werden erst berechnet, wenn alle 12 Gruppen `actual_1st` UND `actual_2nd` gesetzt haben.
- Tiebreaker bleiben vereinfacht: Punkte → Tordifferenz → Tore → Name (kein Head-to-Head, keine Fair-Play-Punkte).
- Admin-Override hat immer Vorrang vor der automatischen Berechnung, bis er explizit zurückgesetzt wird.
- Kein pytest im Projekt – Test-Dateien sind eigenständige `python test_*.py`-Skripte mit `assert` und Konsolen-Output, analog zu den bestehenden `migrate_*.py`-Skripten.
- Encoding: alle Datei-Änderungen mit UTF-8 (kein PowerShell `Get-Content`/`Set-Content` für Dateien mit Umlauten).

---

### Task 1: Datenbank-Migration – `manual_1st`/`manual_2nd` auf `GroupResult`

**Files:**
- Modify: `models.py:235-241` (Klasse `GroupResult`)
- Create: `migrate_qualification.py`

**Interfaces:**
- Produces: `GroupResult.manual_1st: bool`, `GroupResult.manual_2nd: bool` (von allen späteren Tasks gelesen/geschrieben)

- [ ] **Step 1: `GroupResult`-Modell erweitern**

In `models.py`, Zeilen 235-241 ersetzen:

```python
class GroupResult(Base):
    """Endgültige 1./2. Platzierung je Gruppe (automatisch berechnet oder
    vom Admin überschrieben)."""
    __tablename__ = "group_results"

    group_letter: Mapped[str] = mapped_column(String(1), primary_key=True)
    actual_1st: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    actual_2nd: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    # True = Admin hat diesen Platz manuell gesetzt; die automatische
    # Berechnung (qualification.update_qualifications()) fasst ihn dann
    # nicht mehr an, bis der Admin wieder auf "Auto" zurückstellt.
    manual_1st: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    manual_2nd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
```

- [ ] **Step 2: Migrationsskript schreiben**

Create `migrate_qualification.py` (exakt nach dem Muster von `migrate_behavior_stats.py`):

```python
"""
migrate_qualification.py
=========================
Fügt manual_1st/manual_2nd (BOOLEAN DEFAULT false) zur group_results-Tabelle hinzu.

Lokal:      python migrate_qualification.py
Produktion: python migrate_qualification.py "postgresql://..."
"""
import sys, os

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine
from sqlalchemy import text, inspect

with engine.connect() as conn:
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("group_results")]
    dialect = engine.dialect.name
    default = "false" if dialect == "postgresql" else "0"

    for col in ("manual_1st", "manual_2nd"):
        if col not in cols:
            conn.execute(text(
                f"ALTER TABLE group_results ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT {default}"
            ))
            conn.commit()
            print(f"OK – Spalte {col} hinzugefügt.")
        else:
            print(f"Spalte {col} bereits vorhanden – nichts zu tun.")
```

- [ ] **Step 3: Migration lokal ausführen**

Run: `python migrate_qualification.py`
Expected: `OK – Spalte manual_1st hinzugefügt.` und `OK – Spalte manual_2nd hinzugefügt.` (oder „bereits vorhanden“, falls die Tabelle noch leer/neu ist und `init_db()` die Spalten schon über `create_all` angelegt hat – beides ist ein gültiges Ergebnis).

- [ ] **Step 4: Commit**

```bash
git add models.py migrate_qualification.py
git commit -m "feat: manual_1st/manual_2nd auf GroupResult fuer Admin-Override"
```

---

### Task 2: `qualification.py` – Tabellen-Berechnung & Clinch-Logik

**Files:**
- Create: `qualification.py`
- Create: `test_qualification.py`

**Interfaces:**
- Consumes: `models.Team` (`group_letter`, `id`, `name`), `models.Match` (`phase`, `group_letter`, `home_team_id`, `away_team_id`, `has_result`, `result_home`, `result_away`)
- Produces:
  - `TeamStanding` dataclass (`team_id: int`, `name: str`, `points: int`, `goal_diff: int`, `goals_for: int`, `played: int`, `remaining: int`)
  - `compute_group_table(session, group_letter: str) -> list[TeamStanding]`
  - `clinched_from_table(table: list[TeamStanding]) -> tuple[int | None, int | None]`
  - `clinched_winner_and_runner_up(session, group_letter: str) -> tuple[int | None, int | None]`

- [ ] **Step 1: `qualification.py` mit Tabellen-Berechnung und Clinch-Logik anlegen**

Create `qualification.py`:

```python
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
```

- [ ] **Step 2: Test-Skript für die Clinch-Logik schreiben**

Create `test_qualification.py`:

```python
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
```

- [ ] **Step 3: Tests ausführen und Bestehen prüfen**

Run: `python test_qualification.py`
Expected:
```
OK: test_frueher_in_der_gruppe_nichts_entschieden
OK: test_sieger_klar_platz_2_noch_offen
OK: test_sieger_und_platz_2_beide_klar_vor_gruppenende
OK: test_gruppe_komplett_klare_reihenfolge
OK: test_gruppe_komplett_gleichstand_per_tordifferenz_entschieden

Alle Tests bestanden.
```
Falls ein Test fehlschlägt: die `assert`-Meldung zeigt direkt (winner, runner_up) – mit der Tabellen-Logik aus Step 1 abgleichen, nicht den Test ändern, um ihn "passend" zu machen.

- [ ] **Step 4: Commit**

```bash
git add qualification.py test_qualification.py
git commit -m "feat: punktebasierte Clinch-Erkennung fuer Gruppensieger/-zweiten"
```

---

### Task 3: `knockout.py` – Speicherformat der Dritten-Plätze umstellen

**Files:**
- Modify: `knockout.py:48-63` (`_thirds_assignment`, `set_thirds_assignment`)
- Modify: `demo_data.py:217-228` (Schreiben von `ko_thirds`)

**Interfaces:**
- Consumes: `models.Setting`
- Produces:
  - `get_thirds_state() -> dict[int, dict]` (`{match_no: {"team_id": int, "manual": bool}}`)
  - `set_third_slot(match_no: int, team_id: int | None, manual: bool) -> None`
  - `_thirds_assignment() -> dict[int, int]` (unverändertes internes Interface für `propagate()`)

- [ ] **Step 1: Speicherformat in `knockout.py` umstellen**

In `knockout.py`, Zeilen 48-63 ersetzen:

```python
def get_thirds_state() -> dict[int, dict]:
    """Aktueller Zustand der Dritt-Platz-Slots:
    {Spiel-Nr: {"team_id": int, "manual": bool}}."""
    with get_session() as s:
        row = s.get(Setting, "ko_thirds")
        if not row:
            return {}
        return {int(k): v for k, v in json.loads(row.value).items()}


def set_third_slot(match_no: int, team_id: int | None, manual: bool) -> None:
    """Setzt (oder löscht, bei team_id=None) die Zuordnung für einen
    Dritt-Platz-Slot. manual=True markiert eine Admin-Überschreibung, die
    die automatische Berechnung nicht mehr anfasst."""
    with get_session() as s:
        row = s.get(Setting, "ko_thirds")
        state = json.loads(row.value) if row else {}
        if team_id is None:
            state.pop(str(match_no), None)
        else:
            state[str(match_no)] = {"team_id": team_id, "manual": manual}
        payload = json.dumps(state)
        if row:
            row.value = payload
        else:
            s.add(Setting(key="ko_thirds", value=payload))


def _thirds_assignment() -> dict[int, int]:
    """Spiel-Nr -> team_id, für propagate()."""
    return {no: v["team_id"] for no, v in get_thirds_state().items()}
```

- [ ] **Step 2: `demo_data.py` an das neue Speicherformat anpassen**

In `demo_data.py`, Zeilen 217-228 (Block „Beste 8 Dritte >> K.o.-Slots“) ersetzen:

```python
        # ── Beste 8 Dritte >> K.o.-Slots ──────────────────────────
        best = _best_thirds(standings)
        thirds_map = _assign_thirds(best)
        if thirds_map:
            import json
            row = s.get(Setting, "ko_thirds")
            payload = json.dumps({
                str(k): {"team_id": v, "manual": False} for k, v in thirds_map.items()
            })
            if row:
                row.value = payload
            else:
                s.add(Setting(key="ko_thirds", value=payload))
            print(f"\n  {len(thirds_map)} Drittplatzierte den K.o.-Slots zugewiesen.")
```

(Einzige Änderung: `payload` baut jetzt `{"team_id": v, "manual": False}` statt nur `v`.)

- [ ] **Step 3: Manuell prüfen, dass `propagate()` mit dem neuen Format funktioniert**

Run:
```bash
python -c "
from knockout import set_third_slot, _thirds_assignment
set_third_slot(74, 999, manual=True)
print(_thirds_assignment())
set_third_slot(74, None, manual=False)
print(_thirds_assignment())
"
```
Expected: erste Zeile `{74: 999}`, zweite Zeile `{}` (Slot wieder gelöscht). Falls eine alte `ko_thirds`-Row im alten Format (`{"74": 5}` statt `{"74": {...}}`) noch in der lokalen `wm2026.db` liegt, vorher einmal `python demo_data.py reset` ausführen (löscht u. a. die `ko_thirds`-Row).

- [ ] **Step 4: Commit**

```bash
git add knockout.py demo_data.py
git commit -m "feat: Dritten-Slots speichern jetzt Admin-Override-Flag mit"
```

---

### Task 4: `qualification.py` – Beste 8 Dritte & `update_qualifications()`

**Files:**
- Modify: `qualification.py` (ergänzen)
- Modify: `test_qualification.py` (ergänzen)

**Interfaces:**
- Consumes: `knockout.get_thirds_state`, `knockout.set_third_slot`, `knockout.propagate`, `knockout.third_place_slots`, `models.GroupResult`, `data_teams.GROUPS`
- Produces:
  - `third_place_candidates(session, results=None) -> dict[str, TeamStanding]`
  - `update_qualifications() -> None`

- [ ] **Step 1: Cross-Gruppen-Logik und Haupt-Orchestrierung ergänzen**

An `qualification.py` anhängen:

```python
from sqlalchemy.orm import Session as _Session  # bereits oben importiert, hier nur zur Klarheit

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
```

(Die doppelte `Session`-Import-Zeile ist nur ein Kommentar-Hinweis – `Session` ist bereits am Dateianfang aus Task 2 importiert; sie muss nicht erneut importiert werden. Beim Anhängen einfach die Zeile `from sqlalchemy.orm import Session as _Session  # ...` weglassen.)

- [ ] **Step 2: Tests für die Cross-Gruppen-Logik ergänzen**

An `test_qualification.py` anhängen (vor dem `if __name__ == "__main__":`-Block):

```python
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
```

Und im `if __name__ == "__main__":`-Block ergänzen:

```python
    test_match_thirds_to_slots_findet_gueltige_zuordnung()
    test_match_thirds_to_slots_unloesbar_gibt_leeres_dict()
```

- [ ] **Step 3: Tests ausführen**

Run: `python test_qualification.py`
Expected: alle 7 `OK:`-Zeilen plus `Alle Tests bestanden.`

- [ ] **Step 4: Mit der echten DB gegen die tatsächlichen K.o.-Slots prüfen**

Run:
```bash
python -c "
from knockout import third_place_slots
print(third_place_slots())
"
```
Expected: eine Liste von 8 `(match_no, [Gruppenbuchstaben])`-Tupeln (z. B. `(74, ['A','B','C','D','F'])`, ...) – stellt sicher, dass `_match_thirds_to_slots` mit echten Daten aus `data_schedule.py` ebenfalls eine gültige Zuordnung findet (sollte sie, da die WM-2026-Fixture-Liste bewusst lösbar designt ist).

- [ ] **Step 5: Commit**

```bash
git add qualification.py test_qualification.py
git commit -m "feat: gruppenuebergreifende Bestimmung der besten 8 Dritten"
```

---

### Task 5: Automatischer Trigger in `results_sync.py`

**Files:**
- Modify: `results_sync.py:211-219`

**Interfaces:**
- Consumes: `qualification.update_qualifications`

- [ ] **Step 1: `update_qualifications()` vor `recalculate_everything()` einhängen**

In `results_sync.py`, Zeilen 211-219 ersetzen:

```python
    if updated > 0:
        try:
            from qualification import update_qualifications
            from scoring import recalculate_everything, update_total_goals
            from standings import save_all_rank_snapshots
            save_all_rank_snapshots()
            update_qualifications()
            recalculate_everything()
            update_total_goals()
        except Exception as e:
            logger.error("Punkte-Neuberechnung: %s", e)
```

- [ ] **Step 2: Manuell mit Demo-Daten durchspielen**

Run:
```bash
python demo_data.py reset
python demo_data.py 24
python -c "
from qualification import update_qualifications
from scoring import recalculate_everything
update_qualifications()
recalculate_everything()
from database import get_session
from models import GroupResult
from sqlalchemy import select
with get_session() as s:
    for gr in s.scalars(select(GroupResult)).all():
        if gr.actual_1st or gr.actual_2nd:
            print(gr.group_letter, gr.actual_1st, gr.actual_2nd)
"
```
Expected: mindestens eine Zeile mit gesetztem `actual_1st` (manche Gruppen sind nach 2 von 6 simulierten Matchdays oft schon entschieden, andere nicht – `python demo_data.py 24` simuliert die ersten 24 von 72 Gruppenspielen chronologisch über alle 12 Gruppen verteilt, das Ergebnis ist also zufallsabhängig). Wenn gar keine Gruppe etwas zeigt: `python demo_data.py 48` probieren (mehr Spiele simuliert, höhere Wahrscheinlichkeit für eine klare Führung).

- [ ] **Step 3: Demo-Daten zurücksetzen**

Run: `python demo_data.py reset`
Expected: `K.o.-Platzhalter wiederhergestellt.` / `Spielzeiten wiederhergestellt.`

- [ ] **Step 4: Commit**

```bash
git add results_sync.py
git commit -m "feat: automatische KO-Qualifikation nach jedem Ergebnis-Sync"
```

---

### Task 6: Admin-Routen für KO-Qualifikation

**Files:**
- Modify: `routes/admin.py` (Imports + neue Routen anhängen)

**Interfaces:**
- Consumes: `qualification.compute_group_table`, `qualification.third_place_candidates`, `qualification.update_qualifications`, `knockout.third_place_slots`, `knockout.get_thirds_state`, `knockout.set_third_slot`, `models.GroupResult`, `data_teams.GROUPS`
- Produces: `GET /admin/qualifikation`, `POST /admin/qualifikation/group/{letter}`, `POST /admin/qualifikation/thirds/{match_no}`, `POST /admin/qualifikation/recalc`

- [ ] **Step 1: Imports ergänzen**

In `routes/admin.py`, nach Zeile 21 (`from standings import compute_standings`) ergänzen:

```python
from knockout import get_thirds_state, set_third_slot, third_place_slots
from qualification import compute_group_table, third_place_candidates, update_qualifications
```

- [ ] **Step 2: GET-Route für die Übersicht anhängen**

Ans Ende von `routes/admin.py` anhängen:

```python
# ── KO-Qualifikation ─────────────────────────────────────────────────────────

@router.get("/qualifikation")
async def qualifikation_get(request: Request, user: dict = Depends(require_admin)):
    with get_session() as s:
        teams_by_group: dict[str, list[Team]] = {}
        for t in s.scalars(select(Team).order_by(Team.group_letter, Team.name)).all():
            teams_by_group.setdefault(t.group_letter, []).append(t)

        results = {gr.group_letter: gr for gr in s.scalars(select(GroupResult)).all()}
        groups_view = []
        for letter in sorted(GROUPS.keys()):
            gr = results.get(letter)
            groups_view.append({
                "letter": letter,
                "teams": teams_by_group.get(letter, []),
                "actual_1st": gr.actual_1st if gr else None,
                "actual_2nd": gr.actual_2nd if gr else None,
                "manual_1st": gr.manual_1st if gr else False,
                "manual_2nd": gr.manual_2nd if gr else False,
            })

        all_complete = all(g["actual_1st"] and g["actual_2nd"] for g in groups_view)

        thirds_view = []
        if all_complete:
            candidates = third_place_candidates(s)
            state = get_thirds_state()
            for match_no, allowed in third_place_slots():
                options = [(letter, candidates[letter]) for letter in allowed if letter in candidates]
                current = state.get(match_no, {})
                thirds_view.append({
                    "match_no": match_no,
                    "allowed_groups": allowed,
                    "options": options,
                    "team_id": current.get("team_id"),
                    "manual": current.get("manual", False),
                })

    return templates.TemplateResponse(request, "admin_qualifikation.html", {
        "user": user, "active": "admin",
        "groups": groups_view,
        "all_complete": all_complete,
        "thirds": thirds_view,
        "flash": request.session.pop("flash", None),
    })


@router.post("/qualifikation/group/{letter}")
async def qualifikation_save_group(
    request: Request,
    letter: str,
    actual_1st: str = Form(""),
    actual_2nd: str = Form(""),
    user: dict = Depends(require_admin),
):
    with get_session() as s:
        gr = s.get(GroupResult, letter)
        if not gr:
            gr = GroupResult(group_letter=letter)
            s.add(gr)
        if actual_1st:
            gr.actual_1st = int(actual_1st)
            gr.manual_1st = True
        else:
            gr.actual_1st = None
            gr.manual_1st = False
        if actual_2nd:
            gr.actual_2nd = int(actual_2nd)
            gr.manual_2nd = True
        else:
            gr.actual_2nd = None
            gr.manual_2nd = False

    update_qualifications()
    recalculate_everything()
    request.session["flash"] = {"message": f"Gruppe {letter} aktualisiert.", "type": "success"}
    return RedirectResponse("/admin/qualifikation", status_code=303)


@router.post("/qualifikation/thirds/{match_no}")
async def qualifikation_save_third(
    request: Request,
    match_no: int,
    team_id: str = Form(""),
    user: dict = Depends(require_admin),
):
    if team_id:
        set_third_slot(match_no, int(team_id), manual=True)
    else:
        set_third_slot(match_no, None, manual=False)

    update_qualifications()
    recalculate_everything()
    request.session["flash"] = {"message": "Dritten-Platz aktualisiert.", "type": "success"}
    return RedirectResponse("/admin/qualifikation", status_code=303)


@router.post("/qualifikation/recalc")
async def qualifikation_recalc(request: Request, user: dict = Depends(require_admin)):
    update_qualifications()
    recalculate_everything()
    request.session["flash"] = {"message": "Qualifikation neu berechnet.", "type": "success"}
    return RedirectResponse("/admin/qualifikation", status_code=303)
```

- [ ] **Step 3: App startet ohne Importfehler**

Run: `python -c "import routes.admin"`
Expected: kein Traceback (insbesondere kein `ImportError` für `qualification` oder `knockout`).

- [ ] **Step 4: Commit**

```bash
git add routes/admin.py
git commit -m "feat: Admin-Routen fuer KO-Qualifikation (Override + manuelles Neuberechnen)"
```

---

### Task 7: Admin-Template & Navigation

**Files:**
- Create: `templates/admin_qualifikation.html`
- Modify: `templates/admin.html:23` (Button-Leiste)

**Interfaces:**
- Consumes: Kontext aus `qualifikation_get()` (Task 6): `groups`, `all_complete`, `thirds`, `flash`

- [ ] **Step 1: Template anlegen**

Create `templates/admin_qualifikation.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1 class="mb-1">Admin · KO-Qualifikation</h1>
<p class="text-muted mb-4">
  Gruppensieger/-zweiter werden automatisch erkannt, sobald sie rechnerisch
  sicher feststehen (rein punktebasiert). Bei Bedarf hier manuell überschreiben.
</p>

{% if flash %}
<div class="alert alert-{{ flash.type }} alert-dismissible fade show">
  {{ flash.message }}
  <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
{% endif %}

<div class="d-flex justify-content-between align-items-center mb-3">
  <a href="/admin" class="btn btn-outline-secondary btn-sm">← Admin</a>
  <form method="post" action="/admin/qualifikation/recalc">
    <button type="submit" class="btn btn-accent btn-sm">Jetzt neu berechnen</button>
  </form>
</div>

<div class="card border-0 shadow-sm mb-4">
  <div class="card-body">
    <h6 class="fw-bold mb-3">Gruppensieger / -zweiter</h6>
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>Gruppe</th>
            <th>1. Platz</th>
            <th>2. Platz</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for g in groups %}
          <tr>
            <td><strong>{{ g.letter }}</strong></td>
            <td colspan="2">
              <form method="post" action="/admin/qualifikation/group/{{ g.letter }}"
                    class="row g-2 align-items-center">
                <div class="col-5">
                  <select name="actual_1st" class="form-select form-select-sm">
                    <option value="">— Auto —</option>
                    {% for t in g.teams %}
                    <option value="{{ t.id }}" {% if g.actual_1st == t.id %}selected{% endif %}>{{ t.name }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="col-5">
                  <select name="actual_2nd" class="form-select form-select-sm">
                    <option value="">— Auto —</option>
                    {% for t in g.teams %}
                    <option value="{{ t.id }}" {% if g.actual_2nd == t.id %}selected{% endif %}>{{ t.name }}</option>
                    {% endfor %}
                  </select>
                </div>
                <div class="col-2">
                  <button type="submit" class="btn btn-outline-secondary btn-sm w-100">Speichern</button>
                </div>
              </form>
            </td>
            <td>
              {% if g.manual_1st or g.manual_2nd %}
              <span class="badge bg-secondary">manuell</span>
              {% elif g.actual_1st and g.actual_2nd %}
              <span class="badge" style="background:var(--accent-dk)">auto</span>
              {% else %}
              <span class="badge bg-light text-muted">offen</span>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <h6 class="fw-bold mb-3">Beste 8 Dritte</h6>
    {% if not all_complete %}
    <p class="text-muted mb-0">Noch nicht alle Gruppen abgeschlossen.</p>
    {% elif not thirds %}
    <p class="text-muted mb-0">Keine gültige Zuordnung der Dritten zu den K.o.-Slots gefunden.</p>
    {% else %}
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>Spiel</th>
            <th>Erlaubte Gruppen</th>
            <th>Team</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for slot in thirds %}
          <tr>
            <td>#{{ slot.match_no }}</td>
            <td>{{ slot.allowed_groups | join(', ') }}</td>
            <td>
              <form method="post" action="/admin/qualifikation/thirds/{{ slot.match_no }}"
                    class="row g-2 align-items-center">
                <div class="col-8">
                  <select name="team_id" class="form-select form-select-sm">
                    <option value="">— Auto —</option>
                    {% for letter, st in slot.options %}
                    <option value="{{ st.team_id }}" {% if slot.team_id == st.team_id %}selected{% endif %}>
                      {{ st.name }} (Gruppe {{ letter }})
                    </option>
                    {% endfor %}
                  </select>
                </div>
                <div class="col-4">
                  <button type="submit" class="btn btn-outline-secondary btn-sm w-100">Speichern</button>
                </div>
              </form>
            </td>
            <td>
              {% if slot.manual %}<span class="badge bg-secondary">manuell</span>
              {% elif slot.team_id %}<span class="badge" style="background:var(--accent-dk)">auto</span>
              {% else %}<span class="badge bg-light text-muted">offen</span>{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Nav-Button in `admin.html` ergänzen**

In `templates/admin.html`, Zeile 23, direkt nach dem „Bonus Tipps“-Button ergänzen:

```html
    <a href="/admin/bonus" class="btn btn-outline-secondary btn-sm">Bonus Tipps</a>
    <a href="/admin/qualifikation" class="btn btn-outline-secondary btn-sm">KO-Qualifikation</a>
```

- [ ] **Step 3: Manuell im Browser prüfen**

Run: `python -m uvicorn main:app --reload --port 8080`

Im Browser:
1. `http://localhost:8080/admin` öffnen, auf „KO-Qualifikation“ klicken.
2. Prüfen: alle 12 Gruppen werden mit Dropdowns angezeigt, Status-Badge „offen“ (sofern noch keine Demo-Daten simuliert wurden).
3. `python demo_data.py 24` in einem zweiten Terminal ausführen, Seite neu laden – mindestens eine Gruppe sollte jetzt „auto“ mit gesetztem Team zeigen (siehe Task 5, Step 2).
4. Ein Team im Dropdown „1. Platz“ einer Gruppe manuell auswählen, „Speichern“ klicken – Badge wechselt auf „manuell“, Auswahl bleibt nach Reload erhalten.
5. Zurück auf „— Auto —“ stellen und speichern – Badge wechselt zurück auf „auto“ oder „offen“.
6. `python demo_data.py reset` ausführen.

- [ ] **Step 4: Commit**

```bash
git add templates/admin_qualifikation.html templates/admin.html
git commit -m "feat: Admin-UI fuer KO-Qualifikation (Override + Status-Anzeige)"
```

---

### Task 8: End-to-End-Verifikation (vollständiger Turnierverlauf)

**Files:**
- Keine Code-Änderungen – reine Verifikation.

- [ ] **Step 1: Komplette WM simulieren und K.o.-Befüllung prüfen**

Run:
```bash
python demo_data.py reset
python demo_data.py
```
Expected: Ausgabe endet mit `OK Komplette WM simuliert! Alle 104 Spiele, alle Phasen.` ohne Tracebacks. Das bestätigt, dass die in Task 3 geänderte `ko_thirds`-Schreiblogik in `demo_data.py` mit dem neuen Format weiterhin funktioniert und `knockout.propagate()` (über das neue `_thirds_assignment()`) korrekt liest.

- [ ] **Step 2: Bonus-Tipp-Punkte und K.o.-Paarungen im Browser prüfen**

Run: `python -m uvicorn main:app --reload --port 8080`

Im Browser:
1. `http://localhost:8080/uebersicht` → Tab „Bonus Tipps“ – Gruppensieger-Tipps zeigen jetzt Punkte (nicht mehr durchgängig 0).
2. `http://localhost:8080/spielplan` → Sechzehntelfinale-Bracket zeigt echte Teamnamen statt „Sieger Gruppe A“.

- [ ] **Step 3: Teil-Simulation für den eigentlichen Use-Case prüfen (früh erkannte Qualifikation)**

Run:
```bash
python demo_data.py reset
python demo_data.py 40
python -c "
from qualification import update_qualifications
from scoring import recalculate_everything
update_qualifications()
recalculate_everything()
"
```

Im Browser: `http://localhost:8080/admin/qualifikation` öffnen – mehrere Gruppen sollten bereits „auto“ mit gesetztem Sieger zeigen, obwohl die Gruppenphase noch nicht komplett durchgespielt ist (nicht alle 72 Gruppenspiele sind simuliert). Das ist der Kernnutzen dieses Features.

- [ ] **Step 4: Demo-Daten final zurücksetzen**

Run: `python demo_data.py reset`
Expected: `K.o.-Platzhalter wiederhergestellt.` / `Spielzeiten wiederhergestellt.` – Datenbank ist wieder im Ausgangszustand für den echten Turnierbetrieb.

---

## Self-Review

- **Spec-Abdeckung:** Punktebasierte Clinch-Logik (Task 2), Beste-8-Dritte erst bei Komplettierung (Task 4), vereinfachte Tiebreaker (Task 2, `_sort_key`), Admin-Override mit Vorrang (Task 1, 4, 6), automatischer Trigger nach Sync (Task 5), Admin-UI (Task 6/7) – alle Abschnitte der Spec sind abgedeckt.
- **Platzhalter-Scan:** keine TBD/TODO; alle Code-Blöcke sind vollständig copy-paste-fähig.
- **Typkonsistenz:** `TeamStanding`, `compute_group_table`, `clinched_from_table`, `clinched_winner_and_runner_up`, `third_place_candidates`, `update_qualifications`, `get_thirds_state`, `set_third_slot`, `_thirds_assignment` werden in jeder Task identisch benannt und verwendet.
- **Zusätzlich entdeckt und mit eingeplant:** `demo_data.py` schrieb `ko_thirds` bisher im alten Format – ohne Task 3 Step 2 hätte die Formatänderung in Task 3 Step 1 die volle Turnier-Simulation (`python demo_data.py` ohne Argument) für die K.o.-Phase der Dritten gebrochen. Mit Task 8 Step 1 wird das explizit verifiziert.
