"""健康检查与 Schema 契约校验"""
import os
from fastapi import APIRouter
from auth import verify_token
from fastapi import Depends

router = APIRouter(tags=["健康检查"])

# 关键写路径失败计数（由各路由在写库失败时递增）
WRITE_FAILURES = {
    "faq_save": 0,
    "faq_delete": 0,
    "keyword_write": 0,
    "doc_dept_link": 0,
    "search_log": 0,
}

# 部门路径缓存失效标记（文档变更时置 True，menu/documents 会重建）
ENGINE_GENERATION = {"value": 0}


def record_write_failure(kind: str):
    WRITE_FAILURES[kind] = WRITE_FAILURES.get(kind, 0) + 1


def schema_check() -> list:
    """校验关键表结构契约（列存在性、唯一索引），漂移即返回告警条目"""
    issues = []
    from repository import DBRepository
    repo = DBRepository()
    try:
        cols = [r["column_name"] for r in repo._execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'faqs'")]
        for c in ("related", "tickets"):
            if c not in cols:
                issues.append(f"faqs 缺列 {c}")
    except Exception as e:
        issues.append(f"faqs 列校验失败: {e}")
    try:
        idx = repo._execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'keyword_mappings' AND indexname = 'uq_km_kw_mod_active'")
        if not idx:
            issues.append("keyword_mappings 缺部分唯一索引 uq_km_kw_mod_active")
        idx2 = repo._execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'document_departments' AND indexname = 'uq_dd_path_dept'")
        if not idx2:
            issues.append("document_departments 缺唯一索引 uq_dd_path_dept")
    except Exception:
        pass  # SQLite 无 pg_indexes 视图，跳过
    return issues


@router.get("/health")
async def health(user: str = Depends(verify_token)):
    """健康检查：数据源、引擎、Schema 契约、写失败计数"""
    import main
    db_kind = "PostgreSQL" if "postgresql" in os.getenv("DATABASE_URL_SYNC", "") else "SQLite/回退"
    counts = {}
    try:
        from repository import DBRepository
        repo = DBRepository()
        for table in ("faqs", "documents", "reports", "keywords_v2", "keyword_mappings"):
            row = repo._execute_one(f"SELECT COUNT(*) AS c FROM {table}")
            counts[table] = row["c"] if row else None
    except Exception:
        counts = {"error": "数据库不可达"}

    return {
        "ok": True,
        "engine_ready": main.search_engine is not None,
        "db_type": db_kind,
        "schema_issues": schema_check(),
        "write_failures": WRITE_FAILURES,
        "counts": counts,
    }
