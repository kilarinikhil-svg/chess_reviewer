from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field

import chess

from app.config import settings
from app.models.schemas import AnalysisLimits, FullAnalysisStatusResponse, MoveAnalysisResponse, ScoreModel
from app.services.classification import build_suggestion, classify_move, score_to_cp_equivalent
from app.services.engine import engine_service
from app.services.session_store import GameSession


@dataclass
class AnalysisJob:
    job_id: str
    status: str = "pending"
    progress: float = 0.0
    results_by_ply: list[MoveAnalysisResponse] = field(default_factory=list)
    error: str | None = None


class AnalysisJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, AnalysisJob] = {}

    def create(self) -> AnalysisJob:
        job = AnalysisJob(job_id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> AnalysisJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def to_response(self, job_id: str) -> FullAnalysisStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return FullAnalysisStatusResponse(
                status=job.status,
                progress=job.progress,
                results_by_ply=job.results_by_ply,
                error=job.error,
            )


job_store = AnalysisJobStore()


async def _analyze_position(
    index: int, fen: str, limits: AnalysisLimits, semaphore: asyncio.Semaphore
) -> tuple[int, tuple]:
    async with semaphore:
        try:
            score, best_uci, pv, incomplete = await engine_service.analyze(chess.Board(fen), limits)
            return index, (score, best_uci, pv, incomplete)
        except Exception:
            return index, (ScoreModel(type="unknown", value=0), "", [], True)


async def run_full_analysis(job_id: str, session: GameSession, limits: AnalysisLimits) -> None:
    job = job_store.get(job_id)
    if job is None:
        return

    try:
        job.status = "running"
        total = len(session.moves)
        board = chess.Board(session.initial_fen)
        boards_before: list[chess.Board] = []
        position_fens: list[str] = [board.fen()]

        for move_model in session.moves:
            boards_before.append(board.copy(stack=False))
            board.push(chess.Move.from_uci(move_model.uci))
            position_fens.append(board.fen())

        position_results: list[tuple | None] = [None] * len(position_fens)
        semaphore = asyncio.Semaphore(max(1, settings.stockfish_pool_size))
        tasks = [
            asyncio.create_task(_analyze_position(index, fen, limits, semaphore))
            for index, fen in enumerate(position_fens)
        ]

        completed = 0
        for done in asyncio.as_completed(tasks):
            index, result = await done
            position_results[index] = result
            completed += 1
            job.progress = 0.75 * (completed / max(1, len(position_fens)))

        for index, move_model in enumerate(session.moves):
            score_before, best_uci, pv, inc_before = position_results[index]  # type: ignore[misc]
            score_after, _, _, inc_after = position_results[index + 1]  # type: ignore[misc]
            board_before = boards_before[index]

            before_cp = score_to_cp_equivalent(score_before)
            after_cp = score_to_cp_equivalent(score_after)
            # score_after is from next side-to-move perspective; flip back to mover perspective.
            mover_after_cp = -after_cp
            delta_cp = before_cp - mover_after_cp
            classification = classify_move(delta_cp, score_before, score_after)

            if best_uci:
                best_move = chess.Move.from_uci(best_uci)
                best_san = board_before.san(best_move) if best_move in board_before.legal_moves else best_uci
            else:
                best_san = "(none)"

            result = MoveAnalysisResponse(
                ply=move_model.ply,
                played=move_model.san,
                best=best_san,
                score_before=score_before,
                score_after=score_after,
                delta_cp=delta_cp,
                classification=classification,
                pv=pv,
                suggestion=build_suggestion(best_san, classification, delta_cp),
                analysis_incomplete=inc_before or inc_after,
            )
            job.results_by_ply.append(result)
            job.progress = 0.75 + (0.25 * (index + 1) / max(1, total))

            await asyncio.sleep(0)

        job.status = "completed"
        job.progress = 1.0
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
