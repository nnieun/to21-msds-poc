"""사용자와 refresh 토큰 저장소.

PostgresUserStore  서비스 DB의 auth 스키마 (migrations/auth_0001_users.sql, scripts/auth_migrate.py)
MemoryUserStore    시험과 DB 없는 파일 모드 개발 서버용. 서버를 끄면 사라진다

refresh 토큰은 jti만 남긴다(토큰 원문은 저장하지 않는다). 한 번 쓰면 폐기하고 새 토큰을 준다(회전).
이미 폐기된 토큰이 다시 오면 탈취로 보고 그 사용자의 refresh 토큰을 모두 폐기한다.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROLES = ("admin", "reviewer")
USERNAME = re.compile(r"^[a-z0-9_.-]{3,40}$")
DISPLAY_MAX = 40   # 검수 기록의 reviewer 칸 제한(추출 40자, 판정 50자) 중 작은 쪽
PASSWORD_MIN, PASSWORD_MAX = 8, 128


class UserExists(Exception):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict:
        return {"id": self.id, "username": self.username, "display_name": self.display_name,
                "role": self.role, "is_active": self.is_active}


def validate_new_user(username: str, display_name: str, password: str, role: str) -> None:
    """만들기 전 검사. 틀리면 ValueError (화면에는 422)."""
    if not USERNAME.fullmatch(username or ""):
        raise ValueError("아이디는 영문 소문자·숫자·_.- 3~40자입니다")
    validate_display_name(display_name)
    validate_password(password)
    if role not in ROLES:
        raise ValueError(f"역할은 {', '.join(ROLES)} 중 하나입니다")


def validate_display_name(display_name: str) -> None:
    if not display_name or not display_name.strip() or len(display_name) > DISPLAY_MAX or "\x00" in display_name:
        raise ValueError(f"이름은 1~{DISPLAY_MAX}자입니다")


def validate_password(password: str) -> None:
    if not PASSWORD_MIN <= len(password or "") <= PASSWORD_MAX or "\x00" in password:
        raise ValueError(f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자입니다")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryUserStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._users: dict[int, tuple[User, str]] = {}
        self._refresh: dict[str, dict] = {}
        self._next = 1

    def get(self, user_id: int) -> User | None:
        with self._lock:
            row = self._users.get(user_id)
            return row[0] if row else None

    def find(self, username: str) -> tuple[User, str] | None:
        with self._lock:
            return next((row for row in self._users.values() if row[0].username == username), None)

    def list(self) -> list[User]:
        with self._lock:
            return sorted((u for u, _ in self._users.values()), key=lambda u: u.id)

    def create(self, username: str, display_name: str, password_hash: str, role: str) -> User:
        with self._lock:
            if self.find(username):
                raise UserExists(username)
            user = User(self._next, username, display_name.strip(), role, True)
            self._users[user.id] = (user, password_hash)
            self._next += 1
            return user

    def update(self, user_id: int, *, display_name: str | None = None, role: str | None = None,
               is_active: bool | None = None, password_hash: str | None = None) -> User | None:
        with self._lock:
            row = self._users.get(user_id)
            if row is None:
                return None
            user, pw = row
            changes = {k: v for k, v in (("display_name", display_name and display_name.strip()), ("role", role),
                                         ("is_active", is_active)) if v is not None}
            user = replace(user, **changes)
            self._users[user_id] = (user, password_hash or pw)
            return user

    def count_active_admins(self) -> int:
        with self._lock:
            return sum(1 for u, _ in self._users.values() if u.is_admin and u.is_active)

    def touch_login(self, user_id: int) -> None:
        pass

    def save_refresh(self, jti: str, user_id: int, expires_at: datetime) -> None:
        with self._lock:
            self._refresh[jti] = {"user_id": user_id, "expires_at": expires_at, "revoked": False}

    def use_refresh(self, jti: str) -> int | None:
        """살아 있으면 폐기하고 사용자 번호를 돌려준다. 이미 폐기된 것이면 그 사용자 토큰을 모두 폐기하고 None."""
        with self._lock:
            row = self._refresh.get(jti)
            if row is None:
                return None
            if row["revoked"]:
                self.revoke_user(row["user_id"])
                return None
            row["revoked"] = True
            return row["user_id"] if row["expires_at"] > _now() else None

    def revoke_refresh(self, jti: str) -> None:
        with self._lock:
            if jti in self._refresh:
                self._refresh[jti]["revoked"] = True

    def revoke_user(self, user_id: int) -> None:
        with self._lock:
            for row in self._refresh.values():
                if row["user_id"] == user_id:
                    row["revoked"] = True


class PostgresUserStore:
    """요청마다 연결을 연다 (PostgresJobStore 와 같은 방식)."""

    def __init__(self, dsn: str, *, schema: str = "auth"):
        if not dsn or not dsn.strip():
            raise ValueError("A PostgreSQL DSN is required")
        self.dsn = dsn
        self.users = sql.Identifier(schema, "users")
        self.tokens = sql.Identifier(schema, "refresh_tokens")

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)

    def validate_schema(self) -> None:
        try:
            with self._connect() as db:
                db.execute(sql.SQL("SELECT user_id, username, display_name, password_hash, role, is_active "
                                   "FROM {} LIMIT 0").format(self.users))
                db.execute(sql.SQL("SELECT jti, user_id, expires_at, revoked_at FROM {} LIMIT 0").format(self.tokens))
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn,
                psycopg.errors.InvalidSchemaName) as exc:
            raise RuntimeError("로그인 표(auth.users)가 없습니다. scripts/auth_migrate.py 를 먼저 실행하세요") from exc

    @staticmethod
    def _user(row: dict) -> User:
        return User(row["user_id"], row["username"], row["display_name"], row["role"], row["is_active"])

    def get(self, user_id: int) -> User | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT * FROM {} WHERE user_id=%s").format(self.users), (user_id,)).fetchone()
        return self._user(row) if row else None

    def find(self, username: str) -> tuple[User, str] | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT * FROM {} WHERE username=%s").format(self.users), (username,)).fetchone()
        return (self._user(row), row["password_hash"]) if row else None

    def list(self) -> list[User]:
        with self._connect() as db:
            rows = db.execute(sql.SQL("SELECT * FROM {} ORDER BY user_id").format(self.users)).fetchall()
        return [self._user(r) for r in rows]

    def create(self, username: str, display_name: str, password_hash: str, role: str) -> User:
        try:
            with self._connect() as db:
                row = db.execute(sql.SQL("""INSERT INTO {} (username, display_name, password_hash, role)
                    VALUES (%s, %s, %s, %s) RETURNING *""").format(self.users),
                    (username, display_name.strip(), password_hash, role)).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise UserExists(username) from exc
        return self._user(row)

    def update(self, user_id: int, *, display_name: str | None = None, role: str | None = None,
               is_active: bool | None = None, password_hash: str | None = None) -> User | None:
        sets = [(k, v) for k, v in (("display_name", display_name and display_name.strip()), ("role", role),
                                    ("is_active", is_active), ("password_hash", password_hash)) if v is not None]
        with self._connect() as db:
            if not sets:
                row = db.execute(sql.SQL("SELECT * FROM {} WHERE user_id=%s").format(self.users), (user_id,)).fetchone()
            else:
                assignments = sql.SQL(", ").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k, _ in sets)
                row = db.execute(sql.SQL("UPDATE {} SET {}, updated_at=now() WHERE user_id=%s RETURNING *")
                                 .format(self.users, assignments), (*[v for _, v in sets], user_id)).fetchone()
        return self._user(row) if row else None

    def count_active_admins(self) -> int:
        with self._connect() as db:
            return db.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE role='admin' AND is_active")
                              .format(self.users)).fetchone()["n"]

    def touch_login(self, user_id: int) -> None:
        with self._connect() as db:
            db.execute(sql.SQL("UPDATE {} SET last_login_at=now() WHERE user_id=%s").format(self.users), (user_id,))

    def save_refresh(self, jti: str, user_id: int, expires_at: datetime) -> None:
        with self._connect() as db:
            db.execute(sql.SQL("INSERT INTO {} (jti, user_id, expires_at) VALUES (%s, %s, %s)").format(self.tokens),
                       (jti, user_id, expires_at))

    def use_refresh(self, jti: str) -> int | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("""UPDATE {} SET revoked_at=now()
                WHERE jti=%s AND revoked_at IS NULL RETURNING user_id, expires_at > now() AS alive""")
                .format(self.tokens), (jti,)).fetchone()
            if row is not None:
                return row["user_id"] if row["alive"] else None
            reused = db.execute(sql.SQL("SELECT user_id FROM {} WHERE jti=%s").format(self.tokens), (jti,)).fetchone()
            if reused is not None:
                # 이미 쓴 토큰이 다시 왔다: 누가 훔쳐 쓴 것일 수 있으니 그 사용자의 토큰을 모두 끊는다
                db.execute(sql.SQL("UPDATE {} SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL")
                           .format(self.tokens), (reused["user_id"],))
        return None

    def revoke_refresh(self, jti: str) -> None:
        with self._connect() as db:
            db.execute(sql.SQL("UPDATE {} SET revoked_at=now() WHERE jti=%s AND revoked_at IS NULL")
                       .format(self.tokens), (jti,))

    def revoke_user(self, user_id: int) -> None:
        with self._connect() as db:
            db.execute(sql.SQL("UPDATE {} SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL")
                       .format(self.tokens), (user_id,))
