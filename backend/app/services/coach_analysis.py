from __future__ import annotations

import io
import logging
from collections import Counter

import chess
import chess.pgn

from app.models.schemas import (
    CoachActionItem,
    CoachAnalysisResponse,
    CoachColorStats,
    CoachMistakeModel,
    CoachPhaseBreakdown,
)
from app.services.coach_llm import build_llm_coach_report

logger = logging.getLogger(__name__)

MISTAKE_DEFS = {
    "early_queen": (
        "Early queen adventures",
        "Queen moves repeatedly in the opening, which often loses time and invites tactics.",
    ),
    "late_castle": (
        "Delayed king safety",
        "Castling is delayed well past the opening, leaving the king vulnerable to direct attacks.",
    ),
    "edge_pawn_push": (
        "Premature wing pawn pushes",
        "Frequent h/a-pawn pushes in the opening create weaknesses before development is complete.",
    ),
    "quick_mate": (
        "Quick tactical collapses",
        "Games ending very quickly are often caused by one-move blunders or missed mate threats.",
    ),
    "opening_loss": (
        "Opening phase losses",
        "Many losses happen early, indicating opening setup and threat awareness need work.",
    ),
}


RESULT_POINTS = {
    "1-0": 1.0,
    "0-1": 0.0,
    "1/2-1/2": 0.5,
}


def analyze_multi_game_pgn(pgn_blob: str, username_hint: str | None = None) -> CoachAnalysisResponse:
    stream = io.StringIO(pgn_blob)
    games = []
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        games.append(game)

    if not games:
        raise ValueError("No valid games found in PGN input")

    player = _detect_player(games, username_hint)

    mistake_counts: Counter[str] = Counter()
    mistake_examples: dict[str, list[str]] = {k: [] for k in MISTAKE_DEFS}

    phase_counter: Counter[str] = Counter()
    color_stats = {
        "white": {"games": 0, "wins": 0, "losses": 0, "draws": 0},
        "black": {"games": 0, "wins": 0, "losses": 0, "draws": 0},
    }

    for idx, game in enumerate(games, start=1):
        result = str(game.headers.get("Result", "*"))
        white = str(game.headers.get("White", ""))
        black = str(game.headers.get("Black", ""))

        if player == white:
            color = "white"
            opponent = black
            point = RESULT_POINTS.get(result)
        elif player == black:
            color = "black"
            opponent = white
            point = None if result == "*" else (1 - RESULT_POINTS.get(result, 0.5))
        else:
            continue

        color_stats[color]["games"] += 1
        if point == 1:
            color_stats[color]["wins"] += 1
        elif point == 0:
            color_stats[color]["losses"] += 1
        elif point == 0.5:
            color_stats[color]["draws"] += 1

        board = game.board()
        player_castled_ply = None
        player_queen_moves_opening = 0
        player_edge_pawn_push_opening = 0
        total_plies = 0

        for ply, move in enumerate(game.mainline_moves(), start=1):
            turn_color = "white" if board.turn == chess.WHITE else "black"
            piece = board.piece_at(move.from_square)
            if turn_color == color and piece:
                if piece.piece_type == chess.KING and abs(chess.square_file(move.to_square) - chess.square_file(move.from_square)) == 2:
                    if player_castled_ply is None:
                        player_castled_ply = ply
                if ply <= 12 and piece.piece_type == chess.QUEEN:
                    player_queen_moves_opening += 1
                if ply <= 12 and piece.piece_type == chess.PAWN:
                    from_file = chess.square_file(move.from_square)
                    if from_file in (0, 7):
                        player_edge_pawn_push_opening += 1

            total_plies = ply
            board.push(move)

        if player_queen_moves_opening >= 2:
            _record_mistake(mistake_counts, mistake_examples, "early_queen", idx, opponent, total_plies)
        if player_castled_ply is None or player_castled_ply > 16:
            _record_mistake(mistake_counts, mistake_examples, "late_castle", idx, opponent, total_plies)
        if player_edge_pawn_push_opening >= 2:
            _record_mistake(mistake_counts, mistake_examples, "edge_pawn_push", idx, opponent, total_plies)
        if total_plies <= 20:
            _record_mistake(mistake_counts, mistake_examples, "quick_mate", idx, opponent, total_plies)
        if point == 0 and total_plies <= 30:
            _record_mistake(mistake_counts, mistake_examples, "opening_loss", idx, opponent, total_plies)

        if total_plies <= 20:
            phase_counter["opening"] += 1
        elif total_plies <= 60:
            phase_counter["middlegame"] += 1
        else:
            phase_counter["endgame"] += 1

    sorted_mistakes = sorted(mistake_counts.items(), key=lambda item: item[1], reverse=True)
    seed_top_mistakes = []
    for key, count in sorted_mistakes[:3]:
        label, description = MISTAKE_DEFS[key]
        seed_top_mistakes.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "description": description,
                "examples": mistake_examples[key][:3],
            }
        )

    llm_payload = {
        "player": player,
        "games_analyzed": sum(stat["games"] for stat in color_stats.values()),
        "detected_patterns": seed_top_mistakes,
        "phase_breakdown": {
            "opening": phase_counter.get("opening", 0),
            "middlegame": phase_counter.get("middlegame", 0),
            "endgame": phase_counter.get("endgame", 0),
        },
        "color_stats": color_stats,
    }
    llm_report = build_llm_coach_report(llm_payload)
    if not llm_report:
        raise RuntimeError("LLM coach analysis unavailable. Heuristic fallback is disabled.")

    top_mistakes = _parse_llm_top_mistakes(llm_report)
    actions = _parse_llm_actions(llm_report)
    next_game_focus = _parse_llm_next_focus(llm_report)

    if not top_mistakes or not actions or len(next_game_focus) < 3:
        raise RuntimeError("LLM response missing required coach sections.")

    logger.info("Coach analysis generated with source=llm")

    return CoachAnalysisResponse(
        username=player,
        games_analyzed=sum(stat["games"] for stat in color_stats.values()),
        top_mistakes=top_mistakes,
        phase_breakdown=CoachPhaseBreakdown(
            opening=phase_counter.get("opening", 0),
            middlegame=phase_counter.get("middlegame", 0),
            endgame=phase_counter.get("endgame", 0),
        ),
        color_stats={
            color: CoachColorStats(**stats)
            for color, stats in color_stats.items()
        },
        action_plan=actions,
        next_game_focus=next_game_focus,
    )


def _detect_player(games: list[chess.pgn.Game], username_hint: str | None) -> str:
    if username_hint:
        return username_hint

    counter: Counter[str] = Counter()
    for game in games:
        white = str(game.headers.get("White", "")).strip()
        black = str(game.headers.get("Black", "")).strip()
        if white:
            counter[white] += 1
        if black:
            counter[black] += 1

    if not counter:
        return "Unknown"

    return counter.most_common(1)[0][0]


def _record_mistake(
    counts: Counter[str],
    examples: dict[str, list[str]],
    key: str,
    game_idx: int,
    opponent: str,
    plies: int,
) -> None:
    counts[key] += 1
    examples[key].append(f"Game {game_idx} vs {opponent or 'Unknown'} (ended around ply {plies})")


def _parse_llm_top_mistakes(llm_report: dict) -> list[CoachMistakeModel]:
    raw_items = llm_report.get("top_mistakes")
    if not isinstance(raw_items, list):
        return []

    parsed = []
    for idx, item in enumerate(raw_items[:3], start=1):
        if not isinstance(item, dict):
            logger.warning("Ignoring malformed LLM top_mistakes item at index %s", idx)
            continue
        evidence_raw = item.get("evidence", [])
        evidence = [str(x).strip() for x in evidence_raw if str(x).strip()][:3] if isinstance(evidence_raw, list) else []
        count = _safe_int(item.get("count"), fallback=len(evidence))
        parsed.append(
            CoachMistakeModel(
                key=f"llm_{idx}",
                label=str(item.get("label", "Recurring pattern")).strip() or "Recurring pattern",
                count=max(0, count),
                description=str(item.get("description") or item.get("fix") or "").strip(),
                examples=evidence,
            )
        )
    return parsed


def _parse_llm_actions(llm_report: dict) -> list[CoachActionItem]:
    raw_items = llm_report.get("action_plan")
    if not isinstance(raw_items, list):
        return []

    parsed = []
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            logger.warning("Ignoring malformed LLM action_plan item")
            continue
        raw_drills = item.get("drills", [])
        drills = [str(d).strip() for d in raw_drills if str(d).strip()][:4] if isinstance(raw_drills, list) else []
        focus = str(item.get("focus", "Training focus")).strip() or "Training focus"
        parsed.append(CoachActionItem(focus=focus, drills=drills))
    return parsed


def _parse_llm_next_focus(llm_report: dict) -> list[str]:
    raw_items = llm_report.get("next_game_focus")
    if not isinstance(raw_items, list):
        return []
    return [str(item).strip() for item in raw_items[:3] if str(item).strip()]


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
