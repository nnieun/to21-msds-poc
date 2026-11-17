"""FastAPI 의존성: 로그인 확인, 관리자 확인, 기록에 남길 검토자 이름.

앱은 보호할 라우터를 include_router(..., dependencies=[Depends(current_user)]) 로 붙인다 (extract_app).
current_user 가 확인한 사용자를 request.state.user 에 두면, 경로 함수는 acting_reviewer 로 이름을 꺼낸다.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from msds.auth.security import TokenError, decode
from msds.auth.users import User

ACCESS_COOKIE = "msds_access"
REFRESH_COOKIE = "msds_refresh"
REFRESH_PATH = "/api/auth"


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


def bearer_token(request: Request) -> str | None:
    """Authorization: Bearer 가 있으면 그것, 없으면 쿠키. (Basic 같은 다른 방식은 무시한다)"""
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return request.cookies.get(ACCESS_COOKIE)


def current_user(request: Request) -> User:
    """로그인한 사용자. 토큰이 없거나 틀리면 401, 사용자가 없어졌거나 비활성이면 401.

    역할과 이름은 토큰이 아니라 DB에서 다시 읽는다. 관리자가 역할을 바꾸거나 계정을 막으면 다음 요청부터 바로 반영된다.
    """
    auth = getattr(request.app.state, "auth", None)
    if auth is None:
        raise _unauthorized("로그인을 확인할 수 없습니다")
    try:
        claims = decode(auth.settings, bearer_token(request), "access")
    except TokenError as e:
        raise _unauthorized(str(e)) from None
    user = auth.users.get(claims["user_id"])
    if user is None or not user.is_active:
        raise _unauthorized("사용할 수 없는 계정입니다")
    request.state.user = user
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "관리자만 할 수 있습니다")
    return user


def acting_reviewer(request: Request, claimed: str | None) -> str:
    """검수·판정 기록에 남길 이름.

    로그인한 사용자가 있으면 본문의 reviewer 와 상관없이 그 사용자의 이름이다(다른 사람 이름으로 기록하지 못한다).
    인증 없이 라우터만 붙인 시험 앱에서는 예전처럼 본문의 이름을 쓴다. 둘 다 없으면 422.
    """
    user = getattr(request.state, "user", None)
    if user is not None:
        return user.display_name
    if claimed and claimed.strip():
        return claimed.strip()
    raise HTTPException(422, "검토자를 알 수 없습니다. 로그인하세요")


def signed_in_as(user: User):
    """시험용: current_user 를 이 사용자로 바꿔 끼우는 의존성. app.dependency_overrides[current_user] = signed_in_as(u)"""
    def _dep(request: Request) -> User:
        request.state.user = user
        return user
    return _dep
