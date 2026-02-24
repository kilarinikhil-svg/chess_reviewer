from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ImportPgnRequest(BaseModel):
    pgn: Optional[str] = None
    fen: Optional[str] = None
    moves: list[str] = Field(default_factory=list)


class MoveModel(BaseModel):
    ply: int
    san: str
    uci: str
    color: Literal["white", "black"]


class ImportGameResponse(BaseModel):
    game_id: str
    initial_fen: str
    moves: list[MoveModel]
    headers: dict[str, str]


class ChessComImportRequest(BaseModel):
    username: str


class ArchiveModel(BaseModel):
    year: int
    month: int
    url: str


class ChessComImportResponse(BaseModel):
    archives: list[ArchiveModel]


class ChessComSelectRequest(BaseModel):
    archive_url: str
    game_index: int


class AnalysisLimits(BaseModel):
    movetime_ms: Optional[int] = 5000
    nodes: Optional[int] = None
    depth: Optional[int] = 24
    multipv: int = 1


class ScoreModel(BaseModel):
    type: Literal["cp", "mate", "unknown"]
    value: int


class MoveAnalysisRequest(BaseModel):
    game_id: str
    ply: int
    mode: Literal["realtime", "deep"] = "realtime"
    limits: AnalysisLimits = Field(default_factory=AnalysisLimits)


class MoveAnalysisResponse(BaseModel):
    ply: int
    played: str
    best: str
    score_before: ScoreModel
    score_after: ScoreModel
    delta_cp: int
    classification: Literal["best", "good", "inaccuracy", "mistake", "blunder"]
    pv: list[str]
    suggestion: str
    analysis_incomplete: bool = False


class FullAnalysisRequest(BaseModel):
    game_id: str
    mode: Literal["deep"] = "deep"
    limits: AnalysisLimits = Field(default_factory=lambda: AnalysisLimits(depth=24, movetime_ms=5000))


class FullAnalysisStartResponse(BaseModel):
    job_id: str


class FullAnalysisStatusResponse(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]
    progress: float
    results_by_ply: list[MoveAnalysisResponse] = Field(default_factory=list)
    error: Optional[str] = None


class CoachAnalysisRequest(BaseModel):
    pgn: str
    username: Optional[str] = None


class CoachMistakeModel(BaseModel):
    key: str
    label: str
    count: int
    description: str
    examples: list[str] = Field(default_factory=list)


class CoachPhaseBreakdown(BaseModel):
    opening: int
    middlegame: int
    endgame: int


class CoachColorStats(BaseModel):
    games: int
    wins: int
    losses: int
    draws: int


class CoachActionItem(BaseModel):
    focus: str
    drills: list[str] = Field(default_factory=list)


class CoachAnalysisResponse(BaseModel):
    username: str
    games_analyzed: int
    top_mistakes: list[CoachMistakeModel] = Field(default_factory=list)
    phase_breakdown: CoachPhaseBreakdown
    color_stats: dict[str, CoachColorStats]
    action_plan: list[CoachActionItem] = Field(default_factory=list)
    next_game_focus: list[str] = Field(default_factory=list)
