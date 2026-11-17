"""OCR 모델 가중치를 볼륨(/models)에 받는다. 앱은 설치된 가중치만 쓰고 직접 내려받지 않는다(pdf_pipeline).
한 번 받으면 볼륨에 남고, 이미 있으면 건너뛴다. 필요한 것:
- PaddleOCR: PP-OCRv5_server_det, korean_PP-OCRv5_mobile_rec  -> $TO21_OCR_MODELS_DIR/<이름>
- Docling: docling-project/docling-models, docling-project/docling-layout-heron -> HF 캐시($HF_HOME)
(근거: deploy/runpod/demo/README.md 의 OCR 가중치 설치 절차)
"""
import os
from pathlib import Path

from huggingface_hub import snapshot_download

models = Path(os.environ.get("TO21_OCR_MODELS_DIR", "/models/paddlex/official_models"))
models.mkdir(parents=True, exist_ok=True)

for name in ("PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec"):
    folder = models / name
    if (folder / "inference.yml").is_file() and any(folder.glob("*.pdiparams")):
        print(f"있음: {name}", flush=True)
        continue
    print(f"받는 중: PaddlePaddle/{name}", flush=True)
    snapshot_download(f"PaddlePaddle/{name}", local_dir=str(folder))

for repo in ("docling-project/docling-models", "docling-project/docling-layout-heron"):
    print(f"받는 중(이미 있으면 확인만): {repo}", flush=True)
    snapshot_download(repo)

print("OCR 모델 준비 끝", flush=True)
