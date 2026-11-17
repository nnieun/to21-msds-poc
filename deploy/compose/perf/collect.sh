#!/usr/bin/env bash
# 서버에서 실행: GPU와 vLLM 내부 지표를 2초마다 CSV로 기록한다. 끝내려면 pkill -f collect.sh
# 사용: collect.sh [결과 폴더]   (기본 ~/perf/results)
set -uo pipefail
OUT="${1:-$HOME/perf/results}"; INTERVAL="${INTERVAL:-2}"
mkdir -p "$OUT"

IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' to21-msds-vllm-1)
[ -n "$IP" ] || { echo "vllm 컨테이너를 찾지 못했습니다" >&2; exit 1; }

nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv -l "$INTERVAL" > "$OUT/gpu.csv" &
GPU_PID=$!
trap 'kill $GPU_PID 2>/dev/null' EXIT INT TERM

echo "ts,running,waiting,kv_cache_perc,prefix_queries,prefix_hits,prompt_tokens,generation_tokens" > "$OUT/vllm_metrics.csv"

# /metrics 본문(M)에서 이름이 n 인 지표의 값을 합산한다. 이름 뒤에 { 가 붙은 줄만 본다(예: _by_reason 변형 제외)
v() { printf '%s\n' "$M" | awk -v n="$1" 'index($0, n"{")==1 { s += $NF } END { printf "%s", s + 0 }'; }

while true; do
  M=$(curl -s -m 3 "http://$IP:8000/metrics" || true)
  echo "$(date '+%Y/%m/%d %H:%M:%S'),$(v vllm:num_requests_running),$(v vllm:num_requests_waiting),$(v vllm:kv_cache_usage_perc),$(v vllm:prefix_cache_queries_total),$(v vllm:prefix_cache_hits_total),$(v vllm:prompt_tokens_total),$(v vllm:generation_tokens_total)" >> "$OUT/vllm_metrics.csv"
  sleep "$INTERVAL"
done
