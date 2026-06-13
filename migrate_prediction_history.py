"""
migrate_prediction_history.py
==============================
1. Erstellt die Tabelle prediction_history
2. Trägt alle bestehenden Predictions als Baseline-Snapshot ein
   (saved_at = prediction.created_at → gilt als Original-Tipp)

Lokal:      python migrate_prediction_history.py
Produktion: python migrate_prediction_history.py "postgresql://..."
"""
import sys, os

if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]

from database import engine, Base, get_session
from sqlalchemy import text, inspect, select
from models import Prediction, PredictionHistory

# Tabelle anlegen
Base.metadata.create_all(engine, tables=[PredictionHistory.__table__])
print("Tabelle prediction_history: OK")

# Baseline-Snapshots eintragen (nur wo noch kein Eintrag existiert)
with get_session() as s:
    preds = s.scalars(select(Prediction)).all()
    inserted = 0
    for p in preds:
        exists = s.scalar(
            select(PredictionHistory).where(PredictionHistory.prediction_id == p.id).limit(1)
        )
        if exists is None:
            snap = PredictionHistory(
                prediction_id=p.id,
                pred_home=p.pred_home,
                pred_away=p.pred_away,
                saved_at=p.created_at,
            )
            s.add(snap)
            inserted += 1

print(f"Baseline-Snapshots: {inserted} eingetragen ({len(preds) - inserted} bereits vorhanden).")
print("Fertig.")
