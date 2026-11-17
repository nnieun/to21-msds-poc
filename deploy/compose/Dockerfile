# syntax=docker/dockerfile:1
# 앱 이미지: 화면(정적 빌드) + 추출·판정 API. 빌드 위치는 저장소 최상위(compose.yaml의 context).
# TO21 자료(to21/)와 데이터(data/)는 이미지에 넣지 않는다(D-47). 실행할 때 마운트한다.

# ── 1) 화면 정적 빌드 (Next.js output: export → frontend/out) ─────────────
FROM node:24-slim AS web
RUN corepack enable
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV NEXT_PUBLIC_API_BASE=""
RUN pnpm build

# ── 2) 앱 ───────────────────────────────────────────────────────────────
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS ocr
# 글자추출(OCR) 워커 이미지: PaddleOCR + Docling(GPU). compose.ocr.yaml이 target: ocr 로 빌드한다.
# 이 단계는 app 단계보다 위에 둔다. 대상을 안 주면 파일의 마지막 단계(app)가 기본 빌드 대상이기 때문이다.
# UV_NO_CACHE=1: uv가 내려받은 파일의 보관본(/root/.cache/uv)을 이미지에 남기지 않는다.
# 처음 빌드에서 이 보관본이 14GB나 차지해 이미지가 31.8GB가 됐고, 저장(압축)에 20분 넘게 걸렸다.
ENV PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/backend/src
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates libgl1 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --break-system-packages uv
WORKDIR /app/backend
# 의존성은 uv.lock에 고정된 버전 그대로. OCR 그룹(paddleocr, paddlepaddle-gpu, docling, onnxruntime-gpu)을 더한다
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --group ocr --no-install-project --python /usr/bin/python3
# torch(CUDA 13 빌드)와 paddle(CUDA 12 빌드)은 NCCL을 같은 경로(nvidia/nccl/lib/libnccl.so.2)에 설치한다.
# 파일이 하나라 나중에 깔린 옛 버전(cu12 2.27)이 남으면 torch가 `undefined symbol: ncclCommResume`로 import에 실패하고,
# Docling(torch)은 조용히 GPU 없이 기본 좌표로 넘어간다. cu13 버전(2.30.7)을 마지막에 다시 깔아 덮어쓰면
# torch와 paddle이 한 프로세스에서 모두 GPU로 동작한다(2026-11-08 H100에서 두 import 순서 모두 확인).
RUN uv pip install --python /opt/venv/bin/python --no-deps --reinstall nvidia-nccl-cu13==2.30.7
COPY backend/ ./
COPY deploy/compose/ocr /app/deploy/compose/ocr
# 이 이미지의 기본 사용자 ubuntu(uid 1000)는 app 이미지의 app(uid 1000)과 같은 번호라 공유 볼륨을 같이 쓸 수 있다
RUN mkdir -p /app/data/extraction_api /app/data/pages /models && chown -R ubuntu:ubuntu /app/data /models
USER ubuntu

# ── 앱 (기본 빌드 대상) ──────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS app
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/backend/src
RUN pip install --no-cache-dir uv

# 앱은 결과에 코드 버전(git rev-parse HEAD)을 기록하고, 판정으로 넘길 때 그 값이 없으면 409로 거절한다
# (service/handoff.py). 그래서 git이 필요하다. .git은 이미지에 넣지 않고 실행 때 마운트한다(compose.yaml).
# 마운트한 .git의 소유자가 컨테이너 사용자와 달라 git이 거부하지 않도록 /app을 안전한 폴더로 등록한다.
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /app

WORKDIR /app/backend
# 의존성은 uv.lock에 고정된 버전 그대로(런타임만, dev 제외). 소스보다 먼저 복사해 캐시를 살린다
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY deploy/compose/app /app/deploy/compose/app
# 판정으로 넘길 때 앱이 읽는 데이터 계약(service/handoff.py). docs/ 전체는 넣지 않고 이것만 넣는다
COPY docs/contracts /app/docs/contracts
COPY --from=web /src/frontend/out /app/frontend/out

# 쓰기 필요한 곳: 올린 파일(data/service), 시작 때 만드는 프롬프트
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data/service /app/data/pages /app/data/extraction_api /app/to21/v0.6 \
 && chown -R app:app /app/data /app/backend/src/msds/extract/prompts
USER app
EXPOSE 8020
