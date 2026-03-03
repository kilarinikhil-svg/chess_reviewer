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
    MoveAnalysisRequest,
    MoveAnalysisResponse,
)
from app.services.analysis_jobs import job_store, run_full_analysis
from app.services.chesscom import fetch_archives, fetch_game_pgn
from app.services.classification import build_suggestion, classify_move, score_to_cp_equivalent
from app.services.engine import engine_service
from app.services.game_parser import parse_pgn_or_fen
from app.services.session_store import session_store
from app.services.coach_analysis import analyze_multi_game_pgn

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

    board_before = chess.Board(session.initial_fen)
    for move_model in session.moves[: req.ply - 1]:
        board_before.push(chess.Move.from_uci(move_model.uci))
    played_move = chess.Move.from_uci(session.moves[req.ply - 1].uci)
    played_san = board_before.san(played_move)
    board_after = board_before.copy(stack=False)
    board_after.push(played_move)

    try:
        (score_before, best_uci, pv, inc_before), (score_after, _, _, inc_after) = await asyncio.gather(
            engine_service.analyze(board_before, req.limits),
            engine_service.analyze(board_after, req.limits),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    best_san = best_uci
    if best_uci:
        candidate = chess.Move.from_uci(best_uci)
        if candidate in board_before.legal_moves:
            best_san = board_before.san(candidate)

    before_cp = score_to_cp_equivalent(score_before)
    after_cp = score_to_cp_equivalent(score_after)
    mover_after_cp = -after_cp
    delta_cp = before_cp - mover_after_cp
    classification = classify_move(delta_cp, score_before, score_after)

    return MoveAnalysisResponse(
        ply=req.ply,
        played=played_san,
        best=best_san,
        score_before=score_before,
        score_after=score_after,
        delta_cp=delta_cp,
        classification=classification,
        pv=pv,
        suggestion=build_suggestion(best_san, classification, delta_cp),
        analysis_incomplete=inc_before or inc_after,
    )


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
