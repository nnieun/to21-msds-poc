# Docker compose 배포 (GPU 서버 1대)

Docker가 되는 NVIDIA GPU 서버 한 대에 모델(vLLM)·DB·앱·웹을 모두 올립니다. RunPod 시연 서버(`deploy/runpod/demo`)와 같은 구성을 컨테이너로 옮긴 것입니다.

> **2026-11-08에 실제 GPU 서버(Lambda 1x H100 PCIe 80GB)에서 빌드·기동해 PDF를 끝까지 돌려 확인했습니다.** vLLM 이미지는 `vllm/vllm-openai:v0.32.0`입니다. 기본 구성과 OCR 구성 모두 측정했고, 결과는 [PERF_RESULTS.md](PERF_RESULTS.md)에 있습니다.

```
브라우저 ─▶ web(Apache :8080, Basic 인증) ─▶ app(:8020, 화면+추출+판정)
                                               ├▶ vllm(:8000, 밖으로 열지 않음)
                                               └▶ db(PostgreSQL, 밖으로 열지 않음)
```

| 컨테이너 | 하는 일 |
|---|---|
| `vllm` | Qwen3.6-35B-A3B-FP8 서빙. GPU 사용. 모델은 첫 기동에 내려받음(약 35GB) |
| `db` | PostgreSQL 16. 첫 기동에 지식DB 덤프를 복원 |
| `migrate` | 서비스 DB(`msds_service`)와 표 생성. 끝나면 종료 |
| `app` | 화면(정적 빌드)과 추출·판정 API |
| `web` | Apache. Basic 인증(아이디 `to21`)과 프록시. **바깥에 열리는 건 이것뿐(8080)** |

**기본 구성(`compose.yaml`)에는 글자추출(OCR)을 넣지 않았습니다.** L40S 체험 서버(`deploy/runpod/demo`)처럼 `MSDS_PREPROCESS=legacy`(PDF 글자층과 쪽 이미지)로 돌립니다. 프로젝트의 최종 전처리(version17, PaddleOCR + Docling, GPU)와 글자추출 API·OCR 워커(DB 작업 대기열)는 `compose.ocr.yaml`을 겹쳐서 켭니다(`GPU_UTIL=0.72 docker compose -f compose.yaml -f compose.ocr.yaml up -d`). OCR 구성도 같은 서버에서 띄워 Docling이 GPU를 쓰는 것을 확인했고, PDF 48건을 한꺼번에 넣어도 추출 실패가 없었습니다([PERF_RESULTS.md](PERF_RESULTS.md) 7장).

## 필요한 것

- NVIDIA GPU 48GB 이상, Docker + Compose, NVIDIA Container Toolkit (Lambda Stack 이미지는 기본 포함)
- TO21 자료: `to21/v0.6/` (명세서, 스키마 등)
- 지식DB 덤프: `data/kdb.dump`, `data/globals.sql` (아래 2단계)

TO21 자료와 덤프는 **저장소에 올리지 않고** 이미지에도 넣지 않습니다(D-47). 덤프는 `.gitignore`가 막고, `to21/`는 컨테이너에 마운트합니다. 빌드한 이미지는 레지스트리에 올리지 마세요.

## 순서

모든 명령은 서버의 `deploy/compose/`에서 실행합니다.

### 1. 코드와 자료 올리기 (내 컴퓨터에서)
```bash
scp -r <저장소 폴더> ubuntu@<IP>:~/to21-msds-poc          # to21/v0.6/ 도 같이 간다(git이 아니라 scp)
scp "<HTODB.zip 경로>" ubuntu@<IP>:~/
```

### 2. 지식DB 덤프 만들기 (처음 한 번)
덤프가 이미 있으면(`data/kdb.dump`, `data/globals.sql`) 이 단계는 건너뜁니다.
```bash
cd ~/to21-msds-poc/backend && uv sync                      # uv가 없으면 먼저 설치
cd .. && deploy/htodb/setup.sh ~/HTODB.zip                 # SQL Server로 읽어 PostgreSQL에 적재. 10~20분
deploy/compose/export-kdb.sh                               # data/ 에 덤프 생성
```
서버를 지우면 사라지니 덤프는 내 컴퓨터로 받아 두세요. 다음부터는 이 단계 없이 복원만 합니다.
```bash
scp ubuntu@<IP>:~/to21-msds-poc/deploy/compose/data/{kdb.dump,globals.sql} <내 컴퓨터 폴더>
```
`setup.sh`가 띄운 htodb용 컨테이너는 compose와 포트가 겹치지 않지만 램을 쓰니 끝나면 내립니다: `docker compose -f deploy/htodb/compose.yaml down` (볼륨은 지우지 않음).

### 3. 준비 점검
```bash
cd deploy/compose
./gen-env.sh        # .env를 무작위 비밀번호로 만든다
./preflight.sh      # 빠진 것이 있으면 알려 준다
```

### 4. 빌드와 기동
```bash
docker compose build                # app 이미지. 화면 빌드 포함 5~10분
docker compose up -d vllm           # 모델 내려받기 + 올리기. 첫 기동 10~30분
docker compose logs -f vllm         # "Application startup complete" 가 나올 때까지
docker compose up -d                # db, migrate, app, web
```
`up -d`는 vLLM이 healthy가 될 때까지 app을 기다립니다. 그래서 vLLM을 먼저 따로 띄워 두었습니다.

### 5. 확인
```bash
docker compose ps                                              # vllm, db, app, web 이 healthy/running
curl -u to21:$(grep ^WEB_PASSWORD .env | cut -d= -f2) localhost:8080/api/health
```
밖에서 접속하려면 서버 방화벽(Lambda 콘솔의 Firewall)에서 **TCP 8080**을 열고 `http://<서버 IP>:8080`으로 들어갑니다. 아이디 `to21`, 비밀번호는 `.env`의 `WEB_PASSWORD`. HTTPS는 아니니 연습·시연용으로만 쓰세요.
PDF 한 건을 끝까지 돌려 보려면 `python3 deploy/runpod/demo/smoke_test.py http://<IP>:8080 <PDF> <비밀번호>`.

### 6. 끝나면
Lambda는 일시정지가 없고 **Terminate해야 과금이 멈춥니다.** 지우면 서버 안의 모델·DB·올린 파일이 모두 사라집니다. 필요한 결과는 지우기 전에 받아 두세요.

## 자주 쓰는 명령

```bash
docker compose logs -f app            # 앱 로그
docker compose restart app            # 앱만 다시 켜기
docker compose down                   # 내리기 (볼륨은 남음: DB, 모델 캐시, 올린 파일)
docker compose down -v                # 볼륨까지 지움 (DB도 모델 캐시도 사라짐)
```

## 막혔을 때

| 증상 | 원인과 해결 |
|---|---|
| `db`가 비어 있는 DB로 뜸 | 덤프 없이 처음 띄우면 첫 기동 복원이 건너뛰어진 채 굳습니다. 덤프를 `data/`에 두고 `docker compose down -v` 후 다시 시작 |
| `vllm`이 `unauthorized`/이미지를 못 받음 | `.env`의 `VLLM_IMAGE` 태그가 없는 것입니다. `docker pull vllm/vllm-openai:<태그>`로 확인해서 바꿉니다 |
| `vllm`이 GPU를 못 찾음 | `docker info`에 nvidia 런타임이 있는지, `nvidia-smi`가 되는지 확인(`./preflight.sh`) |
| `vllm`이 메모리 부족으로 죽음 | `.env`에서 `GPU_UTIL`을 낮추거나 `MAX_MODEL_LEN`, `MAX_NUM_SEQS`를 줄입니다 |
| `app`이 시작하자마자 종료 | `docker compose logs app`. 명세서가 없으면 `to21/v0.6/` 확인 |
| `migrate` 실패 | `docker compose logs migrate`. 대개 덤프의 지식DB가 비었거나 DB 비밀번호가 바뀐 경우 |
| 웹에서 502 | `app`이 아직 켜지는 중일 수 있습니다. `docker compose ps`로 app이 healthy인지 확인 |

## 설정 값 (`.env`)

견본과 설명은 [.env.example](.env.example). 모델 서버 옵션(`MAX_MODEL_LEN`, `MAX_NUM_SEQS`, `GPU_UTIL`)은 `deploy/runpod/serve_vllm.sh`와 `backend/configs/models.yaml`의 48GB 태그 값과 같습니다.
80GB GPU에서는 `MAX_NUM_SEQS`를 올려 동시 처리를 늘릴 수 있지만, 앱의 판정 설명은 동시 수가 늘면 결과가 달라질 수 있어(README의 설명 LLM 실험) 기본값 8을 유지했습니다.
