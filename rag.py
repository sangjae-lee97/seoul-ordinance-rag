
"""서울시 조례 RAG: 검색 → 답변 생성 → 근거 검증."""

import json
import math
import re
from collections import Counter

import numpy as np

import config

UNKNOWN = {
    "answer": "확인 불가",
    "citation": [],
    "source_url": "",
    "effective_date": "",
}

DISTRICT = re.compile(r"서울특별시\s*\S+구\s")
_cache = {}


# ------------------------------------------------------------
# 1. 검색 인덱스 및 키워드 처리
# ------------------------------------------------------------

def _bigrams(text):
    t = re.sub(r"\s+", "", text)
    return [t[i:i + 2] for i in range(len(t) - 1)]


def _load():
    unit = config.CHUNK_UNIT

    if unit in _cache:
        return _cache[unit]

    chunks = json.loads(
        (config.DATA / f"chunks_{unit}.json").read_text(
            encoding="utf-8"
        )
    )

    vec_path = config.DATA / f"vectors_{unit}.npy"
    vecs = np.load(vec_path) if vec_path.exists() else None

    if vecs is not None:
        vecs = vecs / np.linalg.norm(
            vecs, axis=1, keepdims=True
        )

    docs = [
        Counter(_bigrams(c["label"] + " " + c["text"]))
        for c in chunks
    ]

    df = Counter(g for d in docs for g in d)
    avg = sum(sum(d.values()) for d in docs) / len(docs)

    _cache[unit] = (chunks, vecs, docs, df, avg)
    return _cache[unit]


def _bm25(query, docs, df, avg, k1=1.2, b=0.75):
    n = len(docs)
    q = set(_bigrams(query))
    scores = np.zeros(n)

    for i, d in enumerate(docs):
        ln = sum(d.values())
        s = 0.0

        for g in q:
            if g in d:
                idf = math.log(
                    1 + (n - df[g] + 0.5) / (df[g] + 0.5)
                )
                s += (
                    idf * d[g] * (k1 + 1)
                    / (d[g] + k1 * (1 - b + b * ln / avg))
                )

        scores[i] = s

    return scores


# ------------------------------------------------------------
# 2. Query Expansion
# ------------------------------------------------------------

def _expand_query(question):
    """사용자 표현을 법령 검색 용어로 보강합니다."""
    additions = []

    rules = [
        (r"말하는|뜻|의미|이란|무엇인가", "정의"),
        (r"할인", "감면"),
        (r"둘 다|동시에|중복", "둘 이상의 중복 적용"),
        (r"술|마시", "음주"),
        (r"어떻게 되나요|처벌|벌금", "제재 과태료"),
    ]

    for pattern, terms in rules:
        if re.search(pattern, question):
            additions.append(terms)

    if not additions:
        return question

    return question + " " + " ".join(additions)


def retrieve(question, top_k=config.TOP_K):
    """Embedding 70% + BM25 30% 혼합 검색."""
    chunks, vecs, docs, df, avg = _load()

    search_query = _expand_query(question)

    kw = _bm25(search_query, docs, df, avg)
    kw_norm = kw / kw.max() if kw.max() > 0 else kw

    if vecs is not None and config.UPSTAGE_API_KEY:
        import upstage

        q = np.array(
            upstage.embed(
                [search_query], config.EMBED_QUERY
            )[0],
            dtype=np.float32,
        )

        cos = vecs @ (q / np.linalg.norm(q))
        score = 0.7 * cos + 0.3 * kw_norm

    else:
        cos, score = None, kw_norm

    idx = np.argsort(score)[::-1][:top_k]

    return [
        {
            **chunks[i],
            "score": float(score[i]),
            "cos": float(cos[i]) if cos is not None else None,
        }
        for i in idx
    ]


# ------------------------------------------------------------
# 3. Solar 답변 생성
# ------------------------------------------------------------

SYSTEM = """너는 서울특별시 조례 질의응답 도우미다.

규칙:
- 반드시 아래 [근거]에 적힌 내용만으로 답한다.
- 근거에 없는 내용은 추측하지 않는다.
- 답은 일반 시민이 이해할 수 있는 쉬운 말로 2~4문장으로 쓴다.
- 금액·비율·나이 같은 숫자는 그대로 쓴다.
- 답에 실제로 쓴 근거 번호를 evidence_ids에 넣는다.
- 여러 조항을 함께 썼다면 모두 넣는다.
- 근거로 답할 수 없으면 found를 false로 한다.
- 자치구(OO구) 조례나 규칙은 근거로 쓰지 않는다.

추가 근거 선택 규칙:
- 답변에 사용한 금액·비율·나이·기간 등 숫자나 조건이
  특정 근거에만 있다면 그 근거 번호를 반드시
  evidence_ids에 포함한다.
- 답변에 직접 사용하지 않은 근거 번호는
  evidence_ids에 넣지 않는다.

결과는 JSON으로 낸다."""


SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "law_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "found": {"type": "boolean"},
                "answer": {"type": "string"},
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": [
                "found",
                "answer",
                "evidence_ids",
            ],
            "additionalProperties": False,
        },
    },
}


def _context(hits):
    return "\n\n".join(
        f"[근거 {i}] {h['label']}\n{h['text']}"
        for i, h in enumerate(hits, 1)
    )


def answer(question):
    import upstage

    hits = retrieve(question)

    # 검증 1: 검색 관련성 확인
    if (
        config.USE_VERIFY
        and hits
        and hits[0]["cos"] is not None
        and hits[0]["cos"] < config.MIN_SCORE
    ):
        return dict(UNKNOWN)

    # 검색된 근거를 Solar에 전달
    raw = upstage.chat(
        [
            {
                "role": "system",
                "content": SYSTEM,
            },
            {
                "role": "user",
                "content": (
                    f"[근거]\n{_context(hits)}"
                    f"\n\n[질문]\n{question}"
                ),
            },
        ],
        response_format=SCHEMA,
    )

    out = json.loads(raw)

    # LLM이 선택한 근거 번호를 실제 Chunk와 연결
    used = [
        hits[i - 1]
        for i in out.get("evidence_ids", [])
        if 1 <= i <= len(hits)
    ]

    used = [
        h for h in used
        if not DISTRICT.search(h["label"])
    ]

    if not out.get("found") or not used:
        return dict(UNKNOWN)

    # 검증 2: Solar Decide Groundedness
    if config.USE_VERIFY:
        verdict = upstage.groundedness(
            _context(used),
            out["answer"],
        )

        if verdict == "notGrounded":
            return dict(UNKNOWN)

    citation = list(
        dict.fromkeys(h["label"] for h in used)
    )

    first = used[0]

    return {
        "answer": out["answer"],
        "citation": citation,
        "source_url": first["source_url"],
        "effective_date": first["effective_date"],
    }


def answer_without_rag(question):
    """검색 없이 LLM만 사용하는 비교 시연."""
    import upstage

    return upstage.chat(
        [
            {
                "role": "system",
                "content": (
                    "너는 서울시 조례 전문가다. "
                    "답과 함께 근거 조항(제○조 제○항)과 "
                    "원문 링크, 시행일을 적어라."
                ),
            },
            {
                "role": "user",
                "content": question,
            },
        ],
        temperature=0.3,
    )
