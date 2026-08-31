#!/bin/bash
# ============================================================================
# smoke_test.sh — 知识库全端点冒烟测试（每改必跑）
# 用法:
#   ./scripts/smoke_test.sh                        # 默认 http://localhost:8000，只读检查
#   ./scripts/smoke_test.sh http://localhost:8001
#   ./scripts/smoke_test.sh localhost:8000 --write # 含安全写测试（关键词 CRUD 用一次性词）
#   AUTH_TOKEN=xxx ./scripts/smoke_test.sh         # Phase 2 后带鉴权跑
# ============================================================================
BASE="${1:-http://localhost:8000}"
WRITE_MODE=0
if [ "${1:-}" = "--write" ] || [ "${2:-}" = "--write" ]; then WRITE_MODE=1; fi

PASS=0; FAIL=0; FAILED_NAMES=()
AUTH_HEADER=()
[ -n "$AUTH_TOKEN" ] && AUTH_HEADER=(-H "Authorization: Bearer $AUTH_TOKEN")

# req <名称> <method> <path> [curl额外参数...] -- <python断言>  (stdin=响应体)
# path 会自动做 URL 百分号编码（保留 / ? = & 等结构字符），避免中文/空格乱码
enc() {
  python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1], safe='/?=&:.-_~%'))" "$1"
}

req() {
  local name="$1" method="$2" path="$3"; shift 3
  local assert="" args=() a
  while [ $# -gt 0 ]; do
    if [ "$1" = "--" ]; then assert="$2"; shift 2
    else args+=("$1"); shift; fi
  done
  path="$(enc "$path")"
  local code
  code=$(curl -s -o /tmp/smoke_body -w "%{http_code}" -X "$method" "${AUTH_HEADER[@]}" "${args[@]}" "$BASE$path")
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ] && python3 -c "$assert" < /tmp/smoke_body 2>/dev/null; then
    PASS=$((PASS+1)); echo "  ✅ $name"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$name"); echo "  ❌ $name (HTTP $code 或断言失败)"
  fi
}

echo "== 冒烟测试 $BASE =="

echo "-- 搜索类 --"
req "GET /api/search"         GET "/api/search?q=报销" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and ('results' in d or 'error' in d),d"
req "GET /api/suggest"        GET "/api/suggest?q=报销" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'suggestions' in d,d"
req "GET /api/search/related" GET "/api/search/related?q=报销" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'related' in d,d"
req "GET /api/faq/similar"    GET "/api/faq/similar?keywords=报销" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"

echo "-- FAQ 类 --"
req "GET /api/faq"          GET "/api/faq" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'faqs' in d,d"
req "GET /api/faq/suggest"  GET "/api/faq/suggest?title=报销" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'dept' in d,d"

echo "-- 文档类 --"
req "GET /api/documents" GET "/api/documents" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'documents' in d,d"
DOC_PATH=$(curl -s "${AUTH_HEADER[@]}" "$BASE/api/documents" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['documents'][0]['path'] if d.get('documents') else '')" 2>/dev/null)
if [ -n "$DOC_PATH" ]; then
  DOC_PATH="$(enc "$DOC_PATH")"
  req "GET /api/document" GET "/api/document?path=$DOC_PATH" \
    -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'content' in d,d"
else
  FAIL=$((FAIL+1)); FAILED_NAMES+=("GET /api/document(无文档可测)"); echo "  ❌ GET /api/document (无文档可测)"
fi

echo "-- 部门/菜单类 --"
req "GET /api/departments/tree"    GET "/api/departments/tree" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'tree' in d,d"
req "GET /api/departments/options" GET "/api/departments/options" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'options' in d,d"
req "GET /api/menu" GET "/api/menu" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"

echo "-- 统计/日志类 --"
req "GET /api/dashboard" GET "/api/dashboard" -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"
req "GET /api/stats"     GET "/api/stats"     -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"
req "GET /api/trends"    GET "/api/trends"    -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"
req "GET /api/hotwords"  GET "/api/hotwords"  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'hotwords' in d,d"
req "GET /api/recent"    GET "/api/recent"    -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"
req "GET /api/logs?lines=5" GET "/api/logs?lines=5" -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict),d"
req "GET /api/reports"   GET "/api/reports"   -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'reports' in d,d"

echo "-- 关键词类 --"
req "GET /api/keywords" GET "/api/keywords?page_size=5" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'keywords' in d,d"

echo "-- 系统管理类 --"
req "GET /api/auth/me" GET "/api/auth/me" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'role' in d,d"
req "GET /api/config/ai" GET "/api/config/ai" \
  -- "import sys,json;d=json.load(sys.stdin);assert isinstance(d,dict) and 'model' in d,d"

if [ "$WRITE_MODE" = "1" ]; then
  echo "-- 写测试（一次性数据）--"
  KW="smoke_$(date +%s)"
  req "POST /api/keywords" POST "/api/keywords" \
    -H "Content-Type: application/json" -d "{\"keyword\":\"$KW\",\"module\":\"浙里报\",\"dept\":\"数智财务组\"}" \
    -- "import sys,json;d=json.load(sys.stdin);assert d.get('ok') or d.get('keyword_id') or d.get('mapping_id'),d"
  MAPPING_ID=$(python3 -c "import json;d=json.load(open('/tmp/smoke_body'));print(d.get('mapping_id',''))" 2>/dev/null)
  if [ -n "$MAPPING_ID" ] && [ "$MAPPING_ID" != "None" ]; then
    req "PUT /api/keywords" PUT "/api/keywords" \
      -H "Content-Type: application/json" -d "{\"mapping_id\":$MAPPING_ID,\"dept\":\"数智财务组\"}" \
      -- "import sys,json;d=json.load(sys.stdin);assert d.get('ok'),d"
    req "DELETE /api/keywords" DELETE "/api/keywords" \
      -H "Content-Type: application/json" -d "{\"mapping_id\":$MAPPING_ID}" \
      -- "import sys,json;d=json.load(sys.stdin);assert d.get('ok'),d"
  else
    echo "  ⚠️ POST 未返回 mapping_id，跳过 PUT/DELETE"
  fi

  if [ -n "$AUTH_TOKEN" ]; then
    echo "-- 上传格式回归（一次性数据）--"
    KB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    UP_NAME="smoke_格式验证_$(date +%s).md"
    python3 - "$UP_NAME" <<'PYEOF'
import json, sys
payload = {
    "filename": sys.argv[1],
    "content": "# 格式验证\n\n## 需求分析\n\n现状：<br>1、测试<br>2、测试\n\n## 需求场景\n\n\\-Tab导航：测试；\n",
    "dept": "电子卖场",
    "module": "合同",
}
open('/tmp/smoke_upload.json', 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False))
PYEOF
    UP_RESP=$(curl -s -X POST "${AUTH_HEADER[@]}" -H "Content-Type: application/json" \
      --data-binary @/tmp/smoke_upload.json "$BASE/api/document/upload")
    UP_PATH=$(echo "$UP_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('path',''))" 2>/dev/null)
    if [ -n "$UP_PATH" ] && [ -f "$KB_DIR/$UP_PATH" ]; then
      if python3 - "$KB_DIR/$UP_PATH" <<'PYEOF'
import sys
text = open(sys.argv[1], encoding='utf-8').read()
assert '版本迭代时间线【总目录】' in text, '总目录缺失'
assert '<br>' not in text, '残留 <br>'
assert '\\-' not in text, '残留 \\-'
assert '## 双向链接' in text, '双向链接缺失'
print('格式断言通过')
PYEOF
      then
        PASS=$((PASS+1)); echo "  ✅ 上传格式回归（总目录/<br>/\\-/双向链接）"
      else
        FAIL=$((FAIL+1)); FAILED_NAMES+=("上传格式回归"); echo "  ❌ 上传格式回归（断言失败）"
      fi
      # 清理一次性数据（文件 + documents 行 + 关键词映射 + 孤儿关键词）
      python3 - "$KB_DIR" "$UP_PATH" <<'PYEOF'
import sys
from pathlib import Path
kb_dir, p = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(kb_dir / 'src' / 'server'))
db_ok = False
try:
    from repository.db_repo import DBRepository
    repo = DBRepository()
    repo._execute_write('DELETE FROM keyword_mappings WHERE kb_path = ?', (p,))
    repo._execute_write('DELETE FROM keywords_v2 WHERE id NOT IN (SELECT DISTINCT keyword_id FROM keyword_mappings)')
    repo._execute_write('DELETE FROM document_departments WHERE document_path = ?', (p,))
    repo._execute_write('DELETE FROM documents WHERE path = ?', (p,))
    db_ok = True
except Exception:
    pass
(kb_dir / p).unlink(missing_ok=True)
print(f'清理: {p} (DB={db_ok})')
PYEOF
    else
      FAIL=$((FAIL+1)); FAILED_NAMES+=("上传格式回归"); echo "  ❌ 上传格式回归 (上传失败: $UP_RESP)"
    fi
  fi
fi

echo ""
echo "结果: $PASS 通过 / $FAIL 失败"
if [ $FAIL -gt 0 ]; then printf '失败项: %s\n' "${FAILED_NAMES[@]}"; fi
exit $FAIL
