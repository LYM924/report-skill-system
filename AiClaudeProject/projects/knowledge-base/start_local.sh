#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 产品知识库系统 — 本地一键启动脚本
# 支持：macOS / Linux（需 Python 3.9+）
# 无需 Docker / PostgreSQL / Redis，使用 SQLite 本地模式
# ═══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
echo_info() { echo -e "${YELLOW}[→]${NC} $1"; }
echo_err()  { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "══════════════════════════════════════════"
echo "  产品知识库系统 — 本地启动"
echo "══════════════════════════════════════════"
echo ""

# ──────────────── 1. 检查 Python ────────────────
if ! command -v python3 &>/dev/null; then
    echo_err "未找到 python3，请先安装 Python 3.9+"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo_ok "Python $PY_VERSION"

# ──────────────── 2. 创建虚拟环境 ────────────────
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo_info "创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo_ok "虚拟环境已创建"
fi

source "$VENV_DIR/bin/activate"
echo_ok "虚拟环境已激活"

# ──────────────── 3. 安装依赖 ────────────────
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo_info "安装 Python 依赖（首次启动，约 1-3 分钟）..."
    pip install --upgrade pip -q
    pip install -r src/server/requirements.txt -q 2>/dev/null || {
        # 如果完整依赖安装失败，安装核心最小集（不含向量模型，减小安装包）
        echo_info "完整依赖安装失败，安装核心最小集..."
        pip install fastapi==0.115.0 uvicorn[standard]==0.30.0 \
                    sqlalchemy==2.0.35 pydantic==2.9.0 pydantic-settings==2.5.0 \
                    jieba==0.42.1 pypinyin==0.51.0 numpy==1.26.0 \
                    python-jose[cryptography]==3.3.0 passlib[bcrypt]==1.7.4 \
                    python-multipart==0.0.9 httpx==0.27.2 -q
    }
    echo_ok "依赖安装完成"
else
    echo_ok "依赖已安装"
fi

# ──────────────── 4. 配置本地环境 ────────────────
# 关键：在 .env 中把 DATABASE_URL_SYNC 设为 SQLite，
# 因为 config.py 的 _load_env() 会用 .env 非空值覆盖环境变量

if [ ! -f "$SCRIPT_DIR/.env" ] || ! grep -q "LOCAL_MODE" "$SCRIPT_DIR/.env" 2>/dev/null; then
    echo_info "生成本地模式配置..."
    # 备份已有 .env
    if [ -f "$SCRIPT_DIR/.env" ]; then
        cp "$SCRIPT_DIR/.env" "$SCRIPT_DIR/.env.backup"
        echo_ok "已备份原 .env → .env.backup"
    fi
    cat > "$SCRIPT_DIR/.env" << 'ENVEOF'
# 本地模式配置（start_local.sh 自动生成）
# 如需切回 PostgreSQL 模式，恢复 .env.backup 或重新配置

# 标记：本地模式
LOCAL_MODE=true

# 数据库（SQLite 本地模式，无需安装 PostgreSQL）
DATABASE_URL=sqlite:///./runtime/knowledge.db
DATABASE_URL_SYNC=sqlite:///./runtime/knowledge.db

# 存储
STORAGE_BACKEND=local

# JWT（本地使用，安全要求低）
JWT_SECRET_KEY=local-dev-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# 管理员账号
ADMIN_USER=admin
ADMIN_PASS=admin123

# AI API（留空 = AI 功能不可用，可在 Web 配置中心单独配置）
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_BASE_URL=
ENVEOF
    echo_ok "本地配置已生成 (.env)"
else
    echo_ok "本地配置已存在 (.env)"
fi

# ──────────────── 5. 构建前端（如需要） ────────────────
if [ ! -f "$SCRIPT_DIR/runtime/static/index.html" ]; then
    if command -v node &>/dev/null && command -v npx &>/dev/null; then
        echo_info "构建前端..."
        cd src/web
        if [ ! -d "node_modules" ]; then
            npm install --silent 2>/dev/null
        fi
        npx vite build 2>/dev/null
        cd "$SCRIPT_DIR"
        echo_ok "前端构建完成"
    else
        echo_info "未安装 Node.js，跳过前端构建"
        echo_info "  安装方法: macOS → brew install node | 其他 → https://nodejs.org/"
        echo_info "  安装后重新运行此脚本即可"
    fi
else
    echo_ok "前端已构建"
fi

# ──────────────── 6. 确保 runtime 目录 ────────────────
mkdir -p "$SCRIPT_DIR/runtime/cache" "$SCRIPT_DIR/runtime/logs" "$SCRIPT_DIR/runtime/static"

# ──────────────── 7. 启动服务 ────────────────
echo ""
echo "══════════════════════════════════════════"
echo_ok "服务启动中..."
echo ""
echo "  📖 访问地址: http://localhost:8000"
echo "  👤 默认账号: admin / admin123"
echo ""
echo "  ⏹ 停止服务: 按 Ctrl+C"
echo "══════════════════════════════════════════"
echo ""

# 尝试自动打开浏览器
if command -v open &>/dev/null; then
    # macOS
    (sleep 5 && open http://localhost:8000) &
elif command -v xdg-open &>/dev/null; then
    # Linux
    (sleep 5 && xdg-open http://localhost:8000) &
fi

cd "$SCRIPT_DIR/src/server"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
