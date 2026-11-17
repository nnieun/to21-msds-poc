"""로그인 사용자를 만든다 (주로 첫 관리자). 비밀번호는 화면에 출력하지 않는다.

    MSDS_SERVICE_DATABASE_URL="host=127.0.0.1 port=5433 dbname=msds_service user=kdb password=..." \
      python scripts/create_user.py --username admin --display-name 관리자 --role admin

비밀번호는 MSDS_NEW_USER_PASSWORD 에서 읽고, 없으면 두 번 물어본다.
--if-missing 이면 같은 아이디가 이미 있을 때 아무것도 하지 않고 성공으로 끝난다 (배포 스크립트에서 반복 실행용).
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from msds.auth.security import hash_password  # noqa: E402
from msds.auth.users import ROLES, PostgresUserStore, UserExists, validate_new_user  # noqa: E402


def read_password() -> str:
    password = os.environ.get("MSDS_NEW_USER_PASSWORD")
    if password:
        return password
    first = getpass.getpass("비밀번호: ")
    if first != getpass.getpass("비밀번호 확인: "):
        sys.exit("두 비밀번호가 다릅니다")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", choices=ROLES, default="reviewer")
    parser.add_argument("--if-missing", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("MSDS_SERVICE_DATABASE_URL")
    if not dsn:
        parser.error("MSDS_SERVICE_DATABASE_URL 환경 변수가 필요합니다")
    store = PostgresUserStore(dsn)
    store.validate_schema()
    if args.if_missing and store.find(args.username) is not None:
        print(f"이미 있음: {args.username}")
        return 0
    password = read_password()
    try:
        validate_new_user(args.username, args.display_name, password, args.role)
        user = store.create(args.username, args.display_name, hash_password(password), args.role)
    except ValueError as e:
        sys.exit(str(e))
    except UserExists:
        sys.exit(f"이미 있는 아이디입니다: {args.username}")
    print(f"만듦: {user.username} ({user.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
