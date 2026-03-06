FROM python:3.12-slim

RUN set -eux; \
    apt-get update -o Acquire::Retries=5 -o APT::Update::Error-Mode=any \
    && apt-get install -y --no-install-recommends ca-certificates stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
ENV PYTHONPATH=/app
ENV STOCKFISH_PATH=/usr/games/stockfish

EXPOSE 9001
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9001}"]
