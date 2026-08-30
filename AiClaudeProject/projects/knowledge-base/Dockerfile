FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/server/ ./src/server/
COPY runtime/static/ ./runtime/static/
COPY data/ ./data/

# 单 worker：搜索引擎（BM25/FAISS）与 AI 会话 SESSION_STORE 均为进程内状态，
# 多 worker 会导致会话串号与索引重复加载；单用户内部工具 1 worker 足够
CMD ["gunicorn", "src.server.main:app", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "600"]
