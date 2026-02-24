from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import chess
import chess.engine

from app.config import settings
from app.models.schemas import AnalysisLimits, ScoreModel


@dataclass
class _EngineWorker:
    engine: chess.engine.SimpleEngine
    lock: threading.Lock


class EngineService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(2, settings.stockfish_pool_size * 2, settings.deep_job_workers + 2)
        )
        self._workers_lock = threading.Lock()
        self._workers: list[_EngineWorker] = []
        self._next_worker = 0

    async def analyze(self, board: chess.Board, limits: AnalysisLimits) -> tuple[ScoreModel, str, list[str], bool]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._analyze_with_worker_sync, board.fen(), limits)

    async def shutdown(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._shutdown_sync)
        self._executor.shutdown(wait=False)

    def _shutdown_sync(self) -> None:
        with self._workers_lock:
            workers = self._workers[:]
            self._workers.clear()
            self._next_worker = 0
        for worker in workers:
            try:
                worker.engine.quit()
            except Exception:
                pass

    def _build_engine_options(self, engine: chess.engine.SimpleEngine) -> dict[str, object]:
        options: dict[str, object] = {}
        if "Threads" in engine.options:
            options["Threads"] = settings.stockfish_threads
        if "Hash" in engine.options:
            options["Hash"] = settings.stockfish_hash_mb
        if "Use NNUE" in engine.options:
            options["Use NNUE"] = True
        if "UCI_LimitStrength" in engine.options:
            options["UCI_LimitStrength"] = False
        if "Skill Level" in engine.options:
            options["Skill Level"] = 20
        if settings.stockfish_syzygy_path and "SyzygyPath" in engine.options:
            options["SyzygyPath"] = settings.stockfish_syzygy_path
        if "SyzygyProbeLimit" in engine.options:
            options["SyzygyProbeLimit"] = settings.stockfish_syzygy_probe_limit
        return options

    def _ensure_workers(self) -> None:
        if os.path.isabs(settings.stockfish_path) and not os.path.exists(settings.stockfish_path):
            raise RuntimeError(
                f"Stockfish binary not found at '{settings.stockfish_path}'. "
                "Set STOCKFISH_PATH to a valid executable path."
            )
        with self._workers_lock:
            if self._workers:
                return
            try:
                for _ in range(max(1, settings.stockfish_pool_size)):
                    engine = chess.engine.SimpleEngine.popen_uci(settings.stockfish_path)
                    options = self._build_engine_options(engine)
                    if options:
                        engine.configure(options)
                    self._workers.append(_EngineWorker(engine=engine, lock=threading.Lock()))
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"Stockfish binary '{settings.stockfish_path}' was not found. "
                    "Install stockfish and/or set STOCKFISH_PATH."
                ) from exc
            except Exception as exc:
                for worker in self._workers:
                    try:
                        worker.engine.quit()
                    except Exception:
                        pass
                self._workers = []
                raise RuntimeError(f"Failed to initialize Stockfish worker pool: {exc}") from exc

    def _acquire_worker(self) -> _EngineWorker:
        self._ensure_workers()
        with self._workers_lock:
            worker = self._workers[self._next_worker % len(self._workers)]
            self._next_worker = (self._next_worker + 1) % len(self._workers)
            return worker

    def _analyze_with_worker_sync(self, fen: str, limits: AnalysisLimits) -> tuple[ScoreModel, str, list[str], bool]:
        board = chess.Board(fen)
        worker = self._acquire_worker()
        try:
            with worker.lock:
                limit = chess.engine.Limit(
                    time=(limits.movetime_ms / 1000.0) if limits.movetime_ms else None,
                    depth=limits.depth,
                    nodes=limits.nodes,
                )
                info = worker.engine.analyse(board, limit=limit, multipv=max(1, limits.multipv))
            if isinstance(info, list):
                first = info[0]
            else:
                first = info

            score = first.get("score")
            if score is None:
                return ScoreModel(type="unknown", value=0), "", [], True

            pov = score.pov(board.turn)
            if pov.is_mate():
                score_model = ScoreModel(type="mate", value=int(pov.mate() or 0))
            else:
                score_model = ScoreModel(type="cp", value=int(pov.score(mate_score=100000) or 0))

            pv_moves = first.get("pv", [])
            pv_uci = [m.uci() for m in pv_moves[:8]]

            best_move = first.get("pv", [None])[0]
            best_move_uci = best_move.uci() if best_move else ""

            return score_model, best_move_uci, pv_uci, False
        except Exception:
            return ScoreModel(type="unknown", value=0), "", [], True


engine_service = EngineService()
