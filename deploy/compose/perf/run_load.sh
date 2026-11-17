#!/usr/bin/env bash
# 서버에서 실행: 부하 시험. 같은 PDF 묶음을 6/12/24/48건으로 한꺼번에 넣고 처리량·대기 시간을 잰다.
#   X: 설계 구성 (모델 추출 1건씩, 설명 1건씩)   Y: 문서 3건 동시 추출
# OCR 워커 6개, 앱 전처리는 문서 수 이상(=제한 없음). 건수마다 vLLM을 재시작해 prefix 캐시를 비운다.
set -uo pipefail
cd "$HOME/perf"
export OCR=1 JUDGE=1 OCR_WORKERS=6 PREPROCESS_WORKERS=48 EXPLAIN_WORKERS=1 LIMIT=4200
for n in 6 12 24 48; do
  echo "######## 부하 X(추출 1건씩) ${n}건 $(date +%T)"
  NDOCS=$n ./run_real.sh "1" "loadX$n"
done
for n in 12 24 48; do
  echo "######## 부하 Y(추출 3건 동시) ${n}건 $(date +%T)"
  NDOCS=$n ./run_real.sh "3" "loadY$n"
done
echo "== 부하 시험 끝 $(date +%T)"
