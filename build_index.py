"""3단계: 조문을 조각(chunk)으로 나누고 임베딩해 검색 색인을 만듭니다.

조각마다 '인용 라벨'을 붙여 두는 것이 핵심입니다.
  예) 서울특별시 주차장 설치 및 관리 조례 제7조 제3항
LLM은 이 라벨을 고르기만 하고, 조항 표기를 직접 쓰지 않습니다.

실행:  python -X utf8 build_index.py             (CHUNK_UNIT=paragraph 기본)
       set CHUNK_UNIT=article & python -X utf8 build_index.py   (조 단위, 시연 '전' 장면)
결과:  data/chunks_<단위>.json, data/vectors_<단위>.npy
"""
import json

import numpy as np

import config
from parse_annex import annex_path


def make_chunks(laws, unit):
    chunks = []
    for law in laws:
        meta = {"law": law["name"], "effective_date": law["effective_date"], "source_url": law["source_url"]}
        for a in law["articles"]:
            head = f"{law['name']} {a['article']}({a['title']})"
            if unit == "article" or len(a["paragraphs"]) <= 1 or a["paragraphs"][0]["no"] is None:
                chunks.append({**meta, "label": f"{law['name']} {a['article']}",
                               "text": a["text"]})
                continue
            for p in a["paragraphs"]:
                chunks.append({**meta, "label": f"{law['name']} {a['article']} 제{p['no']}항",
                               "text": f"[{head}]\n{p['text']}"})
        for ax in law["annexes"]:
            if not ax["label"].startswith("별표"):
                continue
            parsed = annex_path(law["mst"], ax["label"])
            if config.USE_PARSED_ANNEX and parsed.exists():
                body, src = parsed.read_text(encoding="utf-8"), "document-parse"
            else:
                body, src = ax["text"], "law.go.kr 원문(괘선 표)"
            # 긴 별표는 잘라서 넣되 라벨은 같게 둡니다
            for i in range(0, max(len(body), 1), 1800):
                chunks.append({**meta, "label": f"{law['name']} {ax['label']}",
                               "text": f"[{law['name']} {ax['label']} {ax['title']}]\n{body[i:i + 1800]}",
                               "annex_source": src})
    for i, c in enumerate(chunks):
        c["id"] = i
    return chunks


def main():
    laws = json.loads((config.DATA / "ordinances.json").read_text(encoding="utf-8"))
    unit = config.CHUNK_UNIT
    chunks = make_chunks(laws, unit)
    (config.DATA / f"chunks_{unit}.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"조각 {len(chunks)}개 ({unit} 단위)")

    if not config.UPSTAGE_API_KEY:
        print("⚠ API 키가 없어 임베딩은 건너뜁니다. 키워드 검색만 동작합니다.")
        return
    import upstage
    vecs = upstage.embed([c["text"] for c in chunks], config.EMBED_PASSAGE)
    np.save(config.DATA / f"vectors_{unit}.npy", np.array(vecs, dtype=np.float32))
    print("임베딩 저장 완료")


if __name__ == "__main__":
    main()
