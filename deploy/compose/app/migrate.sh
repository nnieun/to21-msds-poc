#!/bin/bash
# 서비스 DB(msds_service)를 만들고 표를 맞춘다. 여러 번 돌려도 된다.
# deploy/runpod/demo/pod_app_setup.sh의 [4] 단계와 같은 순서다.
set -euo pipefail
cd /app/backend

python - <<'PY'
import os
import psycopg

with psycopg.connect(host=os.environ["HTODB_PG_HOST"], port=int(os.environ["HTODB_PG_PORT"]),
                     user="kdb", password=os.environ["HTODB_PG_PASSWORD"], dbname="postgres",
                     autocommit=True) as c:
    # 역할은 보통 지식DB 덤프(globals.sql)에 들어 있다. 없을 때만 만든다 (deploy/htodb/TEAM_SETUP.md와 같은 정의)
    for role in ("to21_extract", "to21_judge"):
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            c.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
    if not c.execute("SELECT 1 FROM pg_database WHERE datname = 'msds_service'").fetchone():
        c.execute("CREATE DATABASE msds_service")
        print("msds_service 만듦")
PY

TO21_ERD_DATABASE_URL="host=$HTODB_PG_HOST port=$HTODB_PG_PORT dbname=msds_service user=kdb" \
  python scripts/apply_erd_migrations.py --extract-role to21_extract --judge-role to21_judge
python scripts/b2_migrate.py --database msds_service

echo "서비스 DB 준비 끝"
