
"""Upstage API 호출: Chat · Embedding · Document Parse · Solar Decide."""

import json
import time

import requests

import config

_client = None


def client():
    global _client
    if _client is None:
        if not config.UPSTAGE_API_KEY:
            raise RuntimeError("UPSTAGE_API_KEY가 없습니다.")
        from openai import OpenAI
        _client = OpenAI(
            api_key=config.UPSTAGE_API_KEY,
            base_url=config.UPSTAGE_BASE_URL,
        )
    return _client


def _retry(fn, tries=4):
    """429 요청 제한에 대해 재시도합니다."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if "429" in str(e) and i < tries - 1:
                time.sleep(2 ** i)
                continue
            raise


def chat(messages, response_format=None,
         temperature=0.0, reasoning_effort=None):
    kw = dict(
        model=config.CHAT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    if response_format:
        kw["response_format"] = response_format
    if reasoning_effort:
        kw["reasoning_effort"] = reasoning_effort

    resp = _retry(
        lambda: client().chat.completions.create(**kw)
    )
    return resp.choices[0].message.content


def embed(texts, model):
    out = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        resp = _retry(
            lambda: client().embeddings.create(
                model=model, input=batch
            )
        )
        out.extend(d.embedding for d in resp.data)
    return out


def document_parse(path):
    """문서를 표 구조가 살아 있는 Markdown/HTML로 변환."""
    url = f"{config.UPSTAGE_BASE_URL}/document-digitization"
    headers = {
        "Authorization": f"Bearer {config.UPSTAGE_API_KEY}"
    }

    with open(path, "rb") as f:
        resp = requests.post(
            url,
            headers=headers,
            timeout=300,
            files={"document": f},
            data={
                "model": "document-parse",
                "output_formats": json.dumps(
                    ["html", "markdown"]
                ),
            },
        )

    resp.raise_for_status()
    content = resp.json().get("content", {})

    return (
        content.get("markdown")
        or content.get("html")
        or content.get("text")
        or ""
    )


def groundedness(context, answer):
    """Solar Decide로 답변의 근거 일치 여부를 판단."""
    if not config.UPSTAGE_API_KEY:
        raise RuntimeError("UPSTAGE_API_KEY가 없습니다.")

    url = f"{config.UPSTAGE_BASE_URL}/systemone"
    headers = {
        "Authorization": f"Bearer {config.UPSTAGE_API_KEY}"
    }

    payload = {
        "model": "solar-decide",
        "state": (
            f"[근거 문서]\n{context}\n\n"
            f"[검증할 답변]\n{answer}"
        ),
        "questions": {
            "groundedness": {
                "type": "choice",
                "instructions": (
                    "답변의 주요 사실과 수치가 근거 문서로 "
                    "충분히 뒷받침되는지 판단하세요. "
                    "외부 지식은 사용하지 마세요."
                ),
                "criteria": {
                    "grounded": (
                        "답변의 모든 핵심 주장을 "
                        "근거 문서가 뒷받침합니다."
                    ),
                    "notGrounded": (
                        "답변에 근거 문서가 뒷받침하지 "
                        "않는 핵심 주장이 있습니다."
                    ),
                    "notSure": (
                        "근거가 불명확하거나 판단이 어렵습니다."
                    ),
                },
            }
        },
    }

    def send_request():
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=75,
        )
        resp.raise_for_status()
        return resp

    resp = _retry(send_request)
    verdict = resp.json()["answers"]["groundedness"]["choice"]

    if verdict not in ("grounded", "notGrounded", "notSure"):
        raise ValueError(f"알 수 없는 검증 결과: {verdict}")

    return verdict
