#!/bin/bash
# 构建前端并启动 FastAPI 服务
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 构建前端..."
cd "$SCRIPT_DIR/src/web"
npx vite build

echo "🚀 启动后端..."
cd "$SCRIPT_DIR"
python3 src/server/main.py
