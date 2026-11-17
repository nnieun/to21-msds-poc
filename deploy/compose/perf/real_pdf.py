#!/usr/bin/env python3
"""진짜 PDF 부하: PDF 여러 건을 동시에 올리고 문서별·전체 소요 시간을 잰다 (서버에서 실행, 파이썬 표준 라이브러리만 사용).

사용: real_pdf.py <라벨> <pdf> [<pdf> ...] [--base http://localhost:8080]
- 모든 PDF를 한꺼번에 올린다(화면에서 여러 건을 올리는 것과 같다). 업로드는 reuse=false라 같은 PDF도 처음부터 처리한다.
- 추출이 끝날 때까지(done/failed/stopped) 2초마다 조회하고, 문서별 상태 변화 시각을 기록한다. 판정 단계는 재지 않는다.
- 비밀번호는 deploy/compose/.env 에서 읽고 출력하지 않는다.
"""
import argparse
import base64
import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("label")
ap.add_argument("pdfs", nargs="+")
ap.add_argument("--base", default="http://localhost:8080")
ap.add_argument("--env", default=str(Path.home() / "to21-msds-poc/deploy/compose/.env"))
ap.add_argument("--out", default=str(Path.home() / "perf/results"))
ap.add_argument("--limit", type=int, default=1500, help="이 초를 넘으면 기다리기를 멈춘다")
ap.add_argument("--judge", action="store_true",
                help="추출이 끝난 문서를 판정으로 넘기고 판정 로직과 LLM 설명이 끝날 때까지 잰다 (전체 흐름)")
args = ap.parse_args()

pw = next(line.split("=", 1)[1].strip() for line in Path(args.env).read_text().splitlines() if line.startswith("WEB_PASSWORD="))
AUTH = "Basic " + base64.b64encode(f"to21:{pw}".encode()).decode()


def call(method, path, body=None, ctype="application/json"):
    req = urllib.request.Request(args.base + path, data=body, method=method,
                                 headers={"Authorization": AUTH, "Content-Type": ctype, "User-Agent": "Mozilla/5.0 (to21 perf)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read() or b"null")


T0 = time.time()
docs = {}
lock = threading.Lock()


def run(pdf, idx):
    name = f"{Path(pdf).stem}__{idx:02d}.pdf"   # 같은 PDF를 여러 번 넣어도 문서별로 구분된다(부하 시험)
    rec = {"file": name, "events": []}
    with lock:
        docs[name] = rec
    t = time.time() - T0
    up = call("POST", "/api/documents?filename=" + urllib.parse.quote(name) + "&reuse=false", Path(pdf).read_bytes(), "application/pdf")
    rec["id"] = up["id"]
    rec["uploaded_s"] = round(time.time() - T0, 2)
    last = None
    while True:
        s = call("GET", f"/api/documents/{up['id']}")
        key = (s.get("status"), s.get("stage"))
        now = round(time.time() - T0, 2)
        if key != last:
            rec["events"].append({"t": now, "status": key[0], "stage": key[1]})
            last = key
        if key[0] in ("done", "failed", "stopped"):
            rec["status"] = key[0]
            rec["finished_s"] = now
            rec["reused_from"] = s.get("reused_from")
            break
        if time.time() - T0 > args.limit:
            rec["status"] = "timeout"
            rec["finished_s"] = now
            break
        time.sleep(2)

    # 전체 흐름: 추출이 끝난 문서를 판정으로 넘기고, 판정 로직(규칙)과 LLM 설명이 끝날 때까지 기다린다.
    # 설명은 model_gate에서 추출보다 낮은 우선순위(explain)로 대기한다.
    if args.judge and rec.get("status") == "done":
        try:
            rec["handoff_s"] = round(time.time() - T0, 2)
            call("POST", f"/api/documents/{up['id']}/to-judgment", json.dumps({"reviewer": "perf"}).encode())
            rec["events"].append({"t": rec["handoff_s"], "status": "judge", "stage": "to-judgment"})
            judged = False
            while True:
                st = call("GET", f"/api/judgments/{up['id']}/status")
                now = round(time.time() - T0, 2)
                ex = st.get("explanations") or {}
                if st.get("state") == "판정 있음" and not judged:
                    judged = True
                    rec["judged_s"] = now
                    rec["events"].append({"t": now, "status": "judge", "stage": "판정 완료"})
                if st.get("error"):
                    rec["judge_error"] = str(st["error"])[:200]
                    break
                if judged and ex.get("done") == ex.get("total"):
                    rec["explained_s"] = now
                    rec["explanations"] = ex
                    rec["events"].append({"t": now, "status": "judge", "stage": "설명 완료"})
                    break
                if time.time() - T0 > args.limit:
                    rec["judge_error"] = "timeout"
                    break
                time.sleep(2)
        except Exception as error:
            rec["judge_error"] = f"{type(error).__name__}: {error}"[:200]


start_wall = time.strftime("%Y/%m/%d %H:%M:%S")
threads = [threading.Thread(target=run, args=(p, i)) for i, p in enumerate(args.pdfs)]
for th in threads:
    th.start()
for th in threads:
    th.join()
total = round(time.time() - T0, 1)

ok = [d for d in docs.values() if d.get("status") == "done"]
lat = sorted(d["finished_s"] - d["uploaded_s"] for d in ok)
summary = {
    "label": args.label, "start": start_wall, "docs": len(args.pdfs), "done": len(ok),
    "makespan_s": total,
    "per_doc_s": [round(x, 1) for x in lat],
    "p95_doc_s": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1) if lat else None,
    "median_doc_s": round(lat[len(lat) // 2], 1) if lat else None,
    "reused": [d["file"] for d in docs.values() if d.get("reused_from")],
    "detail": list(docs.values()),
}
if args.judge:
    judged = [d for d in ok if "explained_s" in d]
    summary["judge"] = {
        "documents": len(judged),
        "errors": [d.get("judge_error") for d in ok if d.get("judge_error")],
        "rules_s": [round(d["judged_s"] - d["finished_s"], 1) for d in judged],        # 판정 로직: 넘긴 뒤 판정이 나오기까지
        "explain_s": [round(d["explained_s"] - d["judged_s"], 1) for d in judged],      # LLM 설명이 끝나기까지
        "full_s": [round(d["explained_s"] - d["uploaded_s"], 1) for d in judged],       # 업로드부터 설명 완료까지
    }
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / f"real_{args.label}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
print(f"[{args.label}] 시작 {start_wall} | 문서 {summary['done']}/{summary['docs']} 완료 | 전체 {total}s | 문서별 {summary['per_doc_s']} | 중앙값 {summary['median_doc_s']}s"
      + (f" | 재사용됨 {summary['reused']}" if summary["reused"] else ""))
if args.judge:
    j = summary["judge"]
    print(f"  전체 흐름(판정+설명 포함): {j['documents']}/{len(ok)}건 | 업로드→설명 완료 {j['full_s']} | 판정 로직 {j['rules_s']} | LLM 설명 {j['explain_s']}"
          + (f" | 오류 {j['errors']}" if j["errors"] else ""))
