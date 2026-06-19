# Design: Automatische KO-Qualifikation & Live-Bonus-Punkte

**Datum:** 2026-06-20
**Status:** Genehmigt

---

## Problem

`GroupResult.actual_1st` / `actual_2nd` (wer als Gruppensieger/-zweiter gilt)
wird aktuell **nirgends automatisch gesetzt**. Das hat zwei Auswirkungen:

1. **Bonus-Tipps bleiben bei 0 Punkten.** `scoring.recalculate_group_predictions()`
   wird zwar bei jedem Ergebnis-Sync aufgerufen, findet aber immer `None` und
   vergibt deshalb nie Punkte für Gruppensieger-Tipps.
2. **K.o.-Spiele bleiben auf Platzhaltern stehen** ("Sieger Gruppe A" statt
   z. B. "Mexiko"), weil `knockout.propagate()` nirgends im Live-Betrieb
   aufgerufen wird – nur in `demo_data.py` für Testdaten.

Ziel: Sobald ein Team rechnerisch sicher Gruppensieger oder -zweiter ist –
auch bevor die Gruppe komplett durchgespielt ist – soll das automatisch
erkannt, in die Bonus-Tipp-Wertung übernommen und in die K.o.-Paarungen
eingetragen werden.

---

## Entwurfsentscheidungen

### Clinch-Erkennung nur über Punkte

Eine "mathematisch sichere" Platzierung lässt sich bei Punktgleichstand nie
zu 100 % über Tordifferenz/Tore entscheiden, solange noch Spiele offen sind
(ein beliebig hoher Sieg kann die Tordifferenz immer noch drehen). Die
Clinch-Logik prüft deshalb **ausschließlich Punkte**:

> Ein Team T ist sicher in den Top 2, wenn höchstens ein anderes Team der
> Gruppe noch genug Punkte aus seinen Restspielen holen kann, um T's
> aktuelle Punktzahl zu erreichen oder zu übertreffen.
>
> T ist sicher **Gruppensieger**, wenn **kein** anderes Team das noch kann.

Das ist wasserdicht, erkennt aber manche Fälle etwas später als ein
Tordifferenz-Vergleich es theoretisch könnte. Bewusster Kompromiss:
Korrektheit vor Frühzeitigkeit.

Wenn zwei Teams beide sicher Top-2 sind, aber die Reihenfolge der beiden
zueinander (wer 1., wer 2.) noch nicht über reine Punkte entschieden ist,
wird **noch nichts eingetragen** – die KO-Paarung hängt von 1A vs. 2A ab,
ein falscher Code wäre schlimmer als Warten.

### Beste 8 Dritte: erst wenn alle 12 Gruppen fertig sind

Welche Drittplatzierten zu den besten 8 zählen, hängt von allen 12 Gruppen
gleichzeitig ab. Eine frühzeitige Erkennung ist in der Praxis so gut wie nie
zuverlässig möglich. Diese Zuordnung wird deshalb erst berechnet, sobald
**jede** Gruppe ihren Sieger und Zweiten feststehen hat (impliziert: alle
Gruppenspiele beendet).

### Tiebreaker bleiben vereinfacht

Tabellenberechnung bleibt wie bisher: Punkte → Tordifferenz → Tore → Name.
Kein direkter Vergleich (Head-to-Head), keine Fair-Play-Punkte, keine
Auslosung. Für den seltenen Fall, dass das von der offiziellen FIFA-Reihung
abweicht, gibt es den Admin-Override (s. u.).

---

## Architektur

### Neues Modul `qualification.py`

- `compute_group_table(group_letter) -> list[TeamStanding]`
  Tabellenzeilen inkl. `remaining_matches` (Anzahl noch nicht beendeter
  Gruppenspiele dieses Teams). Faktorisiert aus der bestehenden Logik in
  `routes/spielplan.py:_group_tables`, sodass beide Stellen dieselbe
  Berechnung verwenden (kein doppelter Code).

- `clinched_winner_and_runner_up(group_letter) -> tuple[int | None, int | None]`
  Wendet die Punkte-Clinch-Logik an, gibt `(team_id_1st, team_id_2nd)` oder
  `(None, None)` zurück, wenn noch nicht entschieden.

- `update_qualifications() -> None`
  1. Für jede Gruppe ohne `manual_1st`/`manual_2nd`: Clinch prüfen, ggf.
     `GroupResult.actual_1st`/`actual_2nd` setzen.
  2. Wenn für alle 12 Gruppen `actual_1st` UND `actual_2nd` gesetzt sind:
     beste 8 Drittplatzierte berechnen (Punkte → Tordifferenz → Tore → Name,
     gruppenübergreifend) und in `ko_thirds`-Setting schreiben – aber nur für
     Slots, die nicht `"manual": true` sind.
  3. `knockout.propagate()` aufrufen.

### Trigger

Aufruf von `update_qualifications()` in `results_sync.py`, direkt vor
`recalculate_everything()` (gleiche Stelle, an der `if updated > 0:` bereits
greift). Läuft also automatisch bei jedem Sync-Zyklus (alle 5 Min.), sobald
neue Ergebnisse eingetroffen sind. `recalculate_everything()` (insbesondere
`recalculate_group_predictions()`) liest danach die frisch gesetzten
`GroupResult`-Werte und vergibt entsprechend Punkte.

---

## Datenmodell-Änderungen

### `models.py: GroupResult`

Zwei neue Spalten:
```python
manual_1st: Mapped[bool] = mapped_column(default=False)
manual_2nd: Mapped[bool] = mapped_column(default=False)
```
Wenn der Admin `actual_1st`/`actual_2nd` per Hand setzt, wird das jeweilige
Flag `True` – `update_qualifications()` fasst dieses Feld dann nicht mehr an,
bis der Admin wieder auf "Auto" zurückstellt (Flag → `False`, Wert → `None`,
damit es neu berechnet wird).

### `ko_thirds`-Setting (JSON)

Format erweitert von `{match_no: team_id}` auf
`{match_no: {"team_id": int, "manual": bool}}`, damit die automatische
Berechnung manuell gesetzte Slots nicht überschreibt.
`knockout._thirds_assignment()` und `set_thirds_assignment()` entsprechend
anpassen (Lesen/Schreiben des neuen Formats).

---

## Admin-UI

Neuer Abschnitt "KO-Qualifikation" im Admin-Bereich (`templates/admin.html` +
neue Route(n) in `routes/admin.py`):

- **Gruppentabelle (12 Zeilen):** aktueller Sieger/Zweiter (automatisch
  berechnet oder "noch offen"), je ein Dropdown mit allen Teams der Gruppe
  zum manuellen Überschreiben, Button "Zurück auf Auto" pro Gruppe.
- **Dritten-Plätze (8 Slots):** sobald alle Gruppen fertig sind – sonst
  Hinweistext "Noch nicht alle Gruppen abgeschlossen". Gleiches
  Override-Schema wie oben.
- **Button "Jetzt neu berechnen":** ruft `update_qualifications()` manuell
  auf (z. B. nach einer Korrektur oder außerhalb des 5-Minuten-Sync-Takts).

---

## Testing

- Unit-Tests für `clinched_winner_and_runner_up()` mit synthetischen
  Gruppensituationen:
  - Team mit uneinholbarem Punktvorsprung nach Spieltag 2 (1 Restspiel für
    Rivalen, das nicht mehr reicht)
  - Team, das noch von zwei Rivalen theoretisch eingeholt werden kann →
    kein Clinch
  - Zwei Teams beide sicher Top-2, aber Reihenfolge zueinander offen → kein
    Eintrag
  - Exakter Punktgleichstand mit 0 Restspielen → beide Top-2, Reihenfolge
    über bestehenden Tiebreaker (TD/Tore/Name) bestimmt
- Manueller Test über `demo_data.py` (kann bereits Teilspielstände
  simulieren) plus Sichtprüfung auf `/uebersicht` (Bonus-Tipp-Punkte) und
  `/spielplan` (K.o.-Paarungen mit echten Teamnamen statt Platzhaltern).

---

## Out of Scope

- Echte Frühzeitig-Erkennung für die besten 8 Dritten (gruppenübergreifend,
  unverhältnismäßig aufwändig, siehe Entwurfsentscheidungen oben).
- Visuelle "Qualifiziert"-Badges in der Gruppentabelle auf `/spielplan`
  (bewusst nicht gewünscht – die Auswirkung zeigt sich indirekt über
  Bonus-Tipp-Punkte und echte Teamnamen in den K.o.-Spielen).
- Volle FIFA-Tiebreaker-Kette (Head-to-Head, Fair-Play-Punkte,
  Auslosung) – bleibt vereinfacht wie bisher, Admin-Override fängt
  Abweichungen auf.
