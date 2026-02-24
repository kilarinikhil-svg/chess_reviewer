from fastapi.testclient import TestClient

from app.main import app
from app.services.engine import engine_service


client = TestClient(app)


def test_import_pgn_and_analyze_move(monkeypatch):
    pgn = """
[Event \"Live Chess\"]
[Site \"Chess.com\"]
[Date \"2026.02.23\"]
[Round \"-\"]
[White \"A\"]
[Black \"B\"]
[Result \"*\"]

1. e4 e5 2. Nf3 Nc6 *
"""

    imported = client.post("/api/games/import/pgn", json={"pgn": pgn}).json()
    assert imported["game_id"]
    assert len(imported["moves"]) == 4

    async def fake_analyze(board, limits):
        if board.turn:
            return ({"type": "cp", "value": 50}, "d2d4", ["d2d4", "g8f6"], False)
        return ({"type": "cp", "value": -10}, "", [], False)

    monkeypatch.setattr(engine_service, "analyze", fake_analyze)

    analysis = client.post(
        "/api/analysis/move",
        json={"game_id": imported["game_id"], "ply": 1, "mode": "realtime", "limits": {"movetime_ms": 300}},
    ).json()

    assert analysis["ply"] == 1
    assert analysis["classification"] in {"best", "good", "inaccuracy", "mistake", "blunder"}
    assert analysis["best"]


def test_import_fen_invalid():
    response = client.post("/api/games/import/pgn", json={"fen": "invalid"})
    assert response.status_code == 400
