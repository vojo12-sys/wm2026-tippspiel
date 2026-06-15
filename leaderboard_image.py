"""
leaderboard_image.py
====================
Generiert ein 1280x720px JPEG des aktuellen Leaderboards mit Pillow.
Farben exakt wie auf der Webseite (Design-System).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import DISPLAY_TIMEZONE
from standings import compute_standings

# ── Farben – exakt wie im Design-System der Webseite ─────────────────────────
BG          = (255, 255, 255)
HEADER_BG   = (30, 78, 140)        # #1E4E8C – dunkelblau
HEADER_FG   = (255, 255, 255)

# Podest-Gradienten: (hell → dunkel) wie .podium-step-X
GOLD_LT     = (240, 192,  64)      # #f0c040
GOLD_DK     = (192, 138,  18)      # #c08a12
SILVER_LT   = (208, 216, 224)      # #d0d8e0
SILVER_DK   = (135, 148, 163)      # #8794a3
BRONZE_LT   = (212, 150, 106)      # #d4966a
BRONZE_DK   = (173, 106,  52)      # #ad6a34

# Rang-Textfarben auf den Stufen
RANK_CLR    = {1: (255, 248, 220), 2: (245, 246, 248), 3: (255, 245, 235)}

# Badge-Farben wie .tip-exact / .tip-diff / .tip-tendency
CLR_E       = ( 74, 174, 200)      # --accent-dk: #4aaec8
CLR_D       = (138,  98,   8)      # #8a6208
CLR_T       = (122,  74,  32)      # #7a4a20

CLR_GES     = ( 30,  78, 140)      # #1E4E8C
TEXT_DARK   = ( 22,  32,  43)
TEXT_MUTED  = (130, 140, 150)
ROW_ODD     = (245, 248, 252)
ROW_EVEN    = (255, 255, 255)
DIVIDER     = (210, 218, 228)
ACCENT      = (126, 200, 227)      # #7EC8E3

W, H         = 1280, 720
ROWS_PER_COL = 12
COL_W        = W // 2


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    pairs = [
        ("C:/Windows/Fonts/arialbd.ttf",  True),
        ("C:/Windows/Fonts/arial.ttf",    False),
        ("C:/Windows/Fonts/calibrib.ttf", True),
        ("C:/Windows/Fonts/calibri.ttf",  False),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",            True),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                 False),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",    True),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", False),
    ]
    for path, is_bold in pairs:
        if is_bold == bold and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    for path, _ in pairs:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default(size=size)


def _tw(draw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _trunc(draw, text: str, max_w: int, font) -> str:
    if _tw(draw, text, font) <= max_w:
        return text
    while len(text) > 1 and _tw(draw, text + "…", font) > max_w:
        text = text[:-1]
    return text + "…"


def _gradient_rect(img: Image.Image, x1: int, y1: int, x2: int, y2: int,
                   c_top: tuple, c_bot: tuple) -> None:
    """Füllt ein Rechteck mit vertikalem Farbverlauf (PIL-kompatibel)."""
    draw = ImageDraw.Draw(img)
    h = max(y2 - y1, 1)
    for dy in range(h):
        t = dy / h
        r = int(c_top[0] + (c_bot[0] - c_top[0]) * t)
        g = int(c_top[1] + (c_bot[1] - c_top[1]) * t)
        b = int(c_top[2] + (c_bot[2] - c_top[2]) * t)
        draw.line([(x1, y1 + dy), (x2, y1 + dy)], fill=(r, g, b))


def generate_leaderboard_jpeg(output_path: str | None = None) -> bytes:
    rows = compute_standings()

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now_l  = datetime.now(timezone.utc).astimezone(DISPLAY_TIMEZONE)
    DAYS   = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
    MONTHS = ["Januar","Februar","März","April","Mai","Juni",
              "Juli","August","September","Oktober","November","Dezember"]
    date_str = (f"{DAYS[now_l.weekday()]}, {now_l.day}. {MONTHS[now_l.month-1]} "
                f"{now_l.year}  ·  {now_l.strftime('%H:%M')} Uhr")

    # ── Schriften ────────────────────────────────────────────────────────────
    f_title   = _font(21, bold=True)
    f_date    = _font(13)
    f_podname = _font(15, bold=True)
    f_podpts  = _font(22, bold=True)
    f_podpkt  = _font(14)
    f_podrank = _font(28, bold=True)
    f_th      = _font(11, bold=True)
    f_row     = _font(13)
    f_row_b   = _font(13, bold=True)

    # ── HEADER ───────────────────────────────────────────────────────────────
    HEADER_H = 50
    draw.rectangle([0, 0, W, HEADER_H], fill=HEADER_BG)
    draw.text((20, 14), "WM 2026 Tippspiel  –  Leaderboard", font=f_title, fill=HEADER_FG)
    dw = _tw(draw, date_str, f_date)
    draw.text((W - dw - 18, 18), date_str, font=f_date, fill=ACCENT)

    # ── PODIUM ───────────────────────────────────────────────────────────────
    POD_TOP  = HEADER_H + 24
    STEP_W   = 200
    STEPS    = {1: 90, 2: 65, 3: 48}
    TEXT_GAP = 52
    POD_BOT  = POD_TOP + STEPS[1] + TEXT_GAP
    CX       = W // 2

    POSITIONS  = {1: CX, 2: CX - 235, 3: CX + 235}
    GRAD_COLS  = {1: (GOLD_LT,   GOLD_DK),
                  2: (SILVER_LT, SILVER_DK),
                  3: (BRONZE_LT, BRONZE_DK)}
    PT_COLORS  = {1: GOLD_DK, 2: SILVER_DK, 3: BRONZE_DK}

    for rank in [2, 1, 3]:
        if len(rows) < rank:
            continue
        row      = rows[rank - 1]
        cx_pos   = POSITIONS[rank]
        step_h   = STEPS[rank]
        step_top = POD_BOT - step_h
        c_top, c_bot = GRAD_COLS[rank]

        # Stufe mit Farbverlauf
        _gradient_rect(img,
                       cx_pos - STEP_W//2, step_top,
                       cx_pos + STEP_W//2, POD_BOT,
                       c_top, c_bot)
        draw = ImageDraw.Draw(img)   # Draw nach gradient neu setzen

        # Rang auf der Stufe
        rs = f"{rank}."
        rw = _tw(draw, rs, f_podrank)
        draw.text((cx_pos - rw//2, step_top + (step_h - 32)//2),
                  rs, font=f_podrank, fill=RANK_CLR[rank])

        # Punktzahl: "124" groß + " Pkt" klein
        pts_str = str(row.total_points)
        pkt_str = " Pkt"
        pts_w   = _tw(draw, pts_str, f_podpts)
        pkt_w   = _tw(draw, pkt_str, f_podpkt)
        x_pts   = cx_pos - (pts_w + pkt_w) // 2
        pts_y   = step_top - 38
        draw.text((x_pts,          pts_y + 5),  pts_str, font=f_podpts, fill=PT_COLORS[rank])
        draw.text((x_pts + pts_w,  pts_y + 10), pkt_str, font=f_podpkt, fill=TEXT_MUTED)

        # Name
        name_s = _trunc(draw, row.display_name, STEP_W - 8, f_podname)
        nw     = _tw(draw, name_s, f_podname)
        draw.text((cx_pos - nw//2, step_top - 56), name_s, font=f_podname, fill=TEXT_DARK)

    draw.line([(0, POD_BOT + 5), (W, POD_BOT + 5)], fill=DIVIDER, width=1)

    # ── TABELLE ──────────────────────────────────────────────────────────────
    TABLE_TOP = POD_BOT + 7
    TABLE_BOT = H - 4
    THEAD_H   = 24
    ROW_H     = 34

    PAD  = 10
    COLS = [
        {"key": "rang",    "x": PAD,       "w": 30,  "label": "#",            "color": TEXT_MUTED, "bold": True},
        {"key": "name",    "x": PAD + 34,  "w": 198, "label": "Teilnehmer",   "color": TEXT_DARK,  "bold": False, "left": True},
        {"key": "exakt",   "x": PAD + 236, "w": 82,  "label": "Exakte Tipps", "color": CLR_E,      "bold": False},
        {"key": "tordiff", "x": PAD + 322, "w": 84,  "label": "Tordifferenz", "color": CLR_D,      "bold": False},
        {"key": "tendenz", "x": PAD + 410, "w": 76,  "label": "Tendenz",      "color": CLR_T,      "bold": False},
        {"key": "gesamt",  "x": PAD + 490, "w": 96,  "label": "Gesamtpunkte", "color": CLR_GES,    "bold": True},
    ]

    def _ccx(col, ox): return ox + col["x"] + col["w"] // 2

    def _draw_thead(ox: int) -> None:
        draw.rectangle([ox, TABLE_TOP, ox + COL_W - 1, TABLE_TOP + THEAD_H - 1], fill=HEADER_BG)
        for col in COLS:
            lw = _tw(draw, col["label"], f_th)
            if col.get("left"):
                draw.text((ox + col["x"], TABLE_TOP + 6), col["label"], font=f_th, fill=HEADER_FG)
            else:
                draw.text((_ccx(col, ox) - lw//2, TABLE_TOP + 6), col["label"], font=f_th, fill=HEADER_FG)

    def _val(row, key: str) -> str:
        match key:
            case "rang":    return f"{row.rank}."
            case "name":    return row.display_name
            case "exakt":   return str(row.exact_count)
            case "tordiff": return str(row.goal_diff_count)
            case "tendenz": return str(row.tendency_count)
            case "gesamt":  return str(row.total_points)
            case _:         return ""

    def _draw_rows(entries: list, ox: int) -> None:
        for i, row in enumerate(entries):
            y = TABLE_TOP + THEAD_H + i * ROW_H
            draw.rectangle([ox, y, ox + COL_W - 1, y + ROW_H - 1],
                           fill=ROW_ODD if i % 2 == 0 else ROW_EVEN)
            ty   = y + (ROW_H - 13) // 2
            for col in COLS:
                v    = _val(row, col["key"])
                font = f_row_b if col["bold"] else f_row
                fill = col["color"]
                if col.get("left"):
                    txt = _trunc(draw, v, col["w"] - 4, font)
                    draw.text((ox + col["x"], ty), txt, font=font, fill=fill)
                else:
                    vw = _tw(draw, v, font)
                    draw.text((_ccx(col, ox) - vw//2, ty), v, font=font, fill=fill)

    _draw_thead(0)
    _draw_thead(COL_W)
    _draw_rows(rows[3:3 + ROWS_PER_COL], 0)
    _draw_rows(rows[3 + ROWS_PER_COL:3 + ROWS_PER_COL * 2], COL_W)

    # Trennstrich nach allen Rechtecken – zieht komplett durch
    draw.line([(COL_W, TABLE_TOP), (COL_W, TABLE_BOT)], fill=DIVIDER, width=2)

    # ── Export ───────────────────────────────────────────────────────────────
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    data = buf.getvalue()
    if output_path:
        Path(output_path).write_bytes(data)
    return data


if __name__ == "__main__":
    out = "leaderboard_preview.jpg"
    generate_leaderboard_jpeg(output_path=out)
    print(f"Gespeichert: {out}")
