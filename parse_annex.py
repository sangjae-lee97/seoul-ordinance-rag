"""2단계: 별표(요금표 등)를 Document Parse로 읽어 표 구조를 살립니다.

법제처 API가 주는 별표 본문은 괘선 문자(┌─┬─┐)로 그린 표입니다.
사람 눈에는 표지만, LLM에게는 기호가 섞인 긴 문자열이라 칸이 어긋나기 쉽습니다.
그래서 별표 원본 파일(hwp)을 받아 Document Parse로 다시 읽습니다.

실행:  python -X utf8 parse_annex.py
결과:  data/annex/<일련번호>_<별표라벨>.md
"""
import json

import requests

import config
import upstage


def annex_path(mst, label):
    return config.DATA / "annex" / f"{mst}_{label.replace(' ', '')}.md"


def main():
    laws = json.loads((config.DATA / "ordinances.json").read_text(encoding="utf-8"))
    files = config.DATA / "annex_files"
    files.mkdir(parents=True, exist_ok=True)
    (config.DATA / "annex").mkdir(parents=True, exist_ok=True)

    for law in laws:
        for ax in law["annexes"]:
            if not ax["label"].startswith("별표") or not ax["file_url"]:
                continue                      # 서식(별도)은 건너뜁니다
            out = annex_path(law["mst"], ax["label"])
            if out.exists():
                print("· 이미 있음:", out.name)
                continue
            src = files / f"{law['mst']}_{ax['label'].replace(' ', '')}.{ax['file_type'] or 'hwp'}"
            if not src.exists():
                r = requests.get(ax["file_url"], timeout=60)
                r.raise_for_status()
                src.write_bytes(r.content)
            try:
                md = upstage.document_parse(src)
            except requests.HTTPError as e:
                print(f"✗ {law['name']} {ax['label']}: {e}  → 파일을 PDF로 저장해 다시 시도해 보세요")
                continue
            out.write_text(f"# {law['name']} {ax['label']} {ax['title']}\n\n{md}", encoding="utf-8")
            print(f"✓ {law['name']} {ax['label']}  ({len(md)}자)")


if __name__ == "__main__":
    main()
