# Chess Analyzer

Chess.com-style analyzer with a JavaScript frontend and Python FastAPI backend using Stockfish.

## Features
- PGN/FEN import.
- Chess.com archive import by username.
- Move-by-move analysis with best move, PV, classification, and suggestion.
- Batched move prefetch endpoint for lower latency/cost with optional LLM-first analysis.
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
- Backend root (`http://localhost:9001`) redirects to the frontend URL by default.

Docker frontend uses Vite proxy to backend service (`/api` -> `http://backend:9001`),
so browser requests do not depend on `localhost:9001`.

## Production Deploy (Vercel frontend + Render backend)

### 1) Deploy backend on Render (Docker)
This repo is already ready for Render Docker deploys:
- Dockerfile: `backend/Dockerfile`
- Health endpoint: `/health`
- Render `PORT` binding is supported by the container command.

Render service settings:
- Service type: `Web Service`
- Runtime: `Docker`
- Root directory: `backend`
- Dockerfile path: `./Dockerfile`
- Health check path: `/health`

Set backend environment variables in Render:
- Required:
  - `CORS_ORIGIN=https://<your-frontend-domain>`
  - `FRONTEND_URL=https://<your-frontend-domain>`
- Recommended engine defaults:
  - `STOCKFISH_THREADS=2`
  - `STOCKFISH_POOL_SIZE=4`
  - `STOCKFISH_HASH_MB=512`
  - `ANALYSIS_TIMEOUT_SECONDS=45`
- Optional coach LLM:
  - `COACH_USE_LLM=true`
  - `GOOGLE_APPLICATION_CREDENTIALS_B64=<base64-service-account-json>`
  - `GOOGLE_CLOUD_PROJECT=<project-id>`
  - `GOOGLE_CLOUD_LOCATION=us-central1`
  - `COACH_LLM_MODEL=gemini-2.0-flash-001`
  - `COACH_LLM_MAX_OUTPUT_TOKENS=2048`
  - Optional move LLM:
  - `MOVE_USE_LLM=true`
  - `MOVE_LLM_MODEL=gemini-2.5-flash`
  - `MOVE_LLM_MAX_OUTPUT_TOKENS=2048`
  - `MOVE_LLM_TIMEOUT_SECONDS=30`
  - `MOVE_BATCH_CHUNK_SIZE=4`
  - `MOVE_LLM_MAX_CONCURRENCY=2`
  - `MOVE_LLM_PROMPT_VERSION=v1`

Use `backend/.env.example` as a reference; keep real secrets only in Render env vars.

### 2) Deploy frontend on Vercel
Vercel project settings:
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`

Set frontend environment variable in Vercel:
- `VITE_API_BASE=https://<your-render-service>.onrender.com`
- `VITE_PREFETCH_BATCH_SIZE=4`
- `VITE_PREFETCH_CONCURRENCY=2`

Use `frontend/.env.example` as a reference.

### 3) Post-deploy checks
- Backend health: `https://<your-render-service>.onrender.com/health`
- Frontend loads from Vercel and can:
  - import PGN
  - run move analysis
  - start and poll full analysis

### Performance Profile
Current Docker defaults are tuned for responsive interactive analysis and good throughput:
- `STOCKFISH_THREADS=2`
- `STOCKFISH_POOL_SIZE=4` (persistent parallel engine workers)
- `STOCKFISH_HASH_MB=512`
- Interactive defaults: `movetime=2000ms`, `depth=20`, `multipv=1`
- Deep full-analysis defaults remain around `depth=24` and `movetime=5000ms`

Frontend behavior:
- First launch defaults to `realtime` mode.
- Last selected mode is persisted in `localStorage["analysis.mode"]` (`realtime|deep`).
- Background move prefetch runs in balanced chunks (`4` plies, `2` in-flight requests by default).
- Interactive analysis reuses matching in-flight prefetch requests to avoid duplicate API calls.

Speed notes:
- Move analysis computes "before" and "after" positions in parallel for lower per-request latency.
- Increase throughput by raising `STOCKFISH_POOL_SIZE` and lowering `STOCKFISH_THREADS` per worker.
- Increase per-request strength by lowering `STOCKFISH_POOL_SIZE` and raising `STOCKFISH_THREADS`.
- For this project, start with total engine threads near CPU core count:
  - Throughput-biased: `THREADS=1-2`, higher `POOL_SIZE`
  - Strength-biased: `THREADS=3-4`, lower `POOL_SIZE`

Optional stronger endgames:
- Mount Syzygy tablebases and set:
  - `STOCKFISH_SYZYGY_PATH=/path/to/syzygy`
  - `STOCKFISH_SYZYGY_PROBE_LIMIT=6`

### Chess.com Corporate Network Setup
If Chess.com import fails with one of these:
- `CERTIFICATE_VERIFY_FAILED`
- `Blocked by network web filter`
- `Web Filter Violation` / `Trend Micro`

your backend container is behind corporate TLS interception and/or outbound filtering.

Recommended secure setup:
1. Get your corporate proxy URL and corporate CA bundle (PEM) from IT.
2. Place the CA bundle file under `backend/certs/` (for example: `backend/certs/corporate-ca.pem`).
3. Export proxy variables before starting Docker:
   - `export HTTPS_PROXY=http://proxy.company:port`
   - `export HTTP_PROXY=http://proxy.company:port`
   - `export NO_PROXY=localhost,127.0.0.1,backend`
4. Set backend TLS settings in `backend/.env`:
   - `CHESSCOM_SSL_VERIFY=true`
   - `CHESSCOM_CA_BUNDLE=/app/certs/corporate-ca.pem`
5. Recreate containers:
   - `docker compose up -d --build --force-recreate`

Diagnostics (from project root):
```bash
docker compose exec -T backend python -m app.tools.chesscom_probe --username hikaru
```

Expected healthy probe:
- `http_status=200`
- non-zero `archives_count`

Notes:
- Docker compose now passes both uppercase and lowercase proxy env vars to backend.
- `CHESSCOM_SSL_VERIFY=false` is available only as a temporary fallback and is not recommended.
- If proxy is configured and requests still fail with `403`, ask IT to allow `api.chess.com` through the proxy.


### Coach LLM (LangChain + Google Vertex AI)
To enable LLM-generated coaching insights, add these values in a backend `.env` file:

```env
COACH_USE_LLM=true
GOOGLE_APPLICATION_CREDENTIALS_B64=<base64-encoded-service-account-json>
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
COACH_LLM_MODEL=gemini-2.0-flash-001
COACH_LLM_MAX_OUTPUT_TOKENS=2048
```

The backend decodes `GOOGLE_APPLICATION_CREDENTIALS_B64` at runtime, writes it to a temporary JSON credentials file, and uses LangChain's `ChatVertexAI` client for coach report generation.
Coach prompt templates are editable in:
- `backend/app/prompts/coach_system_prompt.md`
- `backend/app/prompts/coach_human_prompt.md`

If these variables are missing or the LLM response is invalid, the coach endpoint returns an error (LLM-only mode).

## API Endpoints
- `POST /api/games/import/pgn`
- `POST /api/games/import/chesscom`
- `POST /api/games/import/chesscom/select`
- `POST /api/analysis/move`
- `POST /api/analysis/moves-batch`
- `POST /api/analysis/fen`
- `POST /api/analysis/full`
- `GET /api/analysis/full/{job_id}`
- `POST /api/coach/analyze`
- `DELETE /api/sessions/{game_id}`
