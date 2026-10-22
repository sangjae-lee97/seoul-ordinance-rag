"""강의 시연용 스크립트. 장면마다 '전 → 후'를 나란히 보여 줍니다.

  python -X utf8 demo.py llm-only     2-3  검색 없이 LLM만: 그럴듯한 조항을 지어내는가
  python -X utf8 demo.py annex        2-2  별표: 괘선 원문 vs Document Parse 결과
  python -X utf8 demo.py chunk        2-4  조 단위 vs 항 단위: 인용이 어디까지 맞는가
  python -X utf8 demo.py trap         2-5  함정 질문: 검증을 끄면 / 켜면
"""
import json
import os
import sys

import config

Q_FEE = "서울시 공영주차장 1급지 노상주차장 요금은 5분에 얼마인가요?"
Q_LLM = "장애인 주차요금 감면되나요?"
TRAPS = ["서울시에서 자전거 탈 때 헬멧을 안 쓰면 과태료가 얼마인가요?",
         "강남구 부설주차장 관리 규칙에 따르면 부설주차장 개방 요금은 얼마인가요?"]


def bar(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def llm_only():
    import rag
    bar("[전] 검색 없이 Solar에게 바로 물으면")
    print(rag.answer_without_rag(Q_LLM))
    bar("[후] 조례 원문을 검색해 근거 번호를 고르게 하면")
    print(json.dumps(rag.answer(Q_LLM), ensure_ascii=False, indent=2))
    print("\n→ 확인할 것: '전'의 조항 번호·링크·시행일이 실제 원문과 맞는가? (원문: data/ordinances.json)")


def annex():
    import upstage
    from parse_annex import annex_path
    laws = json.loads((config.DATA / "ordinances.json").read_text(encoding="utf-8"))
    park = laws[0]
    ax = park["annexes"][0]
    raw = ax["text"]
    parsed_p = annex_path(park["mst"], ax["label"])
    bar("법제처 원문 별표 1 (괘선 표, 앞부분)")
    print(raw[:1200])
    if parsed_p.exists():
        bar("Document Parse 결과 (앞부분)")
        print(parsed_p.read_text(encoding="utf-8")[:1200])
    for name, body in [("[전] 괘선 원문", raw),
                       ("[후] Document Parse", parsed_p.read_text(encoding="utf-8") if parsed_p.exists() else None)]:
        if body is None:
            print("\n(parse_annex.py를 먼저 실행하세요)")
            continue
        bar(f"{name}을 근거로 주고 질문: {Q_FEE}")
        print(upstage.chat([{"role": "system", "content": "주어진 표만 보고 짧게 답하라."},
                            {"role": "user", "content": f"{body}\n\n질문: {Q_FEE}"}]))
    print("\n→ 정답: 500원 (노상주차장, 1회 주차 시 5분당, 1급지)")


def chunk():
    import subprocess
    for unit in ("article", "paragraph"):
        bar(f"CHUNK_UNIT={unit}")
        env = {**os.environ, "CHUNK_UNIT": unit}
        subprocess.run([sys.executable, "-X", "utf8", "check.py", "--retrieval"], env=env, check=False)


def trap():
    import importlib
    for flag in ("0", "1"):
        os.environ["USE_VERIFY"] = flag
        importlib.reload(config)
        import rag
        importlib.reload(rag)
        bar(f"USE_VERIFY={flag}  ({'검증 끔' if flag == '0' else '검증 켬: 점수 기준선 + Groundedness Check'})")
        for q in TRAPS:
            print("Q:", q)
            print("A:", json.dumps(rag.answer(q), ensure_ascii=False))


if __name__ == "__main__":
    scenes = {"llm-only": llm_only, "annex": annex, "chunk": chunk, "trap": trap}
    if len(sys.argv) < 2 or sys.argv[1] not in scenes:
        print(__doc__)
        sys.exit(1)
    scenes[sys.argv[1]]()
