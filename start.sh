#!/bin/bash
# 知识库服务启动脚本（FastAPI + uvicorn）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/AiClaudeProject/projects/knowledge-base/src/server"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
