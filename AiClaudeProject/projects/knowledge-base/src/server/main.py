"""FastAPI 应用入口"""
import sys, os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 确保项目路径在 sys.path 中
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from database import init_db
from config import settings

# 全局搜索引擎实例（延迟加载）
search_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global search_engine
    # 启动时：初始化数据库（PostgreSQL 不可用时跳过）
    if settings.use_postgres:
        try:
            await init_db()
        except Exception as e:
            print(f"  ⚠️  PostgreSQL 不可用，使用 SQLite 回退: {e}")
    # 加载搜索引擎（始终可用）
    from search_engine import SearchEngine
    search_engine = SearchEngine()
    search_engine.load_all()
    yield
    # 关闭时清理


app = FastAPI(
    title="智能知识库",
    version="2.0",
    description="企业级产品知识管理 + 智能检索系统",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from routes import search, documents, faq, dashboard, keywords as kw_routes, auth_router

app.include_router(search.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(faq.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(kw_routes.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")

# 静态文件（前端）
static_dir = HERE.parent.parent / "runtime" / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


# 兼容旧路由（/api/document/update 等，委托给 search_server.py 的 handler）
# 这些路由在 routes/ 中已重新实现，旧代码保留在 search_server.py 中作为参考