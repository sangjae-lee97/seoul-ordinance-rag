"""스타터 킷 공통 설정.

여기 값만 바꿔도 시연의 '전/후' 장면을 재현할 수 있습니다.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# .env 파일이 있으면 읽습니다 (python-dotenv가 없으면 환경변수만 사용)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "")
UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"

# 법제처 OPEN API 인증값(OC). 'test'로도 응답하지만, 대회용으로는 open.law.go.kr에서 개인 OC를 신청하세요.
LAW_OC = os.environ.get("LAW_OC", "test")

# ---- 대상: 서울특별시 조례 6종 (자치구 조례는 대상이 아닙니다) ----
TARGET_ORDINANCES = [
    "서울특별시 주차장 설치 및 관리 조례",
    "서울특별시 동물보호 조례",
    "서울특별시 자전거이용 활성화에 관한 조례",
    "서울특별시 도시공원 조례",
    "서울특별시 청년 기본 조례",  # 확인 필요: 대회 운영진이 말한 '청년' 조례가 이것인지
    "서울특별시 금연환경 조성 및 간접흡연 피해방지조례",
]
TARGET_ORG = "서울특별시"      # 지자체기관명이 정확히 이것인 것만 받습니다
BASE_DATE = "20261001"          # 기준 시점: 2026년 10월 1일 시행 조례

# ---- 모델 ----
CHAT_MODEL = "solar-pro4"
EMBED_PASSAGE = "solar-embedding-2-passage"   # 조문 조각용
EMBED_QUERY = "solar-embedding-2-query"       # 질문용 (질문과 조각은 서로 다른 모델)

# ---- 시연 스위치 ----
# 2-4 시연: "article"(조 단위) → "paragraph"(항 단위)로 바꾸면 인용이 항까지 맞기 시작합니다
CHUNK_UNIT = os.environ.get("CHUNK_UNIT", "paragraph")
# 2-2 시연: 별표를 Document Parse 결과로 읽을지(True), 법제처 원문 괘선 텍스트로 읽을지(False)
USE_PARSED_ANNEX = os.environ.get("USE_PARSED_ANNEX", "1") == "1"
# 2-5 시연: 근거 검증 장치를 켤지
USE_VERIFY = os.environ.get("USE_VERIFY", "1") == "1"

TOP_K = 6
# 검색 점수가 이보다 낮으면 '확인 불가' 후보로 봅니다. TODO: 공개 예시로 직접 맞춰 보세요.
MIN_SCORE = 0.25

# 대회 제한은 문항당 90초. 여유를 두고 이 시간을 넘기면 '확인 불가'로 돌려줍니다.
ANSWER_TIMEOUT_SEC = 75
