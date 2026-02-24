from __future__ import annotations

import base64
import json
import os
import tempfile
from typing import Any

from app.config import settings

_CREDENTIALS_PATH: str | None = None


def llm_enabled() -> bool:
    return bool(settings.coach_use_llm and settings.google_application_credentials_b64)


def build_llm_coach_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not llm_enabled():
        return None

    _ensure_google_credentials_file()

    # Lazy imports so the app can still run without LLM dependencies configured.
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_vertexai import ChatVertexAI

    model = ChatVertexAI(
        model=settings.coach_llm_model,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        temperature=0,
        max_output_tokens=1200,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a chess coach. Return ONLY valid JSON with keys: "
                "top_mistakes, action_plan, next_game_focus."
                "top_mistakes: list of max 3 items with keys label, description, fix, evidence."
                "action_plan: list of max 3 items with keys focus and drills (list of strings)."
                "next_game_focus: list of exactly 3 short checklist strings.",
            ),
            (
                "human",
                "Player summary:\n{payload_json}\n\n"
                "Use the provided aggregate evidence only. Keep advice concrete and training-oriented.",
            ),
        ]
    )

    chain = prompt | model | StrOutputParser()
    raw = chain.invoke({"payload_json": json.dumps(payload, ensure_ascii=False)})

    parsed = _parse_json_object(raw)
    if not parsed:
        return None
    return parsed


def _ensure_google_credentials_file() -> None:
    global _CREDENTIALS_PATH
    if _CREDENTIALS_PATH:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", _CREDENTIALS_PATH)
        return

    encoded = settings.google_application_credentials_b64.strip()
    creds_json = base64.b64decode(encoded).decode("utf-8")

    with tempfile.NamedTemporaryFile(mode="w", suffix="-gcp-creds.json", delete=False) as f:
        f.write(creds_json)
        _CREDENTIALS_PATH = f.name

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _CREDENTIALS_PATH


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
