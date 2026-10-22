"""셀프 채점기: 공개 예시 문항으로 대회 채점 방식을 흉내 냅니다.

  근거 정확도  항까지 일치 1.0 · 조까지만 일치 0.5 · 별표 인용도 정답 인정
  함정 문항    answer가 "확인 불가"이고 citation이 []이면 정답
  형식         source_url · effective_date가 비어 있지 않은지, 90초 안에 응답했는지

실행:
  python -X utf8 check.py --retrieval      검색만 점검 (API 키 없이도 동작)
  python -X utf8 check.py                  로컬 함수로 전체 채점
  python -X utf8 check.py --url http://localhost:8000/ask   서버로 채점 (제출 전 최종 점검)

※ 실제 채점 규칙의 세부(인용을 여러 개 냈을 때의 처리 등)는 운영진 공지가 기준입니다.
"""
import argparse
import json
import re
import time
from datetime import datetime

import config

CITE = re.compile(r"(서울특별시.*?(?:조례|규칙))\s*(제\d+조(?:의\d+)?|별표\s*\d*|별도\s*\d+)\s*(제\d+항)?")


def parse(c):
    m = CITE.search(c.replace(" ", " "))
    if not m:
        return None
    law = re.sub(r"\s+", "", m.group(1))
    art = re.sub(r"\s+", "", m.group(2))
    para = m.group(3)
    return law, art, para


def match(pred, gold):
    p, g = parse(pred), parse(gold)
    if not p or not g or p[0] != g[0] or p[1] != g[1]:
        return 0.0
    if g[2] is None or p[2] == g[2]:
        return 1.0
    return 0.5


def score_citation(preds, gold):
    """gold: [[대안1, 대안2], [다음 필수 근거], ...]"""
    if not gold:
        return None
    total = 0.0
    for alts in gold:
        total += max((match(p, a) for p in preds for a in alts), default=0.0)
    return total / len(gold)


def run_retrieval(qs):
    import rag
    print(f"[검색 점검] 단위={config.CHUNK_UNIT}  top_k={config.TOP_K}\n")
    hit_n = 0
    for q in qs:
        if not q["gold"]:
            hits = rag.retrieve(q["question"])
            print(f"{q['id']:3} 함정   top1={hits[0]['label']}  (score {hits[0]['score']:.2f})")
            continue
        labels = [h["label"] for h in rag.retrieve(q["question"])]
        sc = score_citation(labels, q["gold"])
        hit_n += sc
        mark = "✓" if sc == 1 else ("△" if sc > 0 else "✗")
        print(f"{q['id']:3} {mark} {sc:.2f}  {q['question'][:34]}")
        if sc < 1:
            print("      찾은 것:", labels[:3])
    n = sum(1 for q in qs if q["gold"])
    print(f"\n정답 근거가 top-{config.TOP_K} 안에 들어온 비율: {hit_n / n:.0%}")


def run_full(qs, url=None):
    if url:
        import requests
        call = lambda q: requests.post(url, json={"question": q}, timeout=90).json()  # noqa: E731
    else:
        import rag
        call = rag.answer
    rows, cite_scores, trap_ok = [], [], []
    for q in qs:
        t0 = time.time()
        try:
            r = call(q["question"])
            err = None
        except Exception as e:  # noqa: BLE001
            r, err = {}, repr(e)
        sec = time.time() - t0
        unknown = r.get("answer", "").startswith("확인 불가") and r.get("citation") == []
        if q["gold"]:
            sc = 0.0 if err or sec > 90 else score_citation(r.get("citation", []), q["gold"])
            cite_scores.append(sc)
        else:
            sc = 1.0 if unknown and not err and sec <= 90 else 0.0
            trap_ok.append(sc)
        fmt_ok = unknown or (r.get("source_url", "").startswith("http") and
                             re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("effective_date", "")))
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"], "score": sc,
                     "sec": round(sec, 1), "format_ok": bool(fmt_ok), "error": err, "response": r,
                     "gold": q["gold"], "answer_key": q["answer_key"]})
        print(f"{q['id']:3} {sc:.2f}  {sec:5.1f}s  {'형식OK' if fmt_ok else '형식✗'}  {r.get('citation')}")
    print("\n근거 정확도(일반 문항 평균):", f"{sum(cite_scores) / max(len(cite_scores), 1):.2f}")
    print("함정 문항 정답률:", f"{sum(trap_ok) / max(len(trap_ok), 1):.0%}")
    out = config.ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"check_{datetime.now():%m%d_%H%M}_{config.CHUNK_UNIT}_v{int(config.USE_VERIFY)}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval", action="store_true")
    ap.add_argument("--url")
    ap.add_argument("--questions", default=str(config.ROOT / "sample_questions.json"))
    a = ap.parse_args()
    qs = json.loads(open(a.questions, encoding="utf-8").read())
    run_retrieval(qs) if a.retrieval else run_full(qs, a.url)
