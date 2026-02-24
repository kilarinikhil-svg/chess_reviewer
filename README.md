# Chess Analyzer

Chess.com-style analyzer with a JavaScript frontend and Python FastAPI backend using Stockfish.

## Features
- PGN/FEN import.
- Chess.com archive import by username.
- Move-by-move analysis with best move, PV, classification, and suggestion.
- Deep full-game analysis job with progress polling.
- Ephemeral session model (no login).

## Tech
- Frontend: React + Vite, `chess.js`, `react-chessboard`
- Backend: FastAPI, `python-chess`, Stockfish UCI

## Local Run (without Docker)
### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Install stockfish if missing:
# Fedora/RHEL: sudo dnf install stockfish
# Ubuntu/Debian: sudo apt-get install stockfish
# macOS (brew): brew install stockfish
#
# Verify path:
# which stockfish || ls /usr/games/stockfish
#
# Set explicit path if needed:
# export STOCKFISH_PATH=/usr/games/stockfish
uvicorn app.main:app --reload --port 9001
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Set API base if needed:
```bash
export VITE_API_BASE=http://localhost:9001
```

Optional (recommended for local dev): use Vite proxy instead of CORS/API base:
```bash
export VITE_PROXY_TARGET=http://localhost:9001
unset VITE_API_BASE
```

## Docker Run
```bash
docker compose up --build
```

Docker URLs:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:9001/health`

Docker frontend uses Vite proxy to backend service (`/api` -> `http://backend:9001`),
so browser requests do not depend on `localhost:9001`.

### Strong Engine Profile
Current Docker defaults are tuned for stronger analysis:
- `STOCKFISH_THREADS=4`
- `STOCKFISH_POOL_SIZE=2` (persistent parallel engine workers)
- `STOCKFISH_HASH_MB=512`
- Deep analysis defaults around `depth=24` and `movetime=5000ms`

Speed notes:
- Deep analysis now analyzes positions in parallel across a persistent Stockfish worker pool.
- Increase throughput by raising `STOCKFISH_POOL_SIZE` and lowering `STOCKFISH_THREADS` per worker.
- Increase per-move strength by lowering `STOCKFISH_POOL_SIZE` and raising `STOCKFISH_THREADS`.

Optional stronger endgames:
- Mount Syzygy tablebases and set:
  - `STOCKFISH_SYZYGY_PATH=/path/to/syzygy`
  - `STOCKFISH_SYZYGY_PROBE_LIMIT=6`

### Chess.com SSL Notes
If your environment uses a self-signed corporate TLS proxy, Chess.com import can fail with
`CERTIFICATE_VERIFY_FAILED`.

Options:
- Set `CHESSCOM_SSL_VERIFY=false` (less secure, but simplest for restricted networks).
- Prefer secure mode by mounting your corporate CA cert and setting:
  - `CHESSCOM_CA_BUNDLE=/path/to/ca-bundle.pem`
  - Keep `CHESSCOM_SSL_VERIFY=true`
- If Chess.com responds with `403 Forbidden`, set/override a browser-like user agent:
  - `CHESSCOM_USER_AGENT="Mozilla/5.0 ..."`
- If response body contains `Web Filter Violation` / `Trend Micro`, this is a network policy block.
  Configure proxy vars before running Docker:
  - `export HTTPS_PROXY=http://proxy.company:port`
  - `export HTTP_PROXY=http://proxy.company:port`
  - `export NO_PROXY=localhost,127.0.0.1,backend`


### Coach LLM (LangChain + Google Vertex AI)
To enable LLM-generated coaching insights, add these values in a backend `.env` file:

```env
COACH_USE_LLM=true
GOOGLE_APPLICATION_CREDENTIALS_B64=<base64-encoded-service-account-json>
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
COACH_LLM_MODEL=gemini-2.0-flash-001
```

The backend decodes `GOOGLE_APPLICATION_CREDENTIALS_B64` at runtime, writes it to a temporary JSON credentials file, and uses LangChain's `ChatVertexAI` client for coach report generation.

If these variables are missing, the coach endpoint falls back to deterministic heuristic analysis.

## API Endpoints
- `POST /api/games/import/pgn`
- `POST /api/games/import/chesscom`
- `POST /api/games/import/chesscom/select`
- `POST /api/analysis/move`
- `POST /api/analysis/full`
- `GET /api/analysis/full/{job_id}`
- `POST /api/coach/analyze`
- `DELETE /api/sessions/{game_id}`
