#!/bin/bash
# app 컨테이너 시작: 명세서에서 프롬프트를 만들고 앱(화면+추출+판정)을 8020에 띄운다.
# 프롬프트(backend/src/msds/extract/prompts/b*.md)는 TO21 명세서에서 만들어 저장소에 없다(D-47).
set -euo pipefail
cd /app/backend

[ -f /app/to21/v0.6/TO21_MSDS_추출명세서_v0.6.xlsx ] || {
  echo "명세서가 없습니다. 서버의 to21/v0.6/ 에 TO21 자료를 두세요 (to21/README.md)" >&2
  exit 1
}

python scripts/build_prompts.py
exec uvicorn --app-dir src msds.api.extract_app:app --host 0.0.0.0 --port "${MSDS_API_PORT:-8020}"
