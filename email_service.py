"""
email_service.py
================
Gmail SMTP E-Mail-Dienst für das WM 2026 Tippspiel.

Benötigte Umgebungsvariable:
  GMAIL_APP_PASSWORD  – Google App-Passwort für hegne94@googlemail.com
  (ohne diesen Key werden alle Funktionen still übersprungen)
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SENDER               = "hegne94@googlemail.com"
RECIPIENTS_REGISTER    = ["hegne@freenet.de"]
SMTP_HOST            = "smtp.gmail.com"
SMTP_PORT            = 587


def _app_password() -> str | None:
    return os.environ.get("GMAIL_APP_PASSWORD")


def _send(msg: MIMEMultipart, recipients: list[str]) -> None:
    pw = _app_password()
    if not pw:
        logger.info("GMAIL_APP_PASSWORD nicht gesetzt – E-Mail wird nicht versendet.")
        return
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.login(SENDER, pw)
            s.sendmail(SENDER, recipients, msg.as_string())
        logger.info("E-Mail '%s' versendet an %s", msg["Subject"], recipients)
    except Exception as exc:
        logger.error("E-Mail-Versand fehlgeschlagen: %s", exc)


def send_registration_notification(username: str, display_name: str,
                                   is_spectator: bool = False) -> None:
    """Wird nach erfolgreicher Registrierung aufgerufen."""
    role = "Zuschauer" if is_spectator else "Tipp-Teilnehmer"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[WM 2026 Tippspiel] Neue Anmeldung: {display_name}"
    msg["From"]    = SENDER
    msg["To"]      = ", ".join(RECIPIENTS_REGISTER)

    text = (
        f"Neuer Nutzer registriert:\n\n"
        f"  Anzeigename:  {display_name}\n"
        f"  Benutzername: {username}\n"
        f"  Rolle:        {role}\n\n"
        f"https://wm2026-tippspiel-l9sj.onrender.com/admin"
    )
    html = f"""
<html><body style="font-family:sans-serif;color:#16202b;">
<h2 style="color:#1E4E8C;">WM 2026 Tippspiel – Neue Anmeldung</h2>
<table style="border-collapse:collapse;">
  <tr><td style="padding:4px 12px 4px 0;color:#828c96;">Anzeigename</td>
      <td style="padding:4px 0;font-weight:bold;">{display_name}</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#828c96;">Benutzername</td>
      <td style="padding:4px 0;">{username}</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#828c96;">Rolle</td>
      <td style="padding:4px 0;">{role}</td></tr>
</table>
<p style="margin-top:16px;">
  <a href="https://wm2026-tippspiel-l9sj.onrender.com/admin"
     style="background:#1E4E8C;color:#fff;padding:8px 16px;border-radius:4px;
            text-decoration:none;">Admin-Bereich öffnen</a>
</p>
</body></html>"""

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html",  "utf-8"))
    _send(msg, RECIPIENTS_REGISTER)
