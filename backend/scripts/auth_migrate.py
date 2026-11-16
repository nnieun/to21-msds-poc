"""로그인 표(auth 스키마)를 만든다. 관리자 계정으로 migrations/auth_*.sql 을 차례로 돌린다. 몇 번 돌려도 된다.

    python scripts/auth_migrate.py --database msds_service                         # 서비스 DB
    python scripts/auth_migrate.py --database msds_service --grant-role to21_extract   # 앱 계정 그룹에 권한도 준다

순서: apply_erd_migrations.py(extract) → b2_migrate.py(judge) → 이 스크립트(auth) → create_user.py(첫 관리자).
auth 는 extract·judge 와 독립이라 ERD 실행기(extract 스키마 지문만 본다)에 넣지 않고 따로 둔다.
판정 역할(to21_judge)에는 auth 권한을 주지 않는다. 접속 정보는 deploy/htodb/.env (HTODB_PG_*).
"""
import argparse
import re
import sys
from pathlib import Path

import psycopg
from psycopg import sql

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.htodb.config import pg_kwargs  # noqa: E402

MIGRATIONS = BACKEND / "migrations"
ROLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")


def migrate(database: str, grant_role: str | None = None) -> None:
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": database}) as conn:
        for path in sorted(MIGRATIONS.glob("auth_*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
            print(f"적용: {path.name}")
        if grant_role:
            role = sql.Identifier(grant_role)
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA auth TO {}").format(role))
            conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON auth.users, auth.refresh_tokens TO {}").format(role))
            conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auth TO {}").format(role))
            print(f"권한: {grant_role} 에 auth 읽기·쓰기 (삭제 없음)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", required=True)
    parser.add_argument("--grant-role")
    args = parser.parse_args()
    if args.grant_role and not ROLE.fullmatch(args.grant_role):
        parser.error("역할명은 영문·숫자·밑줄·$로 된 63자 이하 식별자여야 합니다")
    try:
        migrate(args.database, args.grant_role)
    except psycopg.Error as error:
        # 연결 오류 문장에는 접속 정보가 들어갈 수 있어 종류와 SQLSTATE 만 보인다
        sys.exit(f"auth 마이그레이션 실패: {type(error).__name__} (SQLSTATE {error.sqlstate or '없음'})")
    print(f"auth 스키마 준비 끝 (database={args.database})")
