"""
models.py
=========
Vollständiges Datenbankschema des WM-2026-Tippspiels als SQLAlchemy-ORM.

Überblick der Tabellen:
  users               Teilnehmer + Login + Opt-in zur Kasse
  teams               48 Mannschaften inkl. Flaggen-Code + Gruppe
  matches             104 Spiele (Gruppen- + K.-o.-Phase) mit Ergebnis
  predictions         Spiel-Tipps (Ergebnis je Spiel)
  group_predictions   Langfrist: 1./2. Platz je Gruppe
  special_tips        Langfrist: Weltmeister / Torschützenkönig / Gesamttore
  group_results       Tatsächliche 1./2. Platzierung je Gruppe (Admin)
  tournament_result   Tatsächl. Weltmeister/Torschütze/Gesamttore (Admin)
  settings            Laufzeit-Konfiguration (überschreibt config.py)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Teilnehmer
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_spectator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    # --- Kasse / Geld-Pool (freiwillig) ---
    # Joker: verdoppelt die Punkte für ein Spiel (einmalig, unwiderruflich)
    joker_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)

    show_behavior_stats: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="1")

    in_pool: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Einsatz dieses Teilnehmers (Standard = konfigurierter Buy-in).
    # Eigenes Feld, damit später auch unterschiedliche Einsätze möglich wären.
    stake_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    group_predictions: Mapped[list["GroupPrediction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    special_tip: Mapped["SpecialTip | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    visits: Mapped[list["UserVisit"]] = relationship(cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Mannschaften
# ---------------------------------------------------------------------------

class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)          # deutscher Anzeigename
    name_en: Mapped[str] = mapped_column(String(60), nullable=False)
    flag_code: Mapped[str] = mapped_column(String(10), nullable=False)     # flagcdn-Code, z. B. "de", "gb-eng"
    group_letter: Mapped[str] = mapped_column(String(1), nullable=False)   # A..L
    fifa_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def flag_url(self, size: str = "w320") -> str:
        return f"https://flagcdn.com/{size}/{self.flag_code}.png"


# ---------------------------------------------------------------------------
# Spiele
# ---------------------------------------------------------------------------

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # 1..104 (offiziell)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)  # group/round32/round16/quarter/semi/third_place/final
    group_letter: Mapped[str | None] = mapped_column(String(1), nullable=True)       # nur Gruppenphase

    # Teams: in der K.-o.-Phase erst bekannt, sobald die Vorrunde gespielt ist.
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    # Platzhalter-Text für noch unbekannte Paarungen, z. B. "Sieger Gruppe A",
    # "2. Gruppe B", "Sieger Spiel 73". Für die Anzeige vor dem Freischalten.
    home_placeholder: Mapped[str | None] = mapped_column(String(60), nullable=True)
    away_placeholder: Mapped[str | None] = mapped_column(String(60), nullable=True)

    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Ergebnis (vom Admin eingetragen)
    result_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Weiterkommendes Team in K.-o.-Spielen (kann von result abweichen,
    # falls Verlängerung/Elfmeterschießen). Basis für den K.-o.-Bonus.
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    went_to_penalties: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    went_to_extra_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    ht_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away: Mapped[int | None] = mapped_column(Integer, nullable=True)

    home_team: Mapped["Team | None"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team | None"] = relationship(foreign_keys=[away_team_id])

    @property
    def is_locked(self) -> bool:
        """Tippsperre: True ab 10 Minuten vor Anpfiff."""
        ko = self.kickoff_utc
        if ko is None:
            return False
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        else:
            ko = ko.astimezone(timezone.utc)
        from datetime import timedelta
        return datetime.now(timezone.utc) >= ko - timedelta(minutes=10)

    @property
    def has_result(self) -> bool:
        return self.result_home is not None and self.result_away is not None


# ---------------------------------------------------------------------------
# Spiel-Tipps (Ergebnis je Spiel)
# ---------------------------------------------------------------------------

class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("user_id", "match_id", name="uq_pred_user_match"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)

    pred_home: Mapped[int] = mapped_column(Integer, nullable=False)
    pred_away: Mapped[int] = mapped_column(Integer, nullable=False)

    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="predictions")
    match: Mapped["Match"] = relationship()
    history: Mapped[list["PredictionHistory"]] = relationship(
        back_populates="prediction", order_by="PredictionHistory.saved_at"
    )


# ---------------------------------------------------------------------------
# Tipp-Änderungs-History
# ---------------------------------------------------------------------------

class PredictionHistory(Base):
    __tablename__ = "prediction_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False)
    pred_home: Mapped[int] = mapped_column(Integer, nullable=False)
    pred_away: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prediction: Mapped["Prediction"] = relationship(back_populates="history")


# ---------------------------------------------------------------------------
# Gruppen-Tipps (1./2. Platz je Gruppe) – Langfrist
# ---------------------------------------------------------------------------

class GroupPrediction(Base):
    __tablename__ = "group_predictions"
    __table_args__ = (UniqueConstraint("user_id", "group_letter", name="uq_grouppred_user_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    group_letter: Mapped[str] = mapped_column(String(1), nullable=False)

    predicted_1st: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    predicted_2nd: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)

    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="group_predictions")
    team_1st: Mapped["Team | None"] = relationship(foreign_keys=[predicted_1st])
    team_2nd: Mapped["Team | None"] = relationship(foreign_keys=[predicted_2nd])


# ---------------------------------------------------------------------------
# Sonder-Tipps (Weltmeister / Torschützenkönig / Gesamttore) – Langfrist
# ---------------------------------------------------------------------------

class SpecialTip(Base):
    __tablename__ = "special_tips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)

    champion_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    top_scorer: Mapped[str | None] = mapped_column(String(80), nullable=True)   # Spielername (Freitext/Suche)
    total_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)

    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="special_tip")
    champion_team: Mapped["Team | None"] = relationship(foreign_keys=[champion_team_id])


# ---------------------------------------------------------------------------
# Tatsächliche Ergebnisse (vom Admin gepflegt) – Basis der Langfrist-Wertung
# ---------------------------------------------------------------------------

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


class TournamentResult(Base):
    """Turnierweite tatsächliche Ergebnisse (genau eine Zeile, id=1)."""
    __tablename__ = "tournament_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    champion_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    top_scorer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Torschützenliste (von football-data.org synchronisiert)
# ---------------------------------------------------------------------------

class TopScorer(Base):
    __tablename__ = "top_scorers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nationality: Mapped[str | None] = mapped_column(String(60), nullable=True)
    flag_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    team_flag_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalties: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Seitenbesuche (Nutzungsstatistik)
# ---------------------------------------------------------------------------

class UserVisit(Base):
    __tablename__ = "user_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    route: Mapped[str] = mapped_column(String(100), nullable=False)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Laufzeit-Konfiguration (überschreibt config.py-Standardwerte)
# ---------------------------------------------------------------------------

class Setting(Base):
    """
    Schlüssel/Wert-Speicher für zur Laufzeit änderbare Einstellungen
    (Punktesystem, Kasse, Auszahlung). Werte werden als JSON-Text abgelegt.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialisiert
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
