from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ScoreModel
from app.services import coach_llm
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
            return (ScoreModel(type="cp", value=50), "d2d4", ["d2d4", "g8f6"], False)
        return (ScoreModel(type="cp", value=-10), "", [], False)

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


def test_coach_multi_game_analysis(monkeypatch):
    pgn = """
[Event "G1"]
[White "nikhil_kilari"]
[Black "Opp1"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#

[Event "G2"]
[White "Opp2"]
[Black "nikhil_kilari"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#
"""

    def fake_llm_report(_payload):
        return {
            "top_mistakes": [
                {"label": "Missed tactics", "count": 2, "description": "Missed forks in sharp positions", "evidence": ["G1 move 9", "G2 move 14"]},
            ],
            "action_plan": [
                {"focus": "Tactics", "drills": ["Solve 20 fork puzzles", "Review missed tactical motifs"]},
            ],
            "next_game_focus": ["Blunder check each move", "Castle early", "Improve piece development"],
        }

    monkeypatch.setattr("app.services.coach_analysis.build_llm_coach_report", fake_llm_report)
    response = client.post("/api/coach/analyze", json={"pgn": pgn, "username": "nikhil_kilari"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "nikhil_kilari"
    assert data["games_analyzed"] == 2
    assert "top_mistakes" in data
    assert "phase_breakdown" in data
    assert "color_stats" in data


def test_coach_analysis_requires_valid_llm_report(monkeypatch):
    pgn = """
[Event "G1"]
[White "nikhil_kilari"]
[Black "Opp1"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#
"""

    def fake_llm_report(_payload):
        return {
            "top_mistakes": ["not-a-dict"],
            "action_plan": ["also-not-a-dict"],
            "next_game_focus": ["Check king safety", "Develop first", "Blunder check"],
        }

    monkeypatch.setattr("app.services.coach_analysis.build_llm_coach_report", fake_llm_report)
    response = client.post("/api/coach/analyze", json={"pgn": pgn, "username": "nikhil_kilari"})
    assert response.status_code == 502


def test_parse_json_object_handles_fenced_json():
    raw = """
```json
{
  "top_mistakes": [],
  "action_plan": [],
  "next_game_focus": ["a", "b", "c"]
}
```
"""
    parsed = coach_llm._parse_json_object(raw)
    assert parsed is not None
    assert parsed["next_game_focus"] == ["a", "b", "c"]


def test_parse_json_object_handles_fenced_json_with_extra_text():
    raw = """
I am returning the analysis below.
```json
{
  "top_mistakes": [],
  "action_plan": [],
  "next_game_focus": ["x", "y", "z"]
}
```
Thanks.
"""
    parsed = coach_llm._parse_json_object(raw)
    assert parsed is not None
    assert parsed["next_game_focus"] == ["x", "y", "z"]


def test_prompt_templates_allow_literal_braces():
    _, human_prompt = coach_llm._load_prompt_templates()
    assert "{{ ... }}" in human_prompt
    assert "{payload_json}" in human_prompt
