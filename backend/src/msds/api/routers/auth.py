"""로그인과 사용자 관리 API.

POST  /api/auth/login     아이디·비밀번호 → access·refresh 쿠키(HttpOnly) + 본문에 사용자와 access 토큰
POST  /api/auth/refresh   refresh 쿠키 → 새 access·refresh (쓴 refresh 는 폐기)
POST  /api/auth/logout    refresh 폐기, 쿠키 지움 (로그인이 만료돼도 부를 수 있다)
GET   /api/auth/me        지금 로그인한 사용자
GET   /api/users          사용자 목록            (관리자)
POST  /api/users          사용자 만들기          (관리자)
PATCH /api/users/{id}     이름·역할·사용 여부·비밀번호 바꾸기 (관리자)

쿠키를 쓰는 이유: 화면이 원본 PDF(pdf.js, 새 탭)와 리포트(window.open)를 주소로 여는데, 이런 요청에는
Authorization 머리글을 붙일 수 없다. 같은 출처에서 SameSite=Strict 쿠키라 다른 사이트가 대신 보낼 수 없다.
Swagger·스크립트는 본문의 access_token 을 Authorization: Bearer 로 써도 된다.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from msds.auth.deps import ACCESS_COOKIE, REFRESH_COOKIE, REFRESH_PATH, current_user, require_admin
from msds.auth.security import (DUMMY_HASH, TokenError, decode, hash_password, issue_access, issue_refresh,
                                needs_rehash, verify_password)
from msds.auth.users import ROLES, User, UserExists, validate_display_name, validate_new_user, validate_password

router = APIRouter(tags=["auth"])

LOGIN_FAILED = "아이디 또는 비밀번호가 맞지 않습니다"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Annotated[str, Field(min_length=1, max_length=40)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class NewUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    display_name: str
    password: str
    role: Literal["admin", "reviewer"] = "reviewer"


class UserChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    role: Literal["admin", "reviewer"] | None = None
    is_active: bool | None = None
    password: str | None = None


def _auth(request: Request):
    return request.app.state.auth


def _set_cookies(response: Response, auth, access: str, refresh: str) -> None:
    common = {"httponly": True, "secure": auth.settings.cookie_secure, "samesite": "strict"}
    response.set_cookie(ACCESS_COOKIE, access, max_age=auth.settings.access_seconds, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=auth.settings.refresh_seconds, path=REFRESH_PATH, **common)


def _clear_cookies(response: Response, auth) -> None:
    common = {"httponly": True, "secure": auth.settings.cookie_secure, "samesite": "strict"}
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **common)


def _session(response: Response, auth, user: User) -> dict:
    """새 access·refresh 를 만들어 쿠키에 넣고 본문을 돌려준다."""
    access = issue_access(auth.settings, user)
    refresh, jti, expires = issue_refresh(auth.settings, user)
    auth.users.save_refresh(jti, user.id, expires)
    _set_cookies(response, auth, access, refresh)
    return {"user": user.public(), "access_token": access, "token_type": "bearer",
            "expires_in": auth.settings.access_seconds}


@router.post("/api/auth/login")
def login(request: Request, response: Response, body: LoginRequest):
    auth = _auth(request)
    username = body.username.strip().lower()
    wait = auth.throttle.locked_for(username)
    if wait:
        raise HTTPException(429, f"로그인 실패가 많아 잠시 막았습니다. {int(wait) + 1}초 뒤에 다시 하세요",
                            headers={"Retry-After": str(int(wait) + 1)})
    found = auth.users.find(username)
    # 없는 아이디도 해시 검사를 한 번 해서, 응답 시간으로 아이디가 있는지 알 수 없게 한다
    ok = verify_password(found[1] if found else DUMMY_HASH, body.password)
    if not found or not ok or not found[0].is_active:
        auth.throttle.failed(username)
        raise HTTPException(401, LOGIN_FAILED)
    user, password_hash = found
    auth.throttle.succeeded(username)
    if needs_rehash(password_hash):  # 해시 설정이 바뀌었으면 맞는 비밀번호를 받은 김에 새로 만든다
        auth.users.update(user.id, password_hash=hash_password(body.password))
    auth.users.touch_login(user.id)
    return _session(response, auth, user)


def _refused(auth, message: str) -> JSONResponse:
    """401과 함께 쿠키를 지운다. 예외로 던지면 지운 쿠키가 응답에 실리지 않아 직접 응답을 만든다."""
    response = JSONResponse({"detail": message}, status_code=401)
    _clear_cookies(response, auth)
    return response


@router.post("/api/auth/refresh")
def refresh(request: Request, response: Response):
    auth = _auth(request)
    try:
        claims = decode(auth.settings, request.cookies.get(REFRESH_COOKIE), "refresh")
    except TokenError as e:
        return _refused(auth, str(e))
    user_id = auth.users.use_refresh(claims["jti"])
    user = auth.users.get(user_id) if user_id == claims["user_id"] else None
    if user is None or not user.is_active:
        return _refused(auth, "다시 로그인하세요")
    return _session(response, auth, user)


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    auth = _auth(request)
    try:
        auth.users.revoke_refresh(decode(auth.settings, request.cookies.get(REFRESH_COOKIE), "refresh")["jti"])
    except TokenError:
        pass  # 이미 만료됐거나 없으면 쿠키만 지운다
    _clear_cookies(response, auth)
    response.status_code = 204
    return response


@router.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user.public()


# ── 사용자 관리 (관리자) ──

@router.get("/api/users", dependencies=[Depends(require_admin)])
def list_users(request: Request):
    return {"items": [u.public() for u in _auth(request).users.list()], "roles": list(ROLES)}


@router.post("/api/users", status_code=201, dependencies=[Depends(require_admin)])
def create_user(request: Request, body: NewUser):
    username = body.username.strip().lower()
    try:
        validate_new_user(username, body.display_name, body.password, body.role)
        user = _auth(request).users.create(username, body.display_name, hash_password(body.password), body.role)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except UserExists:
        raise HTTPException(409, f"이미 있는 아이디입니다: {username}") from None
    return user.public()


@router.patch("/api/users/{user_id}")
def change_user(request: Request, user_id: int, body: UserChange, admin: User = Depends(require_admin)):
    users = _auth(request).users
    target = users.get(user_id)
    if target is None:
        raise HTTPException(404, "없는 사용자입니다")
    try:
        if body.display_name is not None:
            validate_display_name(body.display_name)
        if body.password is not None:
            validate_password(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    demotes = target.is_admin and target.is_active and (body.role == "reviewer" or body.is_active is False)
    if demotes and target.id == admin.id:
        raise HTTPException(409, "자기 자신의 관리자 권한이나 계정은 막을 수 없습니다")
    if demotes and users.count_active_admins() <= 1:
        raise HTTPException(409, "마지막 관리자는 막을 수 없습니다")
    updated = users.update(user_id, display_name=body.display_name, role=body.role, is_active=body.is_active,
                           password_hash=hash_password(body.password) if body.password is not None else None)
    if body.password is not None or body.is_active is False:
        users.revoke_user(user_id)  # 비밀번호를 바꾸거나 막았으면 다른 곳의 로그인 유지를 끊는다
    return updated.public()
