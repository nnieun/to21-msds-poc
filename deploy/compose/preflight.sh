#!/usr/bin/env bash
# docker compose up 전에 빠진 게 없는지 본다. 빠진 게 있으면 무엇을 해야 하는지 알려 주고 멈춘다.
# (db는 첫 기동에서만 덤프를 복원한다. 덤프 없이 한 번 띄우면 빈 DB가 굳어 down -v 로 지워야 하니 미리 확인한다)
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
bad=0
ok()   { printf '  [ok]   %s\n' "$*"; }
fail() { printf '  [없음] %s\n' "$*"; bad=1; }

echo "== 준비 확인"
[[ -s .env ]] && ok ".env" || fail ".env → ./gen-env.sh"
[[ -s data/kdb.dump ]] && ok "data/kdb.dump" || fail "data/kdb.dump → deploy/htodb/setup.sh 뒤 ./export-kdb.sh (또는 팀에서 받아 data/ 에 둠)"
[[ -s data/globals.sql ]] && ok "data/globals.sql" || fail "data/globals.sql → 위와 같음"
[[ -s "$ROOT/to21/v0.6/TO21_MSDS_추출명세서_v0.6.xlsx" ]] && ok "to21/v0.6 명세서" || fail "to21/v0.6/ 에 TO21 자료 (to21/README.md)"
[[ -s "$ROOT/to21/v0.6/TO21_MSDS_추출스키마_v0.6.json" ]] && ok "to21/v0.6 스키마" || fail "to21/v0.6/TO21_MSDS_추출스키마_v0.6.json"
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && ok "docker compose" || fail "docker compose"
if command -v nvidia-smi >/dev/null; then ok "GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"; else fail "nvidia-smi (GPU 드라이버)"; fi
docker info 2>/dev/null | grep -qi nvidia && ok "docker의 NVIDIA 런타임" || fail "NVIDIA Container Toolkit (Lambda Stack 이미지는 기본 포함)"
echo
[[ $bad == 0 ]] && echo "준비 끝. docker compose build 로 진행" || { echo "위 항목을 채운 뒤 다시 실행하세요"; exit 1; }
