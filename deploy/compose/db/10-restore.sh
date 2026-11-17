#!/bin/bash
# db 컨테이너의 첫 기동(데이터 볼륨이 빌 때)에만 돈다. 지식DB 덤프를 복원한다.
# deploy/runpod/demo/pod_app_setup.sh의 [3] 단계와 같다. 덤프는 data/ 에 둔다(export-kdb.sh가 만든다).
set -e
D=/dump

if [ ! -s "$D/kdb.dump" ] || [ ! -s "$D/globals.sql" ]; then
  echo "지식DB 덤프가 없습니다: deploy/compose/data/kdb.dump, globals.sql (README 2단계)" >&2
  exit 1
fi

# 적재 계정 kdb는 이미 있다(POSTGRES_USER). 나머지 역할(kdb_reader, to21_*)을 만든다. 이미 있다는 경고는 무시한다
grep -v '^CREATE ROLE kdb;' "$D/globals.sql" | grep -v '^ALTER ROLE kdb ' \
  | psql -q -U kdb -d postgres > /dev/null || true

createdb -U kdb kdb
pg_restore -U kdb -d kdb --no-owner --role=kdb "$D/kdb.dump" || true   # 역할 소유 경고는 무시하고 표 수로 확인한다

N=$(psql -U kdb -d kdb -Atc "select count(*) from pg_tables where schemaname in ('htodb','htodb_map')")
echo "지식DB 표: $N"
if [ "$N" -le 0 ]; then
  echo "지식DB 복원 실패. 덤프를 확인하고 볼륨을 지운 뒤(docker compose down -v) 다시 실행하세요" >&2
  exit 1
fi

# 조회 계정은 쓰기 권한 없이, 비밀번호는 .env 값으로 맞춘다 (deploy/htodb/setup.sh와 같다)
psql -v ON_ERROR_STOP=1 -v rpw="$HTODB_READER_PASSWORD" -U kdb -d postgres -q > /dev/null <<'SQL'
SELECT 'CREATE ROLE kdb_reader LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kdb_reader') \gexec
ALTER ROLE kdb_reader PASSWORD :'rpw';
GRANT pg_read_all_data TO kdb_reader;
ALTER ROLE kdb_reader SET default_transaction_read_only = on;
SQL
echo "지식DB 복원 끝"
