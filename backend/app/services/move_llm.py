from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.coach_llm import _ensure_google_credentials_file

logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "move_system_prompt.md"
_HUMAN_PROMPT_PATH = _PROMPTS_DIR / "move_human_prompt.md"
_MODEL_CACHE_KEY: tuple[str, str, str, int, str] | None = None
_MODEL_CACHE: Any | None = None
_PROMPT_CACHE: Any | None = None
_MODEL_CACHE_LOCK = threading.Lock()


def llm_enabled() -> bool:
    return bool(settings.move_explanation_use_llm and settings.google_application_credentials_b64)


def build_llm_move_explanation(payload: dict[str, Any]) -> str | None:
    if not llm_enabled():
        logger.info("Move explanation LLM disabled or missing credentials")
        return None

    raw = ""
    try:
        _ensure_google_credentials_file()
        model, prompt = _get_llm_runtime()
        messages = prompt.format_messages(payload_json=json.dumps(payload, ensure_ascii=False))
        response = model.invoke(messages)
        raw = _extract_response_text(getattr(response, "content", response))
        parsed = _parse_json_object(raw)
    except Exception:
        logger.exception("Move explanation LLM call failed")
        return None

    if not isinstance(parsed, dict):
        logger.warning("Move explanation LLM returned non-JSON output")
        return None

    explanation = _clean_text(parsed.get("explanation"), max_len=600)
    if not explanation:
        logger.warning("Move explanation LLM response missing explanation field")
        return None

    return explanation


def _get_llm_runtime() -> tuple[Any, Any]:
    global _MODEL_CACHE_KEY, _MODEL_CACHE, _PROMPT_CACHE

    cache_key = (
        settings.move_explanation_model,
        settings.google_cloud_project,
        settings.google_cloud_location,
        settings.move_explanation_max_output_tokens,
        settings.move_explanation_prompt_version,
    )
    if _MODEL_CACHE_KEY == cache_key and _MODEL_CACHE is not None and _PROMPT_CACHE is not None:
        return _MODEL_CACHE, _PROMPT_CACHE

    with _MODEL_CACHE_LOCK:
        if _MODEL_CACHE_KEY == cache_key and _MODEL_CACHE is not None and _PROMPT_CACHE is not None:
            return _MODEL_CACHE, _PROMPT_CACHE

        # Lazy imports so the app can run without LLM dependencies configured.
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_vertexai import ChatVertexAI

        system_prompt, human_prompt = _load_prompt_templates()
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
        model = ChatVertexAI(
            model=settings.move_explanation_model,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            temperature=0,
            max_output_tokens=settings.move_explanation_max_output_tokens,
        )

        _MODEL_CACHE_KEY = cache_key
        _MODEL_CACHE = model
        _PROMPT_CACHE = prompt
        return _MODEL_CACHE, _PROMPT_CACHE


def _load_prompt_templates() -> tuple[str, str]:
    system_prompt = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    human_prompt = _HUMAN_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return system_prompt, human_prompt


def _parse_json_object(text: str) -> dict[str, Any] | list[Any] | None:
    cleaned = text.strip()

    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL):
        candidate = match.group(1).strip()
        parsed = _parse_json_candidate(candidate)
        if parsed is not None:
            return parsed

    parsed_full = _parse_json_candidate(cleaned)
    if parsed_full is not None:
        return parsed_full

    first_obj = cleaned.find("{")
    last_obj = cleaned.rfind("}")
    if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
        parsed_obj = _parse_json_candidate(cleaned[first_obj : last_obj + 1].strip())
        if parsed_obj is not None:
            return parsed_obj

    first_arr = cleaned.find("[")
    last_arr = cleaned.rfind("]")
    if first_arr == -1 or last_arr == -1 or last_arr <= first_arr:
        return None

    return _parse_json_candidate(cleaned[first_arr : last_arr + 1].strip())


def _parse_json_candidate(text: str) -> dict[str, Any] | list[Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _extract_response_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _clean_text(value: object, max_len: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
