#!/bin/bash
cd "$(dirname "$0")"
python3 AiClaudeProject/projects/knowledge-base/src/server/search_server.py 8000
