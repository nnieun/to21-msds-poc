"""앱 수명에서 인증을 준비한다: 설정(비밀키), 사용자 저장소, 로그인 실패 제한, 첫 관리자.

PostgreSQL 모드(MSDS_SERVICE_DATABASE_URL)에서는 비밀키가 없으면 켜지지 않는다.
파일 모드(DB 없음) 개발 서버는 임시 키와 메모리 저장소로 켜지고, 첫 관리자는 환경변수로 만든다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

from msds.auth.security import AuthSettings, hash_password
from msds.auth.users import MemoryUserStore, PostgresUserStore, UserExists, validate_new_user

LOG = logging.getLogger(__name__)

ADMIN_USERNAME_ENV = "MSDS_ADMIN_USERNAME"
ADMIN_PASSWORD_ENV = "MSDS_ADMIN_PASSWORD"
ADMIN_NAME_ENV = "MSDS_ADMIN_DISPLAY_NAME"


class LoginThrottle:
    """아이디별 연속 실패가 max_failures 번이면 lock_seconds 동안 막는다. 프로세스 메모리에만 둔다."""

    def __init__(self, max_failures: int = 5, lock_seconds: float = 300, clock=time.monotonic):
        self.max_failures, self.lock_seconds, self.clock = max_failures, lock_seconds, clock
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float]] = {}

    def locked_for(self, username: str) -> float:
        """남은 잠금 초. 잠겨 있지 않으면 0."""
        with self._lock:
            fails, until = self._state.get(username, (0, 0.0))
            return max(0.0, until - self.clock())

    def failed(self, username: str) -> None:
        with self._lock:
            fails, until = self._state.get(username, (0, 0.0))
            if until and until <= self.clock():
                fails = 0
            fails += 1
            self._state[username] = (fails, self.clock() + self.lock_seconds if fails >= self.max_failures else 0.0)

    def succeeded(self, username: str) -> None:
        with self._lock:
            self._state.pop(username, None)


@dataclass
class AuthContext:
    settings: AuthSettings
    users: object
    throttle: LoginThrottle = field(default_factory=LoginThrottle)


def build_auth(*, users=None, settings: AuthSettings | None = None, db_url: str | None = None) -> AuthContext:
    """주입한 값이 있으면 그것을, 없으면 DB 주소로 PostgreSQL, 그것도 없으면 메모리 저장소를 쓴다."""
    if users is None:
        if db_url:
            users = PostgresUserStore(db_url)
            users.validate_schema()
        else:
            users = MemoryUserStore()
    if settings is None:
        settings, ephemeral = AuthSettings.from_env(require_secret=isinstance(users, PostgresUserStore))
        if ephemeral:
            LOG.warning("MSDS_JWT_SECRET이 없어 이번 실행에만 쓰는 키를 만들었습니다. 다시 켜면 모두 다시 로그인해야 합니다")
    ensure_admin_from_env(users)
    return AuthContext(settings, users)


def ensure_admin_from_env(users) -> None:
    """MSDS_ADMIN_USERNAME·MSDS_ADMIN_PASSWORD 가 있으면 그 관리자를 (없을 때만) 만든다. 있는 계정은 건드리지 않는다."""
    username = os.environ.get(ADMIN_USERNAME_ENV, "").strip()
    password = os.environ.get(ADMIN_PASSWORD_ENV, "")
    if not username or not password:
        return
    if users.find(username) is not None:
        return
    display = os.environ.get(ADMIN_NAME_ENV, "").strip() or "관리자"
    validate_new_user(username, display, password, "admin")
    try:
        users.create(username, display, hash_password(password), "admin")
        LOG.info("첫 관리자 계정을 만들었습니다: %s", username)
    except UserExists:
        pass  # 다른 프로세스가 먼저 만들었다
