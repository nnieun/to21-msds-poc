#!/usr/bin/env bash
# 서버에서 실행: 재빌드(ocr_build3.log에 "재빌드 끝")가 끝나면
#   1) 새 이미지(to21-msds-ocr:fixed)로 OCR 워커를 교체하고
#   2) 손대지 않은 새 이미지에서 torch와 paddle이 GPU로 동작하는지 검증한 뒤(NCCL 수정이 이미지에 들어갔는지)
#   3) 설계대로(OCR은 문서를 한꺼번에, 모델 추출은 한 번에 한 문서) 전체 흐름(OCR→추출→판정→설명)을 재는 실험 2번을 돈다.
#      A: OCR 워커 1개, B: OCR 워커 2개. 문서 6건 전부를 OCR 큐에 바로 넣는다(PREPROCESS_WORKERS=6).
set -uo pipefail
cd "$HOME/to21-msds-poc/deploy/compose"
export COMPOSE_FILE=compose.yaml:compose.ocr.yaml GPU_UTIL=0.72

while ! grep -q "재빌드 끝" "$HOME/perf/ocr_build3.log" 2>/dev/null; do sleep 5; done
echo "== 재빌드 결과 $(date +%T)"; tail -3 "$HOME/perf/ocr_build3.log" | cut -c1-120
docker image inspect to21-msds-ocr:fixed >/dev/null 2>&1 || { echo "새 이미지가 없습니다 -> 중단"; exit 1; }
echo "== 이미지 크기"; docker images to21-msds-ocr --format "  {{.Tag}} {{.Size}}"

docker tag to21-msds-ocr:fixed to21-msds-ocr:latest
echo "== OCR 워커를 새 이미지로 교체 $(date +%T)"
docker compose up -d --force-recreate --wait ocr-worker 2>&1 | tail -2
sleep 6

echo "== 검증: 손대지 않은 새 이미지에서 torch + paddle GPU"
if docker exec to21-msds-ocr-worker-1 python -c "
import sys, torch
ok = torch.cuda.is_available()
print('torch', torch.__version__, '| GPU 사용 가능:', ok)
import paddle
print('paddle GPU 수:', paddle.device.cuda.device_count())
sys.exit(0 if ok else 1)" 2>&1 | grep -v -i warn | tail -3; then
  echo "검증 통과"
else
  echo "검증 실패 -> 측정 안 함"; exit 1
fi
[ "$(docker exec to21-msds-ocr-worker-1 python -c 'import torch;print(torch.cuda.is_available())' 2>/dev/null | tail -1)" = "True" ] || { echo "검증 실패(재확인) -> 측정 안 함"; exit 1; }

cd "$HOME/perf"
for cfg in "A 1" "B 2"; do
  set -- $cfg
  echo; echo "######## 실험 $1: OCR 워커 $2개 (OCR은 6건 동시, 모델 추출은 한 번에 한 문서) $(date +%T)"
  OCR=1 JUDGE=1 PREPROCESS_WORKERS=6 OCR_WORKERS=$2 ./run_real.sh "1" "d$1"
done
echo; echo "== 전부 끝 $(date +%T)"
