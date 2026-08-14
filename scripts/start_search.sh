#!/bin/bash
# 启动 产品知识库 · 智能检索 服务
cd "$(dirname "$0")/.."
python3 AiClaudeProject/projects/knowledge-base/shared-modules/智能检索工具/search_server.py 8765