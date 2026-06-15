from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from database import get_session
from deps import require_user, templates
from models import Match, Prediction
from standings import compute_standings

router = APIRouter()

_MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _fmt_match(m: Match, tz) -> dict:
    koff = m.kickoff_utc
    if koff.tzinfo is None:
        koff = koff.replace(tzinfo=timezone.utc)
    local_dt = koff.astimezone(tz)
    home = m.home_team.name if m.home_team else (m.home_placeholder or "TBD")
    away = m.away_team.name if m.away_team else (m.away_placeholder or "TBD")
    return {
        "id": m.id,
        "home": home,
        "away": away,
        "home_flag": m.home_team.flag_code if m.home_team else None,
        "away_flag": m.away_team.flag_code if m.away_team else None,
        "date_de": f"{local_dt.day}. {_MONTHS_DE[local_dt.month - 1]}",
        "time_de": local_dt.strftime("%H:%M"),
        "kickoff_iso": koff.isoformat(),
        "result_home": m.result_home,
        "result_away": m.result_away,
        "went_to_penalties": m.went_to_penalties,
    }


@router.get("/home")
async def home_get(request: Request, user: dict = Depends(require_user)):
    if isinstance(user, RedirectResponse):
        return user

    from config import DISPLAY_TIMEZONE
    from results_sync import get_live_scores

    now = datetime.now(timezone.utc)
    in_24h = now + timedelta(hours=24)
    lock_threshold = now + timedelta(minutes=10)

    from live_preview import calc_live_preview
    live_scores = {int(k): v for k, v in get_live_scores().items()}
    live_ids = set(live_scores.keys())
    live_preview = calc_live_preview() if live_ids else {}

    with get_session() as s:
        # ── Letztes abgeschlossenes Spiel ──────────────────────────────
        last_match_raw = s.scalar(
            select(Match)
            .where(Match.is_finished == True)
            .order_by(Match.kickoff_utc.desc())
            .limit(1)
        )
        last_match = None
        last_pred = None
        if last_match_raw:
            _ = last_match_raw.home_team, last_match_raw.away_team
            last_match = _fmt_match(last_match_raw, DISPLAY_TIMEZONE)
            if not user.get("is_spectator"):
                p = s.scalar(
                    select(Prediction).where(
                        Prediction.user_id == user["id"],
                        Prediction.match_id == last_match_raw.id,
                    )
                )
                if p:
                    last_pred = {
                        "home": p.pred_home,
                        "away": p.pred_away,
                        "points": p.points_awarded or 0,
                    }

        # ── Laufende Spiele ────────────────────────────────────────────
        live_matches = []
        if live_ids:
            live_raw = list(s.scalars(
                select(Match).where(Match.id.in_(live_ids))
            ).all())
            live_preds: dict[int, dict] = {}
            if not user.get("is_spectator"):
                for row in s.execute(
                    select(Prediction.match_id, Prediction.pred_home,
                           Prediction.pred_away, Prediction.points_awarded)
                    .where(Prediction.user_id == user["id"],
                           Prediction.match_id.in_(live_ids))
                ).all():
                    live_preds[row.match_id] = {
                        "home": row.pred_home,
                        "away": row.pred_away,
                        "points": row.points_awarded or 0,
                    }
            for m in live_raw:
                _ = m.home_team, m.away_team
                d = _fmt_match(m, DISPLAY_TIMEZONE)
                d["live"] = live_scores.get(m.id)
                pred = live_preds.get(m.id)
                if pred is not None:
                    pred["live_points"] = live_preview.get(m.id, {}).get(user["id"], 0)
                d["pred"] = pred
                live_matches.append(d)

        # ── Nächstes Spiel (nicht live) ────────────────────────────────
        next_match = None
        next_pred = None
        next_raw = s.scalar(
            select(Match)
            .where(Match.kickoff_utc > now, Match.is_finished == False,
                   Match.id.not_in(live_ids) if live_ids else True)
            .order_by(Match.kickoff_utc)
            .limit(1)
        )
        if next_raw:
            _ = next_raw.home_team, next_raw.away_team
            next_match = _fmt_match(next_raw, DISPLAY_TIMEZONE)
            if not user.get("is_spectator"):
                p = s.scalar(
                    select(Prediction).where(
                        Prediction.user_id == user["id"],
                        Prediction.match_id == next_raw.id,
                    )
                )
                if p:
                    next_pred = {"home": p.pred_home, "away": p.pred_away}

        # ── Nächste Spiele (Liste) ─────────────────────────────────────
        upcoming_raw = list(s.scalars(
            select(Match)
            .where(Match.kickoff_utc > now, Match.is_finished == False)
            .order_by(Match.kickoff_utc)
            .limit(5)
        ).all())
        for m in upcoming_raw:
            _ = m.home_team, m.away_team
        upcoming = [_fmt_match(m, DISPLAY_TIMEZONE) for m in upcoming_raw]

        # ── Offene Tipps in den nächsten 24 Std ───────────────────────
        open_tips_24h = 0
        open_tips_total = 0
        if not user.get("is_spectator"):
            matches_24h = [
                m for m in upcoming_raw
                if m.kickoff_utc.replace(tzinfo=timezone.utc) > lock_threshold
                and m.kickoff_utc.replace(tzinfo=timezone.utc) <= in_24h
            ]
            all_open = [
                m for m in upcoming_raw
                if m.kickoff_utc.replace(tzinfo=timezone.utc) > lock_threshold
            ]
            if all_open:
                tipped_ids = set(
                    row[0] for row in s.execute(
                        select(Prediction.match_id)
                        .where(
                            Prediction.user_id == user["id"],
                            Prediction.match_id.in_([m.id for m in all_open]),
                        )
                    ).all()
                )
                open_tips_total = len(all_open) - len(tipped_ids)
                open_tips_24h = sum(
                    1 for m in matches_24h if m.id not in tipped_ids
                )

    standings = compute_standings()
    top5 = standings[:5]
    user_rank = None
    user_points = 0
    for r in standings:
        if r.user_id == user["id"]:
            user_rank = r.rank
            user_points = r.total_points
            break

    return templates.TemplateResponse(request, "home.html", {
        "user": user,
        "active": "home",
        "last_match": last_match,
        "last_pred": last_pred,
        "live_matches": live_matches,
        "next_match": next_match,
        "next_pred": next_pred,
        "upcoming": upcoming,
        "top5": top5,
        "user_rank": user_rank,
        "user_points": user_points,
        "open_tips_24h": open_tips_24h,
        "open_tips_total": open_tips_total,
        "flash": request.session.pop("flash", None),
    })
