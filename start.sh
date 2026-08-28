#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/AiClaudeProject/projects/knowledge-base/src/server/search_server.py" 8000
