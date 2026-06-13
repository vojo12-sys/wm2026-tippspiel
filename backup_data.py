"""
Backup-Script: exportiert alle Tipps und Nutzerdaten als CSV.

Lokal (SQLite):
    python backup_data.py

Remote (Render PostgreSQL):
    python backup_data.py "postgresql://user:pass@host/db"
"""

import csv
import os
import sys
from datetime import datetime

# DB-URL aus Argument oder Umgebungsvariable
if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import get_session
from models import GroupPrediction, Prediction, SpecialTip, User

timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
backup_dir = os.path.join("backup", timestamp)
os.makedirs(backup_dir, exist_ok=True)


def write_csv(filename, rows, fieldnames):
    path = os.path.join(backup_dir, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  OK {filename} ({len(rows)} Zeilen)")
    return path


with get_session() as s:

    # --- Nutzer (ohne Passwort-Hash) ---
    users = s.query(User).all()
    write_csv("users.csv", [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "is_admin": u.is_admin,
            "in_pool": u.in_pool,
            "has_paid": u.has_paid,
            "stake_amount": u.stake_amount,
            "joker_match_id": u.joker_match_id,
            "created_at": u.created_at,
        }
        for u in users
    ], ["id", "username", "display_name", "is_admin", "in_pool", "has_paid", "stake_amount", "joker_match_id", "created_at"])

    # --- Spieltipps ---
    predictions = s.query(Prediction).all()
    write_csv("predictions.csv", [
        {
            "id": p.id,
            "user_id": p.user_id,
            "username": p.user.username,
            "match_id": p.match_id,
            "match_number": p.match.match_number,
            "pred_home": p.pred_home,
            "pred_away": p.pred_away,
            "points_awarded": p.points_awarded,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in predictions
    ], ["id", "user_id", "username", "match_id", "match_number", "pred_home", "pred_away", "points_awarded", "created_at", "updated_at"])

    # --- Gruppensieger-Tipps ---
    gp = s.query(GroupPrediction).all()
    write_csv("group_predictions.csv", [
        {
            "id": g.id,
            "user_id": g.user_id,
            "username": g.user.username,
            "group_letter": g.group_letter,
            "predicted_1st_id": g.predicted_1st,
            "predicted_1st_name": g.team_1st.name if g.team_1st else "",
            "predicted_2nd_id": g.predicted_2nd,
            "predicted_2nd_name": g.team_2nd.name if g.team_2nd else "",
            "points_awarded": g.points_awarded,
        }
        for g in gp
    ], ["id", "user_id", "username", "group_letter", "predicted_1st_id", "predicted_1st_name", "predicted_2nd_id", "predicted_2nd_name", "points_awarded"])

    # --- Sonder-Tipps ---
    st = s.query(SpecialTip).all()
    write_csv("special_tips.csv", [
        {
            "id": t.id,
            "user_id": t.user_id,
            "username": t.user.username,
            "champion_team_id": t.champion_team_id,
            "champion_team_name": t.champion_team.name if t.champion_team else "",
            "top_scorer": t.top_scorer,
            "total_goals": t.total_goals,
            "points_awarded": t.points_awarded,
        }
        for t in st
    ], ["id", "user_id", "username", "champion_team_id", "champion_team_name", "top_scorer", "total_goals", "points_awarded"])


print(f"\nBackup gespeichert in: backup/{timestamp}/")
