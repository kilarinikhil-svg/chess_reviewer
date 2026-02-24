import os
import shutil
from pydantic import BaseModel


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_stockfish_path() -> str:
    explicit = os.getenv("STOCKFISH_PATH")
    if explicit:
        return explicit

    candidates = [
        "stockfish",
        "/usr/games/stockfish",
        "/usr/local/bin/stockfish",
        "/opt/homebrew/bin/stockfish",
    ]
    for candidate in candidates:
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return "stockfish"


def default_stockfish_threads() -> int:
    cpu = os.cpu_count() or 1
    return max(1, min(4, cpu))


def default_stockfish_pool_size() -> int:
    cpu = os.cpu_count() or 1
    threads = int(os.getenv("STOCKFISH_THREADS", str(default_stockfish_threads())))
    # Keep total engine threads roughly bounded by available CPU.
    return max(1, min(8, cpu // max(1, threads)))


class Settings(BaseModel):
    stockfish_path: str = resolve_stockfish_path()
    stockfish_threads: int = int(os.getenv("STOCKFISH_THREADS", str(default_stockfish_threads())))
    stockfish_pool_size: int = int(os.getenv("STOCKFISH_POOL_SIZE", str(default_stockfish_pool_size())))
    stockfish_hash_mb: int = int(os.getenv("STOCKFISH_HASH_MB", "512"))
    stockfish_syzygy_path: str | None = os.getenv("STOCKFISH_SYZYGY_PATH")
    stockfish_syzygy_probe_limit: int = int(os.getenv("STOCKFISH_SYZYGY_PROBE_LIMIT", "6"))
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 6)))
    deep_job_workers: int = int(os.getenv("DEEP_JOB_WORKERS", "1"))
    analysis_timeout_seconds: int = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "45"))
    cors_origin: str = os.getenv("CORS_ORIGIN", "*")
    chesscom_ssl_verify: bool = env_bool("CHESSCOM_SSL_VERIFY", True)
    chesscom_ca_bundle: str | None = os.getenv("CHESSCOM_CA_BUNDLE")
    chesscom_user_agent: str = os.getenv(
        "CHESSCOM_USER_AGENT",
        "chess-analyzer/0.1 (+https://github.com/your-org/chess-analyzer)",
    )


settings = Settings()
