# 서울시 조례 Q&A — Upstage Solar RAG 프로젝트

## 1. 프로젝트 소개

Upstage Solar 모델과 RAG(Retrieval-Augmented Generation)를 이용해 서울특별시 조례를 검색하고, 실제 법령을 근거로 답변하는 AI 질의응답 시스템입니다.

단순히 질문에 답하는 것이 아니라 다음 정보를 함께 제공합니다.

- 답변 내용 (`answer`)
- 근거 조례 및 조항 (`citation`)
- 법령 원문 주소 (`source_url`)
- 조례 시행일 (`effective_date`)

**핵심 목표:** 근거가 없는 내용을 생성하지 않고, 검증 가능한 법령 정보를 제공하는 것.

---

## 2. 기술 스택

| 구분 | 기술 |
|---|---|
| 개발 언어 | Python |
| LLM | Upstage Solar Pro 4 |
| 문서 처리 | Upstage Document Parse |
| 문서 데이터 추출 | Upstage Extract (Studio 실습) |
| Embedding | Solar Embedding 2 |
| 검색 | BM25 + Vector Similarity |
| 근거 검증 | Solar Decide |
| API 서버 | FastAPI, Uvicorn |
| 데이터 수집 | 법제처 OPEN API |
| 개발 환경 | Windows 11, VS Code |

---

## 3. 전체 시스템 구조

```text
[데이터 준비]

법제처 OPEN API
       |
       v
서울특별시 조례 6종 수집
       |
       v
Document Parse (별표 구조 복원)
       |
       v
Chunking (항 단위 528개)
       |
       v
Solar Embedding
       |
       v
검색 인덱스 저장


[질의응답]

사용자 질문
       |
       v
Query Expansion
       |
       v
Hybrid Search (Embedding + BM25)
       |
       v
관련 법령 Top-6 검색
       |
       v
Solar Pro 4 답변 생성
       |
       v
Solar Decide 근거 검증
       |
       v
Citation / URL / 시행일 결합
       |
       v
FastAPI POST /ask
       |
       v
JSON 응답
```

---

## 4. 환경 설정

### 4.1 가상환경 생성

Windows PowerShell 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4.2 라이브러리 설치

```powershell
python -m pip install -r requirements.txt
```

주요 라이브러리:

- openai
- requests
- numpy
- fastapi
- uvicorn
- python-dotenv

### 4.3 환경변수 설정

`.env.example`을 복사해 `.env` 파일을 생성합니다.

```powershell
Copy-Item .env.example .env
```

설정 예시:

```ini
UPSTAGE_API_KEY=본인의_API_KEY
LAW_OC=test
```

실제 API Key는 GitHub에 업로드하지 않습니다.

API Key는 Upstage Console에서 발급받습니다.

https://console.upstage.ai

---

## 5. 데이터 수집 및 전처리

### 5.1 서울시 조례 수집

실행 명령:

```powershell
python -X utf8 fetch_ordinances.py
```

총 6개 조례 수집 성공:

1. 서울특별시 주차장 설치 및 관리 조례
2. 서울특별시 동물보호 조례
3. 서울특별시 자전거이용 활성화에 관한 조례
4. 서울특별시 도시공원 조례
5. 서울특별시 청년 기본 조례
6. 서울특별시 금연환경 조성 및 간접흡연 피해방지조례

결과 저장:

`data/ordinances.json`

### 5.2 Document Parse

```powershell
python -X utf8 parse_annex.py
```

실제 실행 결과:

- 주차장 조례 별표 4개
- 자전거 조례 별표 1개
- 도시공원 조례 별표 5개

총 10개 별표의 파싱 결과 생성 성공.

결과 저장:

`data/annex/`

### 5.3 Upstage Studio 실습

Studio에서 Parse → Extract 워크플로우 구성.

서울시 공영주차장 주차요금표를 입력해 다음 정보를 추출했습니다.

- 1·2·3급지별 주차요금 18개
- 표 하단 주석 2개
- 비고 9개
- 급지 기준

**주차요금 정답표 비교 결과: 18/18 일치**

`notes`는 JSON 문자열 배열로 추출했습니다.

주석 전체의 문자 단위 원문 일치 여부는 별도로 검증하지 않았습니다.

---

## 6. Chunking과 Embedding

실행 명령:

```powershell
python -X utf8 build_index.py
```

결과:

```text
조각 528개 (paragraph 단위)
임베딩 저장 완료
```

생성 파일:

- `data/chunks_paragraph.json`
- `data/vectors_paragraph.npy`

### Chunking

조례 전체를 한 번에 처리하지 않고 항 단위로 분할합니다.

예시:

```text
제7조 제1항
제7조 제2항
제7조 제3항
```

이렇게 분리하면 구체적인 근거 조항을 검색하고 인용하기 쉬워집니다.

### Embedding

문서의 의미를 숫자 벡터로 변환합니다.

사용 모델:

- 문서: `solar-embedding-2-passage`
- 질문: `solar-embedding-2-query`

---

## 7. Hybrid Search

본 프로젝트는 의미 기반 검색과 키워드 검색을 결합합니다.

```text
최종 검색 점수
= 0.7 × Embedding 유사도
+ 0.3 × BM25 정규화 점수
```

Embedding은 의미가 유사한 문서를 찾고, BM25는 질문과 법령의 검색어 일치도를 반영합니다.

검색된 상위 6개 근거를 Solar에 전달합니다.

```python
TOP_K = 6
```

---

## 8. RAG 성능 개선

### 8.1 초기 기준선

실행:

```powershell
python -X utf8 check.py --retrieval
python -X utf8 check.py
```

초기 결과:

| 평가 항목 | 점수 |
|---|---:|
| 검색 근거 정확도 | 0.81 |
| RAG 근거 인용 정확도 | 0.81 |
| 함정 문항 정답률 | 100% |

주요 실패 문항:

- S3: 청년의 나이 정의
- M1: 주차요금 중복 감면
- M2: 금주구역 음주 관련 규정

### 8.2 Query Expansion

사용자 질문과 조례 원문의 용어 차이를 줄이기 위해 검색 질문을 확장했습니다.

적용 예시:

| 사용자 표현 | 추가 검색어 |
|---|---|
| 말하는, 뜻, 의미 | 정의 |
| 할인 | 감면 |
| 둘 다, 중복 | 둘 이상의 중복 적용 |
| 술, 마시다 | 음주 |
| 처벌, 벌금 | 제재 과태료 |

기존 질문은 유지하면서 검색할 때만 관련 법령 용어를 추가합니다.

수정 파일:

`rag.py`

검색 단계 개선 결과:

**Top-6 정답 근거 검색률 81% → 100%**

### 8.3 Evidence ID 선택 규칙 개선

검색 정확도를 높인 뒤에도 M3 문항에서 일부 근거가 누락됐습니다.

문제:

자전거주차장 요금을 설명할 때 관련 조례 별표를 인용하지 않는 경우 발생.

개선:

- 답변에 사용한 숫자나 조건의 근거를 반드시 인용
- 답변에 직접 사용하지 않은 근거는 제외
- LLM은 실제 조항명을 작성하지 않고 근거 번호만 선택

수정 위치:

`rag.py`의 `SYSTEM` 프롬프트

### 8.4 최종 성능 비교

| 단계 | 근거 인용 정확도 |
|---|---:|
| 초기 기준선 | 0.81 |
| Query Expansion 적용 | 0.94 |
| Evidence ID 규칙 개선 | 1.00 |

함정 문항 정답률: **100% 유지**

평가 기준:

- 일반 문항 9개
- 함정 문항 2개

주의: 정확도 1.00은 제공된 연습문항의 근거 인용 평가 결과이며, 새로운 모든 법률 질문에 대한 정확도를 의미하지 않습니다.

---

## 9. Solar Decide — Groundedness 검증

Solar가 생성한 답변이 실제 검색 근거에 기반하는지 확인합니다.

기존 Starter Kit의 지원되지 않는 Groundedness 호출을 Solar Decide 방식으로 수정했습니다.

수정 파일:

`upstage.py`

사용 모델:

`solar-decide`

호출 API:

`POST https://api.upstage.ai/v1/systemone`

주요 판단 결과:

| 결과 | 의미 |
|---|---|
| grounded | 근거가 답변을 뒷받침함 |
| notGrounded | 근거가 뒷받침하지 않는 핵심 주장 존재 |
| notSure | 판단이 불명확함 |

실제 API 호출 테스트에서 `grounded` 응답을 확인했습니다.

근거가 부족하면 확인 불가를 반환하도록 설계했으며, 근거가 충분한지 최종 판단하는 과정 역시 모델 기반 검증이라는 한계가 있습니다.

---

## 10. FastAPI 서버

### 10.1 서버 실행

```powershell
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 10.2 Health Check

주소:

`http://127.0.0.1:8000/health`

실제 검증 결과:

```json
{
  "ok": true,
  "chunk_unit": "paragraph",
  "verify": true
}
```

### 10.3 질문 API

엔드포인트:

`POST /ask`

요청 예시:

```json
{
  "question": "서울시 공영주차장 1급지 노상주차장 요금은 5분에 얼마인가요?"
}
```

실제 응답:

```json
{
  "answer": "서울시 공영주차장 1급지 노상주차장의 1회 주차시 5분당 요금은 500원입니다.",
  "citation": [
    "서울특별시 주차장 설치 및 관리 조례 별표 1"
  ],
  "source_url": "https://www.law.go.kr/ordinInfoP.do?ordinSeq=2171833",
  "effective_date": "2026-10-01"
}
```

근거가 부족한 질문은 다음 구조로 처리합니다.

```json
{
  "answer": "확인 불가",
  "citation": [],
  "source_url": "",
  "effective_date": ""
}
```

---

## 11. 최종 API 셀프 채점

실행:

```powershell
python -X utf8 check.py --url http://127.0.0.1:8000/ask
```

실제 결과:

| 검증 항목 | 결과 |
|---|---|
| 일반 문항 근거 정확도 | 1.00 |
| 함정 문항 정답률 | 100% |
| JSON 형식 | 11/11 정상 |
| 최장 응답 시간 | 3.4초 |
| API 테스트 오류 | 0건 |

최종 평가 결과:

`results/check_1022_1716_paragraph_v1.json`

최종 평가 문항은 모두 정상적으로 처리되었습니다.

---

## 12. 주요 파일 구성

```text
starter-kit/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── config.py
├── fetch_ordinances.py
├── parse_annex.py
├── build_index.py
├── rag.py
├── upstage.py
├── app.py
├── check.py
├── demo.py
├── sample_questions.json
└── data/
    ├── raw/
    ├── annex/
    ├── ordinances.json
    ├── chunks_paragraph.json
    └── vectors_paragraph.npy
```

일부 데이터 파일과 폴더는 스크립트 실행 후 생성됩니다.

실행 결과 파일인 `results/`와 API Key가 들어 있는 `.env` 등은 `.gitignore` 정책에 따라 Git 추적에서 제외합니다.

---

## 13. 학습 내용 정리

### RAG에서 이해한 핵심 원리

**1. Document Parse와 Extract는 다르다.**

Parse는 문서의 텍스트와 표 구조를 읽고, Extract는 필요한 정보를 지정된 형식으로 추출합니다.

**2. Chunking과 Embedding은 다르다.**

Chunking은 문서를 작은 단위로 나누고, Embedding은 나눈 내용을 벡터로 표현합니다.

**3. 검색이 정확해야 답변도 정확해질 가능성이 높다.**

정답 근거가 검색 결과에 없다면 LLM이 올바른 근거를 인용하기 어렵습니다.

**4. 검색 성공과 근거 선택 성공은 다르다.**

정답 조항을 검색했더라도 LLM이 이를 `evidence_ids`에서 누락할 수 있습니다.

**5. RAG의 성능은 LLM만으로 결정되지 않는다.**

문서 파싱, Chunking, 검색, 프롬프트, 근거 검증 모두 답변 품질에 영향을 줍니다.

### 이번 실습의 핵심 성과

검색 알고리즘과 프롬프트를 단계적으로 개선하면서 제공된 평가 문항 기준 근거 정확도를 0.81에서 1.00까지 향상시켰습니다.

또한 Upstage Studio의 문서 처리부터 Python RAG 시스템, FastAPI 서버까지 전체 흐름을 실제로 실행하고 검증했습니다.

---

## 14. 한계와 향후 개선 방향

현재 시스템은 학습용 기준선입니다.

향후 개선 방향:

1. 새로운 법령 질문으로 일반화 성능 확인
2. 별표를 행 단위로 Chunking
3. 인용하지 않아야 할 근거에 대한 평가 강화
4. 답변 내용 자체의 사실 정확도 평가
5. 법령 개정 시 데이터 재수집 및 인덱스 갱신
6. 일반 사용자용 웹 UI 구현

## 15. 보안 및 주의사항

- 실제 API Key는 `.env`에 저장하고 GitHub에 업로드하지 않습니다.
- `.venv`, 캐시, 임시파일 등을 Git에서 제외합니다.
- 실습 평가 정확도는 제한된 연습문항 기준입니다.
- 실제 법률 판단에는 최신 조례 원문을 별도로 확인해야 합니다.
- 이 프로젝트는 학습 및 기술 검증용이며 법률 자문을 대체하지 않습니다.

---

## 참고 자료

- [Upstage Console](https://console.upstage.ai)
- [Upstage Studio](https://studio.upstage.ai)
- [국가법령정보센터](https://www.law.go.kr)
- [법제처 OPEN API](https://open.law.go.kr)

**실습 완료일:** 2026-10-22

**최종 결과:** 서울시 조례 RAG API 구현 및 제공된 연습문항 전체 검증 완료
