#!/bin/bash
cd "$(dirname "$0")"
python3 AiClaudeProject/projects/knowledge-base/shared-modules/智能检索工具/search_server.py 8765
