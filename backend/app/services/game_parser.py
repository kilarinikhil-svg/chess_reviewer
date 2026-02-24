from __future__ import annotations

import io
import chess
import chess.pgn

from app.models.schemas import MoveModel


def parse_pgn_or_fen(pgn: str | None, fen: str | None, moves: list[str]) -> tuple[str, list[MoveModel], dict[str, str]]:
    if pgn:
        return _parse_pgn(pgn)
    if fen:
        return _parse_fen_and_moves(fen, moves)
    raise ValueError("Either pgn or fen must be provided")


def _parse_pgn(pgn_text: str) -> tuple[str, list[MoveModel], dict[str, str]]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Invalid PGN")

    board = game.board()
    move_models: list[MoveModel] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        san = board.san(move)
        color = "white" if board.turn == chess.WHITE else "black"
        move_models.append(MoveModel(ply=ply, san=san, uci=move.uci(), color=color))
        board.push(move)

    headers = {k: str(v) for k, v in game.headers.items()}
    return game.board().fen(), move_models, headers


def _parse_fen_and_moves(fen: str, moves: list[str]) -> tuple[str, list[MoveModel], dict[str, str]]:
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError("Invalid FEN") from exc

    move_models: list[MoveModel] = []
    for ply, m in enumerate(moves, start=1):
        move = chess.Move.from_uci(m)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move at ply {ply}: {m}")
        san = board.san(move)
        color = "white" if board.turn == chess.WHITE else "black"
        move_models.append(MoveModel(ply=ply, san=san, uci=move.uci(), color=color))
        board.push(move)

    return fen, move_models, {"Source": "FEN"}
