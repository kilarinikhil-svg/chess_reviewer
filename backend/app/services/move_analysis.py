from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import chess

from app.config import settings
from app.models.schemas import AnalysisLimits, MoveAnalysisResponse, ScoreModel
from app.services.classification import build_suggestion, classify_move, score_to_cp_equivalent
from app.services.engine import engine_service
from app.services.move_llm import build_llm_move_report, llm_enabled
from app.services.session_store import GameSession

logger = logging.getLogger(__name__)
_CLASS_DELTA_DEFAULTS = {
    "best": 0,
    "good": 40,
    "inaccuracy": 120,
    "mistake": 250,
    "blunder": 500,
}


@dataclass
class _MoveContext:
    ply: int
    board_before: chess.Board
    board_after: chess.Board
    played_san: str
    played_uci: str


class MoveAnalysisService:
    async def analyze_move(
        self,
        session: GameSession,
        ply: int,
        mode: str,
        limits: AnalysisLimits,
        force: bool = False,
    ) -> MoveAnalysisResponse:
        results = await self.analyze_moves(session, [ply], mode, limits, force=force)
        return results[0]

    async def analyze_moves(
        self,
        session: GameSession,
        plies: list[int],
        mode: str,
        limits: AnalysisLimits,
        force: bool = False,
    ) -> list[MoveAnalysisResponse]:
        if not plies:
            return []

        unique_plies: list[int] = []
        seen: set[int] = set()
        for ply in plies:
            if ply in seen:
                continue
            seen.add(ply)
            unique_plies.append(ply)

        contexts = _build_contexts(session, unique_plies)
        results_by_ply: dict[int, MoveAnalysisResponse] = {}
        pending_contexts: list[_MoveContext] = []

        for context in contexts:
            cache_key = self._cache_key(session.game_id, context.ply, mode, limits)
            if force:
                pending_contexts.append(context)
                continue
            cached = self._get_cached(session, cache_key)
            if cached:
                results_by_ply[context.ply] = cached
            else:
                pending_contexts.append(context)

        if pending_contexts:
            if settings.move_use_llm and llm_enabled():
                llm_results, fallback_targets = await self._analyze_with_llm_batches(session, pending_contexts, mode, limits)
                for ply, result in llm_results.items():
                    results_by_ply[ply] = result
                    cache_key = self._cache_key(session.game_id, ply, mode, limits)
                    self._put_cached(session, cache_key, result)
            else:
                fallback_targets = [(context, None) for context in pending_contexts]

            if fallback_targets:
                fallback_results = await asyncio.gather(
                    *[
                        self._analyze_with_stockfish_context(context, limits, fallback_reason)
                        for context, fallback_reason in fallback_targets
                    ]
                )
                for result in fallback_results:
                    results_by_ply[result.ply] = result
                    cache_key = self._cache_key(session.game_id, result.ply, mode, limits)
                    self._put_cached(session, cache_key, result)

        return [results_by_ply[ply] for ply in plies if ply in results_by_ply]

    async def _analyze_with_llm_batches(
        self,
        session: GameSession,
        contexts: list[_MoveContext],
        mode: str,
        limits: AnalysisLimits,
    ) -> tuple[dict[int, MoveAnalysisResponse], list[tuple[_MoveContext, str]]]:
        chunk_size = max(1, settings.move_batch_chunk_size)
        max_concurrency = max(1, settings.move_llm_max_concurrency)
        timeout_seconds = max(1, settings.move_llm_timeout_seconds)

        results: dict[int, MoveAnalysisResponse] = {}
        fallback_targets: list[tuple[_MoveContext, str]] = []
        chunks = [contexts[idx : idx + chunk_size] for idx in range(0, len(contexts), chunk_size)]
        semaphore = asyncio.Semaphore(max_concurrency)

        task_results = await asyncio.gather(
            *[
                self._analyze_llm_chunk(
                    session=session,
                    chunk=chunk,
                    mode=mode,
                    limits=limits,
                    semaphore=semaphore,
                    timeout_seconds=timeout_seconds,
                )
                for chunk in chunks
            ],
            return_exceptions=True,
        )

        for chunk, output in zip(chunks, task_results):
            if isinstance(output, Exception):
                logger.error(
                    "Move LLM chunk task crashed: model=%s chunk_size=%s",
                    settings.move_llm_model,
                    len(chunk),
                    exc_info=(type(output), output, output.__traceback__),
                )
                fallback_targets.extend((context, "llm_batch_failed") for context in chunk)
                continue

            chunk_results, chunk_fallbacks = output
            results.update(chunk_results)
            fallback_targets.extend(chunk_fallbacks)

        return results, fallback_targets

    async def _analyze_llm_chunk(
        self,
        session: GameSession,
        chunk: list[_MoveContext],
        mode: str,
        limits: AnalysisLimits,
        semaphore: asyncio.Semaphore,
        timeout_seconds: int,
    ) -> tuple[dict[int, MoveAnalysisResponse], list[tuple[_MoveContext, str]]]:
        started = time.perf_counter()
        timeout_hit = False
        chunk_results: dict[int, MoveAnalysisResponse] = {}
        chunk_fallbacks: list[tuple[_MoveContext, str]] = []

        payload = {
            "game_id": session.game_id,
            "mode": mode,
            "limits": {
                "movetime_ms": limits.movetime_ms,
                "depth": limits.depth,
                "nodes": limits.nodes,
                "multipv": limits.multipv,
            },
            "moves": [
                {
                    "ply": context.ply,
                    "fen_before": context.board_before.fen(),
                    "played_uci": context.played_uci,
                    "played_san": context.played_san,
                    "legal_uci": [move.uci() for move in context.board_before.legal_moves],
                }
                for context in chunk
            ],
        }

        llm_report: dict | None = None
        try:
            async with semaphore:
                llm_report = await asyncio.wait_for(
                    asyncio.to_thread(build_llm_move_report, payload),
                    timeout=timeout_seconds,
                )
        except asyncio.TimeoutError:
            timeout_hit = True
            chunk_fallbacks.extend((context, "llm_timeout") for context in chunk)
        except Exception:
            logger.exception("Move LLM chunk call failed")
            chunk_fallbacks.extend((context, "llm_batch_failed") for context in chunk)

        if llm_report is None and not chunk_fallbacks:
            chunk_fallbacks.extend((context, "llm_batch_failed") for context in chunk)

        if llm_report:
            parsed_items = _index_llm_items(llm_report)
            valid_llm_results: list[tuple[_MoveContext, MoveAnalysisResponse]] = []
            for context in chunk:
                raw_item = parsed_items.get(context.ply)
                if raw_item is None:
                    chunk_fallbacks.append((context, "missing_llm_item"))
                    continue

                llm_result, reason = _build_llm_response(context, raw_item)
                if llm_result is None:
                    chunk_fallbacks.append((context, reason or "invalid_llm_item"))
                    continue

                valid_llm_results.append((context, llm_result))

            if valid_llm_results:
                eval_results = await asyncio.gather(
                    *[
                        engine_service.analyze(context.board_after, limits)
                        for context, _ in valid_llm_results
                    ],
                    return_exceptions=True,
                )
                for (context, llm_result), eval_data in zip(valid_llm_results, eval_results):
                    if isinstance(eval_data, Exception):
                        chunk_fallbacks.append((context, "llm_eval_failed"))
                        continue
                    score_after, _, _, inc_after = eval_data
                    llm_result.score_after = score_after
                    llm_result.analysis_incomplete = bool(llm_result.analysis_incomplete or inc_after)
                    chunk_results[context.ply] = llm_result

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reasons = sorted({reason for _, reason in chunk_fallbacks})
        fallback_reason = reasons[0] if len(reasons) == 1 else ("mixed" if reasons else "")
        logger.info(
            "Move LLM chunk complete: model=%s chunk_size=%s latency_ms=%s timeout_hit=%s fallback_reason=%s result_count=%s",
            settings.move_llm_model,
            len(chunk),
            elapsed_ms,
            timeout_hit,
            fallback_reason,
            len(chunk_results),
        )
        return chunk_results, chunk_fallbacks

    async def _analyze_with_stockfish_context(
        self,
        context: _MoveContext,
        limits: AnalysisLimits,
        fallback_reason: str | None,
    ) -> MoveAnalysisResponse:
        (score_before, best_uci, pv, inc_before), (score_after, _, _, inc_after) = await asyncio.gather(
            engine_service.analyze(context.board_before, limits),
            engine_service.analyze(context.board_after, limits),
        )

        best_san = best_uci
        if best_uci:
            candidate = chess.Move.from_uci(best_uci)
            if candidate in context.board_before.legal_moves:
                best_san = context.board_before.san(candidate)

        before_cp = score_to_cp_equivalent(score_before)
        after_cp = score_to_cp_equivalent(score_after)
        mover_after_cp = -after_cp
        delta_cp = before_cp - mover_after_cp
        classification = classify_move(delta_cp, score_before, score_after)

        return MoveAnalysisResponse(
            ply=context.ply,
            played=context.played_san,
            best=best_san or "(none)",
            score_before=score_before,
            score_after=score_after,
            delta_cp=delta_cp,
            classification=classification,
            pv=pv,
            suggestion=build_suggestion(best_san or "(none)", classification, delta_cp),
            analysis_source="stockfish",
            fallback_reason=fallback_reason,
            analysis_incomplete=inc_before or inc_after,
        )

    def _cache_key(self, game_id: str, ply: int, mode: str, limits: AnalysisLimits) -> str:
        limits_key = f"{limits.movetime_ms}:{limits.depth}:{limits.nodes}:{limits.multipv}"
        llm_key = f"{settings.move_use_llm}:{settings.move_llm_model}:{settings.move_llm_prompt_version}"
        return f"{game_id}:{ply}:{mode}:{limits_key}:{llm_key}"

    def _get_cached(self, session: GameSession, cache_key: str) -> MoveAnalysisResponse | None:
        with session.cache_lock:
            return session.analysis_cache.get(cache_key)

    def _put_cached(self, session: GameSession, cache_key: str, result: MoveAnalysisResponse) -> None:
        with session.cache_lock:
            session.analysis_cache[cache_key] = result


move_analysis_service = MoveAnalysisService()


def _build_contexts(session: GameSession, plies: list[int]) -> list[_MoveContext]:
    targets = set(plies)
    contexts: dict[int, _MoveContext] = {}

    board = chess.Board(session.initial_fen)
    for idx, move_model in enumerate(session.moves, start=1):
        move = chess.Move.from_uci(move_model.uci)
        if idx in targets:
            board_before = board.copy(stack=False)
            played_san = board_before.san(move)
            board_after = board_before.copy(stack=False)
            board_after.push(move)
            contexts[idx] = _MoveContext(
                ply=idx,
                board_before=board_before,
                board_after=board_after,
                played_san=played_san,
                played_uci=move_model.uci,
            )
        board.push(move)

    missing = [ply for ply in plies if ply not in contexts]
    if missing:
        raise ValueError(f"ply out of range: {missing[0]}")

    return [contexts[ply] for ply in plies]


def _index_llm_items(llm_report: dict) -> dict[int, dict]:
    raw_items = llm_report.get("moves") if isinstance(llm_report, dict) else None
    if not isinstance(raw_items, list):
        return {}

    indexed: dict[int, dict] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        ply = _safe_int(raw_item.get("ply"))
        if ply is None:
            continue
        indexed[ply] = raw_item
    return indexed


def _build_llm_response(context: _MoveContext, raw_item: dict) -> tuple[MoveAnalysisResponse | None, str | None]:
    classification_raw = str(raw_item.get("classification", "")).strip().lower()
    if classification_raw not in _CLASS_DELTA_DEFAULTS:
        return None, "invalid_llm_classification"

    best_uci = str(raw_item.get("best_uci", "")).strip()
    try:
        best_move = chess.Move.from_uci(best_uci)
    except ValueError:
        return None, "invalid_llm_best_move"

    if best_move not in context.board_before.legal_moves:
        return None, "illegal_llm_best_move"

    best_san = context.board_before.san(best_move)
    delta_cp = _safe_int(raw_item.get("delta_cp"))
    if delta_cp is None:
        delta_cp = _CLASS_DELTA_DEFAULTS[classification_raw]
    delta_cp = max(0, min(3000, delta_cp))

    suggestion = _clean_text(raw_item.get("suggestion"), max_len=280)
    if not suggestion:
        suggestion = build_suggestion(best_san, classification_raw, delta_cp)

    explanation = _clean_text(raw_item.get("explanation"), max_len=320)
    confidence = _safe_float(raw_item.get("confidence"))
    if confidence is not None:
        confidence = max(0.0, min(1.0, confidence))

    pv: list[str] = []
    raw_pv = raw_item.get("pv")
    if isinstance(raw_pv, list):
        for item in raw_pv[:8]:
            text = str(item).strip()
            if text:
                pv.append(text)

    themes: list[str] = []
    raw_themes = raw_item.get("themes")
    if isinstance(raw_themes, list):
        for item in raw_themes:
            text = _clean_text(item, max_len=48)
            if text and text not in themes:
                themes.append(text)
            if len(themes) >= 4:
                break

    return (
        MoveAnalysisResponse(
            ply=context.ply,
            played=context.played_san,
            best=best_san,
            score_before=ScoreModel(type="unknown", value=0),
            score_after=ScoreModel(type="unknown", value=0),
            delta_cp=delta_cp,
            classification=classification_raw,
            pv=pv,
            suggestion=suggestion,
            analysis_source="llm",
            explanation=explanation or None,
            confidence=confidence,
            themes=themes,
            fallback_reason=None,
            analysis_incomplete=False,
        ),
        None,
    )


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: object, max_len: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
