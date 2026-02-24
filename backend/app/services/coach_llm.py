from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from app.config import settings

_CREDENTIALS_PATH: str | None = None
logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "coach_system_prompt.md"
_HUMAN_PROMPT_PATH = _PROMPTS_DIR / "coach_human_prompt.md"


def llm_enabled() -> bool:
    return bool(settings.coach_use_llm and settings.google_application_credentials_b64)


def build_llm_coach_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not llm_enabled():
        logger.warning("Coach LLM disabled or missing credentials")
        return None

    raw = ""
    try:
        _ensure_google_credentials_file()

        # Lazy imports so the app can still run without LLM dependencies configured.
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_vertexai import ChatVertexAI

        model = ChatVertexAI(
            model=settings.coach_llm_model,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            temperature=0,
            max_output_tokens=settings.coach_llm_max_output_tokens,
        )

        system_prompt, human_prompt = _load_prompt_templates()
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )

        messages = prompt.format_messages(payload_json=json.dumps(payload, ensure_ascii=False))
        response = model.invoke(messages)
        raw = _extract_response_text(getattr(response, "content", response))
        response_metadata = getattr(response, "response_metadata", {}) or {}
        usage_metadata = getattr(response, "usage_metadata", {}) or {}
        finish_reason = response_metadata.get("finish_reason") or response_metadata.get("finish_reason_name")

        logger.warning(
            "Coach LLM response metadata: finish_reason=%s usage=%s",
            finish_reason,
            usage_metadata,
        )
        parsed = _parse_json_object(raw)
    except Exception:
        logger.exception("Coach LLM call failed")
        return None

    if not parsed:
        logger.warning(
            "Coach LLM returned non-JSON output (max_output_tokens=%s). "
            "If finish_reason indicates truncation, increase COACH_LLM_MAX_OUTPUT_TOKENS.",
            settings.coach_llm_max_output_tokens,
        )
        return None
    if not _has_required_coach_keys(parsed):
        logger.warning("Coach LLM output missing required keys or invalid top-level shapes")
        return None
    logger.info("Coach LLM response parsed successfully")
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

    # Preferred path: parse JSON from fenced blocks first.
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL):
        candidate = match.group(1).strip()
        parsed = _parse_json_candidate(candidate)
        if parsed is not None:
            return parsed

    # Fallback path: parse full text or first JSON-like object span.
    parsed_full = _parse_json_candidate(cleaned)
    if parsed_full is not None:
        return parsed_full

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    return _parse_json_candidate(cleaned[start : end + 1].strip())


def _load_prompt_templates() -> tuple[str, str]:
    system_prompt = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    human_prompt = _HUMAN_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return system_prompt, human_prompt


def _has_required_coach_keys(report: dict[str, Any]) -> bool:
    if not isinstance(report, dict):
        return False
    if not isinstance(report.get("top_mistakes"), list):
        return False
    if not isinstance(report.get("action_plan"), list):
        return False
    if not isinstance(report.get("next_game_focus"), list):
        return False
    return True


def _parse_json_candidate(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
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
