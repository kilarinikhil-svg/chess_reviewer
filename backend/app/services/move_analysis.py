from __future__ import annotations

import asyncio
from dataclasses import dataclass

import chess

from app.models.schemas import AnalysisLimits, MoveAnalysisResponse
from app.services.classification import build_suggestion, classify_move, score_to_cp_equivalent
from app.services.engine import engine_service
from app.services.session_store import GameSession


@dataclass
class _MoveContext:
    ply: int
    board_before: chess.Board
    board_after: chess.Board
    played_san: str


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
            new_results = await asyncio.gather(
                *[
                    self._analyze_with_stockfish_context(context, limits)
                    for context in pending_contexts
                ]
            )
            for result in new_results:
                results_by_ply[result.ply] = result
                cache_key = self._cache_key(session.game_id, result.ply, mode, limits)
                self._put_cached(session, cache_key, result)

        return [results_by_ply[ply] for ply in plies if ply in results_by_ply]

    async def _analyze_with_stockfish_context(
        self,
        context: _MoveContext,
        limits: AnalysisLimits,
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
            fallback_reason=None,
            analysis_incomplete=inc_before or inc_after,
        )

    def _cache_key(self, game_id: str, ply: int, mode: str, limits: AnalysisLimits) -> str:
        limits_key = f"{limits.movetime_ms}:{limits.depth}:{limits.nodes}:{limits.multipv}"
        return f"{game_id}:{ply}:{mode}:{limits_key}"

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
            )
        board.push(move)

    missing = [ply for ply in plies if ply not in contexts]
    if missing:
        raise ValueError(f"ply out of range: {missing[0]}")

    return [contexts[ply] for ply in plies]
