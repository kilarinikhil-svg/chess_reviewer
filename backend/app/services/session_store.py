from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from app.config import settings
from app.models.schemas import MoveAnalysisResponse, MoveModel


@dataclass
class GameSession:
    game_id: str
    initial_fen: str
    moves: list[MoveModel]
    headers: dict[str, str]
    created_at: float = field(default_factory=time.time)
    analysis_cache: dict[str, MoveAnalysisResponse] = field(default_factory=dict)
    cache_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, GameSession] = {}

    def create(self, initial_fen: str, moves: list[MoveModel], headers: dict[str, str]) -> GameSession:
        with self._lock:
            self._prune_locked()
            session = GameSession(game_id=str(uuid.uuid4()), initial_fen=initial_fen, moves=moves, headers=headers)
            self._sessions[session.game_id] = session
        return session

    def get(self, game_id: str) -> GameSession | None:
        with self._lock:
            self._prune_locked()
            return self._sessions.get(game_id)

    def delete(self, game_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(game_id, None) is not None

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            game_id
            for game_id, session in self._sessions.items()
            if now - session.created_at > settings.session_ttl_seconds
        ]
        for game_id in expired:
            self._sessions.pop(game_id, None)


session_store = SessionStore()
