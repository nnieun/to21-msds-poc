#!/usr/bin/env bash
# 서버에서 실행: 설계 그대로의 구성으로 전체 흐름(OCR → 추출 → 판정 → 설명)을 잰다.
#   설계: 점유(독점)하는 것은 모델뿐이다.
#     - 추출 모델: 한 번에 문서 1건     (EXTRACT_WORKERS=1)
#     - 판정 쪽 모델(설명): 한 번에 1건 (EXPLAIN_WORKERS=1)
#     - 그 밖의 OCR·전처리는 제한 없이 동시에: PDF 수만큼 전처리(6)와 OCR 워커(6)
# 앞선 실험 스크립트(after_build.sh)가 끝난 뒤에 시작한다.
set -uo pipefail
while pgrep -f "[a]fter_build.sh" >/dev/null; do sleep 5; done
echo "######## 설계 구성 실험 C: OCR 워커 6개, 전처리 6, 추출 1, 설명 1  $(date +%T)"
cd "$HOME/perf"
OCR=1 JUDGE=1 PREPROCESS_WORKERS=6 OCR_WORKERS=6 EXPLAIN_WORKERS=1 ./run_real.sh "1" dC
echo "== 설계 구성 실험 끝 $(date +%T)"
