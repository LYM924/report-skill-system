"""FastAPI 应用入口"""
import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 确保项目路径在 sys.path 中
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import settings

# 全局搜索引擎实例（延迟加载）
search_engine = None


def _setup_logging():
    """统一日志：runtime/logs/kb_server.log（RotatingFileHandler 5MB×5）"""
    log_dir = settings.RUNTIME_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "kb_server.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    logging.getLogger("uvicorn.access").addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global search_engine
    _setup_logging()
    # Schema 由 config/migrations/ 管理（psql 应用），不再用 create_all（避免重建已删除的旧表）
    # 启动时校验 Schema 契约
    try:
        from routes.health import schema_check
        issues = schema_check()
        if issues:
            logging.getLogger("main").warning(f"Schema 契约校验失败: {issues}")
        else:
            logging.getLogger("main").info("Schema 契约校验通过")
    except Exception as e:
        logging.getLogger("main").warning(f"Schema 校验不可用: {e}")
    # 加载搜索引擎（启动即装载，避免首个请求冷启动缺加载）
    from search_engine import SearchEngine
    search_engine = SearchEngine()
    search_engine.load_all()
    logging.getLogger("main").info("搜索引擎装载完成")
    yield


app = FastAPI(
    title="智能知识库",
    version="3.0",
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
from routes import search, documents, faq, dashboard, keywords as kw_routes, auth_router, health

app.include_router(search.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(faq.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(kw_routes.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(health.router, prefix="/api")

# 静态文件（前端构建产物 runtime/static）
static_dir = HERE.parent.parent / "runtime" / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
