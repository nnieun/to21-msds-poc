#!/usr/bin/env bash
# 서버에서 실행: 동시성을 바꿔 가며 vLLM 서빙 벤치마크를 돌리고 결과를 JSON으로 저장한다.
# 사용: run_sweep.sh <라벨> "<동시성 목록>" [반복 횟수=1]
# 예:   run_sweep.sh base "1 2 4 8 16" 1
#       INPUT_LEN=3800 OUTPUT_LEN=700 run_sweep.sh seqs32 "8 16 32" 1
# 작업량 기본값(입력 3800, 출력 700)은 실제 PDF 3건 처리에서 구한 평균이다(PERF_PLAN.md).
set -euo pipefail
LABEL="${1:?라벨이 필요합니다}"; LIST="${2:?동시성 목록이 필요합니다}"; REPEAT="${3:-1}"
IN="${INPUT_LEN:-3800}"; OUTLEN="${OUTPUT_LEN:-700}"; MODEL="${MODEL:-Qwen/Qwen3.6-35B-A3B-FP8}"
RES="$HOME/perf/results"; mkdir -p "$RES"
cd "$HOME/to21-msds-poc/deploy/compose"
docker compose exec -T vllm mkdir -p /tmp/perf

for r in $(seq 1 "$REPEAT"); do
  for c in $LIST; do
    n=$(( c * 8 < 32 ? 32 : c * 8 ))     # 요청 수는 동시성의 8배, 최소 32
    echo "== $LABEL conc=$c prompts=$n repeat=$r $(date +%T)"
    docker compose exec -T vllm bash -c "vllm bench serve \
      --backend openai --base-url http://127.0.0.1:8000 --endpoint /v1/completions --model $MODEL \
      --dataset-name random --random-input-len $IN --random-output-len $OUTLEN \
      --num-prompts $n --max-concurrency $c --num-warmups 4 --ignore-eos --seed $r \
      --percentile-metrics ttft,tpot,e2el --metric-percentiles 50,95,99 \
      --save-result --result-dir /tmp/perf --result-filename ${LABEL}_c${c}_r${r}.json \
      --header \"Authorization=Bearer \$VLLM_API_KEY\"" > "$RES/${LABEL}_c${c}_r${r}.log" 2>&1 \
      || { echo "실패: $RES/${LABEL}_c${c}_r${r}.log"; tail -5 "$RES/${LABEL}_c${c}_r${r}.log"; continue; }
    grep -E "Benchmark duration|Output token throughput|Median TTFT|P95 TTFT|Median E2EL|P95 E2EL" "$RES/${LABEL}_c${c}_r${r}.log" || true
  done
done
docker compose cp vllm:/tmp/perf/. "$RES/" >/dev/null
echo "끝: $RES"
