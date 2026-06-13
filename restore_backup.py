"""
restore_backup.py
=================
Importiert das neueste lokale CSV-Backup in die lokale SQLite-DB.
Ersetzt: User, Predictions, GroupPredictions, SpecialTips.
Behaelt: Matches, Teams (werden nicht angefasst).

Ausfuehren:
    python restore_backup.py
"""

import csv
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import delete, select, text

from database import get_session, init_db
from models import GroupPrediction, Prediction, SpecialTip, Team, User

# Neuestes Backup finden
backups = sorted(os.listdir("backup")) if os.path.exists("backup") else []
if not backups:
    print("Kein Backup gefunden.")
    sys.exit(1)

backup_dir = os.path.join("backup", backups[-1])
print(f"Verwende Backup: {backups[-1]}")

# Dummy-Passwort-Hash (PBKDF2, Wert = "test123")
import hashlib, secrets
def _dummy_hash():
    salt = "localtestonly"
    dk = hashlib.pbkdf2_hmac("sha256", b"test123", salt.encode(), 260000)
    return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"

DUMMY_HASH = _dummy_hash()

init_db()

with get_session() as s:

    # Team-Index: name -> id (deutscher Name)
    team_by_name = {t.name: t.id for t in s.scalars(select(Team)).all()}

    # --- 1. Alles loeschen ---
    s.execute(delete(Prediction))
    s.execute(delete(GroupPrediction))
    s.execute(delete(SpecialTip))
    s.execute(delete(User))
    # Auto-Increment zuruecksetzen (SQLite)
    for tbl in ["users", "predictions", "group_predictions", "special_tips"]:
        try:
            s.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tbl}'"))
        except Exception:
            pass
    print("  Tabellen geleert.")

    # --- 2. User importieren ---
    with open(os.path.join(backup_dir, "users.csv"), encoding="utf-8") as f:
        users_csv = list(csv.DictReader(f))

    for row in users_csv:
        u = User(
            id=int(row["id"]),
            username=row["username"],
            display_name=row["display_name"],
            password_hash=DUMMY_HASH,
            is_admin=row["is_admin"] == "True",
            in_pool=row["in_pool"] == "True",
            has_paid=row["has_paid"] == "True",
            stake_amount=float(row["stake_amount"] or 0),
            joker_match_id=int(row["joker_match_id"]) if row["joker_match_id"] else None,
        )
        s.add(u)
    print(f"  {len(users_csv)} User importiert.")

    # --- 3. Predictions importieren ---
    with open(os.path.join(backup_dir, "predictions.csv"), encoding="utf-8") as f:
        preds_csv = list(csv.DictReader(f))

    for row in preds_csv:
        p = Prediction(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            match_id=int(row["match_id"]),
            pred_home=int(row["pred_home"]),
            pred_away=int(row["pred_away"]),
            points_awarded=int(row["points_awarded"] or 0),
        )
        s.add(p)
    print(f"  {len(preds_csv)} Predictions importiert.")

    # --- 4. GroupPredictions importieren ---
    with open(os.path.join(backup_dir, "group_predictions.csv"), encoding="utf-8") as f:
        gp_csv = list(csv.DictReader(f))

    skipped_gp = 0
    for row in gp_csv:
        t1_id = team_by_name.get(row["predicted_1st_name"])
        t2_id = team_by_name.get(row["predicted_2nd_name"])
        if row["predicted_1st_name"] and not t1_id:
            print(f"    WARNUNG: Team nicht gefunden: '{row['predicted_1st_name']}'")
            skipped_gp += 1
            continue
        gp = GroupPrediction(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            group_letter=row["group_letter"],
            predicted_1st=t1_id,
            predicted_2nd=t2_id,
            points_awarded=int(row["points_awarded"] or 0),
        )
        s.add(gp)
    print(f"  {len(gp_csv) - skipped_gp} GroupPredictions importiert ({skipped_gp} übersprungen).")

    # --- 5. SpecialTips importieren ---
    with open(os.path.join(backup_dir, "special_tips.csv"), encoding="utf-8") as f:
        st_csv = list(csv.DictReader(f))

    skipped_st = 0
    for row in st_csv:
        champ_id = team_by_name.get(row["champion_team_name"]) if row["champion_team_name"] else None
        if row["champion_team_name"] and not champ_id:
            print(f"    WARNUNG: Weltmeister-Team nicht gefunden: '{row['champion_team_name']}'")
        st = SpecialTip(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            champion_team_id=champ_id,
            top_scorer=row["top_scorer"] if row["top_scorer"] else None,
            total_goals=int(row["total_goals"]) if row["total_goals"] else None,
            points_awarded=int(row["points_awarded"] or 0),
        )
        s.add(st)
    print(f"  {len(st_csv)} SpecialTips importiert.")

print(f"\nRestore abgeschlossen. Lokales Passwort fuer alle User: 'test123'")
