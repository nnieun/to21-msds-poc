#!/usr/bin/env bash
# deploy/htodb/setup.sh로 지식DB를 적재한 뒤 실행한다. 지식DB를 덤프로 떠서 data/ 에 둔다.
# 이 덤프가 있으면 다음부터는 SQL Server와 setup.sh 없이 compose만으로 복원된다.
# 덤프는 TO21 자료다. 저장소에 올리지 않는다(.gitignore가 막는다, D-47).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/data"
mkdir -p "$OUT"
cd "$HERE/../htodb"

docker compose ps --status running pg | grep -q pg || { echo "htodb pg가 떠 있지 않습니다. 먼저 deploy/htodb/setup.sh 를 실행하세요" >&2; exit 1; }

docker compose exec -T pg pg_dump -U kdb -Fc kdb > "$OUT/kdb.dump"
docker compose exec -T pg pg_dumpall -U kdb --globals-only > "$OUT/globals.sql"
# db 컨테이너의 postgres 사용자(uid가 이 사용자와 다름)가 읽어야 복원된다. 소유자만 읽기(600)면 복원이 실패한다
chmod 644 "$OUT/kdb.dump" "$OUT/globals.sql"

ls -lh "$OUT/kdb.dump" "$OUT/globals.sql"
echo "끝. 서버가 사라져도 쓰도록 이 두 파일을 내 컴퓨터로도 받아 두세요 (scp)"
