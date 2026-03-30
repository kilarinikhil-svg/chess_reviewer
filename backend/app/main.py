from __future__ import annotations

import asyncio
import chess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import settings
from app.models.schemas import (
    ChessComImportRequest,
    ChessComImportResponse,
    ChessComSelectRequest,
    CoachAnalysisRequest,
    CoachAnalysisResponse,
    FenAnalysisRequest,
    FenAnalysisResponse,
    FullAnalysisRequest,
    FullAnalysisStartResponse,
    FullAnalysisStatusResponse,
    ImportGameResponse,
    ImportPgnRequest,
    MoveBatchAnalysisRequest,
    MoveBatchAnalysisResponse,
    MoveExplanationRequest,
    MoveExplanationResponse,
    MoveAnalysisRequest,
    MoveAnalysisResponse,
)
from app.services.analysis_jobs import job_store, run_full_analysis
from app.services.chesscom import fetch_archives, fetch_game_pgn
from app.services.coach_analysis import analyze_multi_game_pgn
from app.services.engine import engine_service
from app.services.game_parser import parse_pgn_or_fen
from app.services.move_analysis import move_analysis_service
from app.services.move_explanation import move_explanation_service
from app.services.session_store import session_store

app = FastAPI(title="Chess Analyzer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin] if settings.cors_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    if settings.frontend_url:
        return RedirectResponse(url=settings.frontend_url, status_code=307)
    return {"name": "Chess Analyzer API", "health": "/health"}


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await engine_service.shutdown()


@app.post("/api/games/import/pgn", response_model=ImportGameResponse)
async def import_pgn(req: ImportPgnRequest) -> ImportGameResponse:
    try:
        initial_fen, moves, headers = parse_pgn_or_fen(req.pgn, req.fen, req.moves)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = session_store.create(initial_fen, moves, headers)
    return ImportGameResponse(
        game_id=session.game_id,
        initial_fen=session.initial_fen,
        moves=session.moves,
        headers=session.headers,
    )


@app.post("/api/games/import/chesscom", response_model=ChessComImportResponse)
async def import_chesscom(req: ChessComImportRequest) -> ChessComImportResponse:
    try:
        archives = await fetch_archives(req.username)
        return ChessComImportResponse(archives=archives)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch archives: {exc}") from exc


@app.post("/api/games/import/chesscom/select", response_model=ImportGameResponse)
async def import_chesscom_select(req: ChessComSelectRequest) -> ImportGameResponse:
    try:
        pgn = await fetch_game_pgn(req.archive_url, req.game_index)
        initial_fen, moves, headers = parse_pgn_or_fen(pgn, None, [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to import game: {exc}") from exc

    session = session_store.create(initial_fen, moves, headers)
    return ImportGameResponse(
        game_id=session.game_id,
        initial_fen=session.initial_fen,
        moves=session.moves,
        headers=session.headers,
    )


@app.post("/api/analysis/move", response_model=MoveAnalysisResponse)
async def analyze_move(req: MoveAnalysisRequest) -> MoveAnalysisResponse:
    session = session_store.get(req.game_id)
    if not session:
        raise HTTPException(status_code=404, detail="game_id not found")
    if req.ply < 1 or req.ply > len(session.moves):
        raise HTTPException(status_code=400, detail="ply out of range")

    try:
        return await move_analysis_service.analyze_move(
            session=session,
            ply=req.ply,
            mode=req.mode,
            limits=req.limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analysis/move-explanation", response_model=MoveExplanationResponse)
async def analyze_move_explanation(req: MoveExplanationRequest) -> MoveExplanationResponse:
    session = session_store.get(req.game_id)
    if not session:
        raise HTTPException(status_code=404, detail="game_id not found")
    if req.ply < 1 or req.ply > len(session.moves):
        raise HTTPException(status_code=400, detail="ply out of range")

    try:
        return await move_explanation_service.explain_move(
            session=session,
            ply=req.ply,
            mode=req.mode,
            limits=req.limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/analysis/moves-batch", response_model=MoveBatchAnalysisResponse)
async def analyze_moves_batch(req: MoveBatchAnalysisRequest) -> MoveBatchAnalysisResponse:
    session = session_store.get(req.game_id)
    if not session:
        raise HTTPException(status_code=404, detail="game_id not found")

    if not req.plies:
        return MoveBatchAnalysisResponse(results_by_ply=[])

    if any(ply < 1 or ply > len(session.moves) for ply in req.plies):
        raise HTTPException(status_code=400, detail="One or more plies are out of range")

    try:
        results = await move_analysis_service.analyze_moves(
            session=session,
            plies=req.plies,
            mode=req.mode,
            limits=req.limits,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MoveBatchAnalysisResponse(results_by_ply=results)


@app.post("/api/analysis/fen", response_model=FenAnalysisResponse)
async def analyze_fen(req: FenAnalysisRequest) -> FenAnalysisResponse:
    try:
        board = chess.Board(req.fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}") from exc

    try:
        score, best_uci, pv, incomplete = await engine_service.analyze(board, req.limits)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    best_san = best_uci
    if best_uci:
        candidate = chess.Move.from_uci(best_uci)
        if candidate in board.legal_moves:
            best_san = board.san(candidate)

    return FenAnalysisResponse(
        fen=board.fen(),
        score=score,
        best=best_san,
        pv=pv,
        analysis_incomplete=incomplete,
    )


@app.post("/api/analysis/full", response_model=FullAnalysisStartResponse)
async def analyze_full(req: FullAnalysisRequest) -> FullAnalysisStartResponse:
    session = session_store.get(req.game_id)
    if not session:
        raise HTTPException(status_code=404, detail="game_id not found")

    job = job_store.create()
    asyncio.create_task(run_full_analysis(job.job_id, session, req.limits))
    return FullAnalysisStartResponse(job_id=job.job_id)


@app.get("/api/analysis/full/{job_id}", response_model=FullAnalysisStatusResponse)
async def full_status(job_id: str) -> FullAnalysisStatusResponse:
    response = job_store.to_response(job_id)
    if not response:
        raise HTTPException(status_code=404, detail="job not found")
    return response


@app.post("/api/coach/analyze", response_model=CoachAnalysisResponse)
async def coach_analyze(req: CoachAnalysisRequest) -> CoachAnalysisResponse:
    try:
        return analyze_multi_game_pgn(req.pgn, req.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/sessions/{game_id}")
async def delete_session(game_id: str) -> dict[str, bool]:
    deleted = session_store.delete(game_id)
    return {"deleted": deleted}
