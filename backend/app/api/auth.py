from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from backend.app.logging import audit
from backend.app.security.auth import COOKIE, SESSION_SECONDS

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def set_session(response, token):
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )


@router.post("/login")
def login(value: Login, request: Request, response: Response):
    store = request.app.state.auth
    token, must_change = store.login(
        value.username, value.password, request.client.host if request.client else "unknown"
    )
    store.logout(request.cookies.get(COOKIE))
    set_session(response, token)
    audit("auth.login", username="admin")
    return {"authenticated": True, "username": "admin", "must_change_password": must_change}


@router.get("/session")
def session(request: Request):
    value = request.app.state.auth.session(request.cookies.get(COOKIE))
    return {"authenticated": bool(value), **(value or {})}


@router.post("/password")
def password(value: PasswordChange, request: Request, response: Response):
    token = request.app.state.auth.change_password(
        request.cookies.get(COOKIE),
        value.current_password,
        value.new_password,
    )
    set_session(response, token)
    audit("auth.password.changed", username="admin")
    return {"authenticated": True, "username": "admin", "must_change_password": False}


@router.post("/logout")
def logout(request: Request, response: Response):
    request.app.state.auth.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    audit("auth.logout", username="admin")
    return {"authenticated": False}
