"""비밀번호 해시와 JWT.

토큰은 둘이다.
- access: 짧게 산다(기본 30분). 매 요청에서 확인한다. 쿠키(msds_access) 또는 Authorization: Bearer 로 온다.
- refresh: 길게 산다(기본 7일). /api/auth/refresh 에서만 쓴다. jti 를 DB에 남겨 한 번 쓰면 폐기(회전)한다.

서명은 HS256 하나다. 서버 한 대 구성이라 대칭키로 충분하고, 키는 MSDS_JWT_SECRET 에서 읽는다.
"""
from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ALGORITHM = "HS256"
ISSUER = "to21-msds"
MIN_SECRET_BYTES = 32

SECRET_ENV = "MSDS_JWT_SECRET"
ACCESS_ENV = "MSDS_ACCESS_TOKEN_MINUTES"
REFRESH_ENV = "MSDS_REFRESH_TOKEN_DAYS"
COOKIE_SECURE_ENV = "MSDS_COOKIE_SECURE"

_hasher = PasswordHasher()


class TokenError(Exception):
    """토큰이 없거나, 서명·만료·종류가 맞지 않는다. 화면에는 401로 나간다."""


@dataclass(frozen=True)
class AuthSettings:
    secret: str
    access_minutes: int = 30
    refresh_days: int = 7
    cookie_secure: bool = False

    def __post_init__(self):
        if len(self.secret.encode("utf-8")) < MIN_SECRET_BYTES:
            raise ValueError(f"JWT 비밀키는 {MIN_SECRET_BYTES}바이트 이상이어야 합니다")
        if self.access_minutes < 1 or self.refresh_days < 1:
            raise ValueError("토큰 수명은 1 이상이어야 합니다")

    @property
    def access_seconds(self) -> int:
        return self.access_minutes * 60

    @property
    def refresh_seconds(self) -> int:
        return self.refresh_days * 86400

    @classmethod
    def from_env(cls, *, require_secret: bool) -> tuple["AuthSettings", bool]:
        """(설정, 임시 키 여부). 비밀키가 없으면 require_secret 일 때 멈추고, 아니면 이번 실행에만 쓰는 키를 만든다.

        임시 키는 파일 모드 개발 서버용이다. 서버를 다시 켜면 모두 다시 로그인해야 한다.
        """
        secret = os.environ.get(SECRET_ENV, "").strip()
        ephemeral = not secret
        if ephemeral:
            if require_secret:
                raise RuntimeError(f"{SECRET_ENV}가 없습니다. 32바이트 이상의 무작위 값을 넣으세요 "
                                   "(예: python -c 'import secrets; print(secrets.token_urlsafe(48))')")
            secret = secrets.token_urlsafe(48)
        settings = cls(
            secret=secret,
            access_minutes=int(os.environ.get(ACCESS_ENV, "30")),
            refresh_days=int(os.environ.get(REFRESH_ENV, "7")),
            cookie_secure=os.environ.get(COOKIE_SECURE_ENV, "0") == "1",
        )
        return settings, ephemeral


# ── 비밀번호 ──

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# 없는 아이디에도 같은 시간이 걸리게 할 때 대신 검사하는 해시 (아이디가 있는지 응답 시간으로 알 수 없게)
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ── JWT ──

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(settings: AuthSettings, claims: dict, lifetime: timedelta) -> tuple[str, str, datetime]:
    now = _now()
    jti = uuid.uuid4().hex
    expires = now + lifetime
    payload = {**claims, "iss": ISSUER, "iat": now, "nbf": now, "exp": expires, "jti": jti}
    return jwt.encode(payload, settings.secret, algorithm=ALGORITHM), jti, expires


def issue_access(settings: AuthSettings, user) -> str:
    """사용자 번호(sub)·역할만 넣는다. 이름은 매 요청 DB에서 다시 읽으므로 넣지 않는다."""
    token, _, _ = _encode(settings, {"sub": str(user.id), "role": user.role, "type": "access"},
                          timedelta(minutes=settings.access_minutes))
    return token


def issue_refresh(settings: AuthSettings, user) -> tuple[str, str, datetime]:
    """(토큰, jti, 만료 시각). jti와 만료 시각은 저장소에 남긴다."""
    return _encode(settings, {"sub": str(user.id), "type": "refresh"}, timedelta(days=settings.refresh_days))


def decode(settings: AuthSettings, token: str | None, expected_type: str) -> dict:
    if not token:
        raise TokenError("로그인이 필요합니다")
    try:
        claims = jwt.decode(token, settings.secret, algorithms=[ALGORITHM], issuer=ISSUER,
                            options={"require": ["exp", "iat", "sub", "jti", "type"]})
    except jwt.ExpiredSignatureError as e:
        raise TokenError("로그인이 만료되었습니다") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("로그인 정보가 올바르지 않습니다") from e
    if claims.get("type") != expected_type:
        raise TokenError("로그인 정보가 올바르지 않습니다")
    try:
        claims["user_id"] = int(claims["sub"])
    except (TypeError, ValueError) as e:
        raise TokenError("로그인 정보가 올바르지 않습니다") from e
    return claims
