#!/usr/bin/env bash
# .env를 무작위 비밀번호로 만든다. 이미 있으면 건드리지 않는다. 비밀번호는 화면에 출력하지 않는다.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -e .env ]]; then
  echo ".env가 이미 있어 그대로 둡니다 (새로 만들려면 지우고 다시 실행)"
  exit 0
fi

tok() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32; }

umask 077
{
  grep -v -E '^(HTODB_PG_PASSWORD|HTODB_READER_PASSWORD|JUDGE_PG_PASSWORD|VLLM_API_KEY|WEB_PASSWORD)=' .env.example
  echo "HTODB_PG_PASSWORD=$(tok)"
  echo "HTODB_READER_PASSWORD=$(tok)"
  echo "JUDGE_PG_PASSWORD=$(tok)"
  echo "VLLM_API_KEY=$(tok)"
  echo "WEB_PASSWORD=$(tok)"
} > .env
echo ".env 만듦. 웹 접속 비밀번호는 'grep WEB_PASSWORD .env' 로 확인합니다 (아이디 to21)"
