"""
auth.py
=======
Einfache, sichere Authentifizierung für die Tipprunde (für ~20 Teilnehmer
völlig ausreichend). Nutzt PBKDF2-HMAC-SHA256 aus der Standardbibliothek –
keine Zusatz-Abhängigkeit nötig.

Der Admin legt die Accounts an (create_user). Jeder Teilnehmer bekommt sein
Passwort und loggt sich am Handy oder Desktop ein.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import select

from database import get_session
from models import User

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def create_user(username: str, display_name: str, password: str,
                *, is_admin: bool = False) -> int:
    """Legt einen Teilnehmer an und gibt dessen ID zurück."""
    with get_session() as s:
        if s.scalar(select(User).where(User.username == username)):
            raise ValueError(f"Benutzername '{username}' existiert bereits.")
        u = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            is_admin=is_admin,
        )
        s.add(u)
        s.flush()
        return u.id


def authenticate(username: str, password: str) -> User | None:
    """Prüft Login. Gibt den User zurück oder None."""
    with get_session() as s:
        u = s.scalar(select(User).where(User.username == username))
        if u and verify_password(password, u.password_hash):
            s.expunge(u)
            return u
    return None
