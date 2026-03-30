from __future__ import annotations

import asyncio
from dataclasses import dataclass

import chess

from app.config import settings
from app.models.schemas import AnalysisLimits, MoveExplanationResponse
from app.services.move_analysis import move_analysis_service
from app.services.move_llm import build_llm_move_explanation, llm_enabled
from app.services.session_store import GameSession


@dataclass
class _MoveContext:
    board_before: chess.Board
    played_san: str
    played_uci: str


class MoveExplanationService:
    async def explain_move(
        self,
        session: GameSession,
        ply: int,
        mode: str,
        limits: AnalysisLimits,
        force: bool = False,
    ) -> MoveExplanationResponse:
        cache_key = self._cache_key(session.game_id, ply, mode, limits)
        if not force:
            cached = self._get_cached(session, cache_key)
            if cached:
                return MoveExplanationResponse(ply=ply, explanation=cached)

        if not llm_enabled():
            raise RuntimeError("Move explanation LLM unavailable")

        analysis = await move_analysis_service.analyze_move(
            session=session,
            ply=ply,
            mode=mode,
            limits=limits,
            force=force,
        )

        context = _build_context(session, ply)
        payload = {
            "game_id": session.game_id,
            "mode": mode,
            "limits": {
                "movetime_ms": limits.movetime_ms,
                "depth": limits.depth,
                "nodes": limits.nodes,
                "multipv": limits.multipv,
            },
            "move": {
                "ply": ply,
                "fen_before": context.board_before.fen(),
                "played_san": context.played_san,
                "played_uci": context.played_uci,
                "best_san": analysis.best,
                "best_uci": _best_san_to_uci(context.board_before, analysis.best),
                "pv": analysis.pv,
                "score_before": analysis.score_before.model_dump(),
                "score_after": analysis.score_after.model_dump(),
                "delta_cp": analysis.delta_cp,
                "classification": analysis.classification,
                "suggestion": analysis.suggestion,
            },
        }

        timeout_seconds = max(1, settings.move_explanation_timeout_seconds)
        try:
            explanation = await asyncio.wait_for(
                asyncio.to_thread(build_llm_move_explanation, payload),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Move explanation timed out") from exc
        except Exception as exc:
            raise RuntimeError("Move explanation failed") from exc

        if not explanation:
            raise RuntimeError("Move explanation unavailable")

        self._put_cached(session, cache_key, explanation)
        return MoveExplanationResponse(ply=ply, explanation=explanation)

    def _cache_key(self, game_id: str, ply: int, mode: str, limits: AnalysisLimits) -> str:
        limits_key = f"{limits.movetime_ms}:{limits.depth}:{limits.nodes}:{limits.multipv}"
        llm_key = f"{settings.move_explanation_model}:{settings.move_explanation_prompt_version}"
        return f"{game_id}:{ply}:{mode}:{limits_key}:{llm_key}"

    def _get_cached(self, session: GameSession, cache_key: str) -> str | None:
        with session.cache_lock:
            return session.move_explanation_cache.get(cache_key)

    def _put_cached(self, session: GameSession, cache_key: str, explanation: str) -> None:
        with session.cache_lock:
            session.move_explanation_cache[cache_key] = explanation


def _build_context(session: GameSession, ply: int) -> _MoveContext:
    board = chess.Board(session.initial_fen)
    for idx, move_model in enumerate(session.moves, start=1):
        move = chess.Move.from_uci(move_model.uci)
        if idx == ply:
            board_before = board.copy(stack=False)
            return _MoveContext(
                board_before=board_before,
                played_san=board_before.san(move),
                played_uci=move_model.uci,
            )
        board.push(move)
    raise ValueError(f"ply out of range: {ply}")


def _best_san_to_uci(board: chess.Board, best_san: str) -> str | None:
    if not best_san or best_san == "(none)":
        return None
    try:
        return board.parse_san(best_san).uci()
    except ValueError:
        return None


move_explanation_service = MoveExplanationService()
