from __future__ import annotations

from app.models.schemas import ScoreModel


def score_to_cp_equivalent(score: ScoreModel) -> int:
    if score.type == "cp":
        return score.value
    if score.type == "mate":
        # Force mates far from 0 to emphasize tactical urgency.
        return 10000 if score.value > 0 else -10000
    return 0


def classify_move(delta_cp: int, before: ScoreModel, after: ScoreModel) -> str:
    abs_loss = max(delta_cp, 0)

    if before.type == "mate" or after.type == "mate":
        if before.type == "mate" and before.value > 0 and after.type != "mate":
            return "blunder"
        if after.type == "mate" and after.value < 0:
            return "blunder"
        if abs_loss > 90:
            return "mistake"

    if abs_loss <= 10:
        return "best"
    if abs_loss <= 40:
        return "good"
    if abs_loss <= 90:
        return "inaccuracy"
    if abs_loss <= 180:
        return "mistake"
    return "blunder"


def build_suggestion(best_san: str, classification: str, delta_cp: int) -> str:
    if classification == "best":
        return "You played the best move in this position."
    return f"{best_san} was stronger here (approx {abs(delta_cp)} centipawns better)."
