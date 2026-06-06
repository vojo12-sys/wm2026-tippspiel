from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth import authenticate, create_user
from deps import templates

router = APIRouter()


def _flash(request: Request, message: str, type: str = "danger") -> None:
    request.session["flash"] = {"message": message, "type": type}


def _get_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


@router.get("/")
async def index(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps", status_code=302)
    return templates.TemplateResponse(request, "landing.html", {})


@router.get("/login")
async def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps", status_code=302)
    return templates.TemplateResponse(request, "login.html", {
        "flash": _get_flash(request), "user": None,
    })


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    u = authenticate(username.strip(), password)
    if not u:
        _flash(request, "Benutzername oder Passwort falsch.")
        return RedirectResponse("/login", status_code=303)
    request.session["user"] = {
        "id": u.id,
        "display_name": u.display_name,
        "is_admin": u.is_admin,
    }
    return RedirectResponse("/tipps", status_code=303)


@router.get("/register")
async def register_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/tipps", status_code=302)
    return templates.TemplateResponse(request, "register.html", {
        "flash": _get_flash(request), "user": None,
    })


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    if password != password2:
        _flash(request, "Passwörter stimmen nicht überein.")
        return RedirectResponse("/register", status_code=303)
    if len(password) < 6:
        _flash(request, "Passwort muss mindestens 6 Zeichen lang sein.")
        return RedirectResponse("/register", status_code=303)
    try:
        create_user(username.strip(), display_name.strip() or username.strip(), password)
    except ValueError as e:
        _flash(request, str(e))
        return RedirectResponse("/register", status_code=303)
    _flash(request, "Konto erstellt – bitte einloggen.", "success")
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
