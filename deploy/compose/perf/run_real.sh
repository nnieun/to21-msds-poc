#!/usr/bin/env bash
# 서버에서 실행: 같은 PDF 묶음을 문서 동시 처리 수(MSDS_EXTRACT_WORKERS)만 바꿔 가며 처리하고 시간을 잰다.
# 사용: run_real.sh "<워커 수 목록>" [접두어=real]
# 예:   run_real.sh "1 3 6"
# app 컨테이너만 다시 만들고(vLLM은 그대로), 앱의 동시 호출 상한(MSDS_MODEL_MAX_INFLIGHT)은 MAX_NUM_SEQS를 따른다.
set -euo pipefail
LIST="${1:?워커 수 목록이 필요합니다}"; PREFIX="${2:-real}"
cd "$HOME/to21-msds-poc/deploy/compose"
# OCR=1 이면 글자추출 API·OCR 워커 구성(compose.ocr.yaml)을 겹쳐 쓴다. vLLM 설정이 같아야 컨테이너가 다시 만들어지지 않는다
if [ "${OCR:-0}" = "1" ]; then export COMPOSE_FILE=compose.yaml:compose.ocr.yaml GPU_UTIL=0.72; fi
shopt -s nullglob
PDFS=("$HOME"/perf/pdfs/*.pdf)
[ "${#PDFS[@]}" -gt 0 ] || { echo "~/perf/pdfs/ 에 PDF가 없습니다" >&2; exit 1; }
# NDOCS=N 이면 같은 PDF 묶음을 반복해 N건으로 만든다(부하 시험). LIMIT=초 로 기다리는 한도를 바꾼다
if [ -n "${NDOCS:-}" ]; then
  BASE=("${PDFS[@]}"); PDFS=()
  for ((i = 0; i < NDOCS; i++)); do PDFS+=("${BASE[$((i % ${#BASE[@]}))]}"); done
fi
echo "PDF ${#PDFS[@]}건: $(basename -a "${PDFS[@]}" | tr '\n' ' ')"

for w in $LIST; do
  # 같은 PDF를 여러 번 처리하면 앞선 실행의 prefix 캐시 덕에 뒤쪽이 공짜로 빨라진다. 매 실험 전에 vLLM을 재시작해 캐시를 비운다
  echo "== vLLM 재시작(prefix 캐시 비우기) $(date +%T)"
  docker compose restart vllm >/dev/null
  docker compose up -d --wait vllm >/dev/null
  echo "== 문서 동시 수 $w 로 app 재시작 $(date +%T)"
  EXTRACT_WORKERS="$w" docker compose up -d --force-recreate --wait app >/dev/null
  # OCR_WORKERS=N 이면 글자추출 워커를 N개로 맞춘다(기존 컨테이너는 그대로 두고 늘리거나 줄인다. OCR=1일 때만)
  if [ "${OCR:-0}" = "1" ] && [ -n "${OCR_WORKERS:-}" ]; then
    docker compose up -d --no-recreate --scale ocr-worker="$OCR_WORKERS" ocr-worker >/dev/null 2>&1
    sleep 8
    echo "   OCR 워커 $(docker compose ps -q ocr-worker | wc -l)개, 앱 전처리 동시 ${PREPROCESS_WORKERS:-2}, 모델 추출 동시 $w"
  fi
  sleep 5
  # JUDGE=1 이면 추출 뒤 판정 로직과 LLM 설명까지(전체 흐름) 잰다
  python3 "$HOME/perf/real_pdf.py" ${JUDGE:+--judge} --limit "${LIMIT:-1500}" "${PREFIX}_w${w}" "${PDFS[@]}"
done
echo "끝 $(date +%T)"
