"""1단계: 법제처 OPEN API로 서울특별시 조례 6종을 받아 조·항 단위로 정리합니다.

실행:  python -X utf8 fetch_ordinances.py
결과:  data/raw/<일련번호>.xml, data/ordinances.json
"""
import json
import re
import xml.etree.ElementTree as ET

import requests

import config

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
PAGE_URL = "https://www.law.go.kr/ordinInfoP.do?ordinSeq={mst}"   # 시행 버전이 고정되는 원문 링크

CIRCLED = {chr(0x2460 + i): i + 1 for i in range(20)}   # ①=1 ... ⑳=20
ARTICLE_HEAD = re.compile(r"^\s*(제\d+조(?:의\d+)?)\s*(?:\(([^)]*)\))?\s*")


def find_ordinance(name):
    """이름이 정확히 같고, 지자체기관명이 '서울특별시'인 조례만 고릅니다.

    검색 결과에는 'OO구' 조례가 섞여 나옵니다. 여기서 거르지 않으면 자치구 조례를 인용해 오답이 됩니다.
    """
    r = requests.get(SEARCH_URL, params=dict(OC=config.LAW_OC, target="ordin", type="XML",
                                             query=name, display=100), timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    hits = []
    for law in root.findall("law"):
        if law.findtext("지자체기관명") == config.TARGET_ORG and law.findtext("자치법규명") == name:
            hits.append({"mst": law.findtext("자치법규일련번호"),
                         "effective": law.findtext("시행일자")})
    if not hits:
        raise SystemExit(f"찾지 못했습니다: {name}")
    hits.sort(key=lambda h: h["effective"], reverse=True)
    best = hits[0]
    if best["effective"] > config.BASE_DATE:
        print(f"  ⚠ {name}: 최신본 시행일 {best['effective']}가 기준일 {config.BASE_DATE}보다 늦습니다. 연혁 확인 필요")
    return best


def split_paragraphs(body):
    """조 본문을 항(①②…) 단위로 나눕니다. 호(1. 2.)와 목(가. 나.)은 소속 항에 붙입니다."""
    paras, cur = [], None
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s[0] in CIRCLED:
            cur = {"no": CIRCLED[s[0]], "text": s}
            paras.append(cur)
        elif cur is None:
            cur = {"no": None, "text": s}       # 항이 없는 조
            paras.append(cur)
        else:
            cur["text"] += "\n" + s
    return paras


def parse_xml(xml_bytes, name, mst):
    root = ET.fromstring(xml_bytes)
    info = root.find("자치법규기본정보")
    eff = info.findtext("시행일자")
    law = {
        "name": name,
        "mst": mst,
        "effective_date": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}",
        "source_url": PAGE_URL.format(mst=mst),
        "articles": [],
        "annexes": [],
    }
    for jo in root.find("조문").findall("조"):
        if jo.findtext("조문여부") != "Y":           # 장·절 제목은 건너뜁니다
            continue
        text = (jo.findtext("조내용") or "").strip()
        m = ARTICLE_HEAD.match(text)
        if not m or "삭제" in text[:30] and len(text) < 40:
            continue
        label, title = m.group(1), m.group(2) or (jo.findtext("조제목") or "")
        rest = text[m.end():]
        law["articles"].append({
            "article": label,
            "title": title,
            "text": text,
            "paragraphs": split_paragraphs(rest),
        })
    for b in root.findall("별표단위"):
        kind = b.findtext("별표구분") or "별표"
        no = int(b.findtext("별표번호") or 0)
        sub = int(b.findtext("별표가지번호") or 0)
        # 별표가 하나뿐인 조례는 번호가 0으로 옵니다 → "별표"
        label = (f"{kind} {no}" if no else kind) + (f"의{sub}" if sub else "")
        law["annexes"].append({
            "label": label,
            "title": (b.findtext("별표제목") or "").strip(),
            "text": (b.findtext("별표내용") or "").strip(),   # 괘선(┌─┐)으로 그린 표: LLM이 읽기 어렵습니다
            "file_url": (b.findtext("별표첨부파일명") or "").strip(),
            "file_type": b.findtext("별표첨부파일구분"),
        })
    return law


def main():
    raw = config.DATA / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    laws = []
    for name in config.TARGET_ORDINANCES:
        hit = find_ordinance(name)
        r = requests.get(SERVICE_URL, params=dict(OC=config.LAW_OC, target="ordin",
                                                  MST=hit["mst"], type="XML"), timeout=60)
        r.raise_for_status()
        (raw / f"{hit['mst']}.xml").write_bytes(r.content)
        law = parse_xml(r.content, name, hit["mst"])
        n_para = sum(len(a["paragraphs"]) for a in law["articles"])
        print(f"✓ {name}  시행 {law['effective_date']}  조 {len(law['articles'])} · 항 {n_para} · 별표 {len(law['annexes'])}")
        laws.append(law)
    out = config.DATA / "ordinances.json"
    out.write_text(json.dumps(laws, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", out)


if __name__ == "__main__":
    main()
