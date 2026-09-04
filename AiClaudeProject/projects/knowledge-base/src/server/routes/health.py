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
    from repository import get_repo
    repo = get_repo()
    try:
        cols = repo.check_table_columns("faqs")
        for c in ("related", "tickets"):
            if c not in cols:
                issues.append(f"faqs 缺列 {c}")
    except Exception as e:
        issues.append(f"faqs 列校验失败: {e}")
    try:
        idx = repo.check_table_indexes("keyword_mappings", "uq_km_kw_mod_active")
        if not idx:
            issues.append("keyword_mappings 缺部分唯一索引 uq_km_kw_mod_active")
        idx2 = repo.check_table_indexes("document_departments", "uq_dd_path_dept")
        if not idx2:
            issues.append("document_departments 缺唯一索引 uq_dd_path_dept")
    except Exception:
        pass  # SQLite 无 pg_indexes 视图，跳过
    return issues


@router.get("/health")
async def health(user: str = Depends(verify_token)):
    """健康检查：数据源、引擎、Schema 契约、写失败计数、内存与DB漂移检测"""
    import main
    db_kind = "PostgreSQL" if "postgresql" in os.getenv("DATABASE_URL_SYNC", "") else "SQLite/回退"
    counts = {}
    drift = {"ok": True, "warnings": []}
    try:
        from repository import get_repo
        repo = get_repo()
        for table in ("faqs", "documents", "reports", "keywords_v2", "keyword_mappings"):
            counts[table] = repo.get_table_count(table)

        # 漂移检测：内存数据 vs DB 活跃数据
        # 原理：内存引擎加载时从 DB 读取 is_deleted=FALSE 的数据，
        # 若外部直接改了 DB（绕过 API），内存仍持有旧数据，产生漂移。
        # 修复方法：调用 /api/rebuild 重建索引。
        if main.search_engine is not None:
            try:
                # FAQ：内存 faq_docs vs DB faqs (is_deleted=FALSE)
                db_faq_count = repo._execute_one(
                    "SELECT count(*) as cnt FROM faqs WHERE is_deleted = FALSE"
                )["cnt"]
                mem_faq_count = len(main.search_engine.faq_docs)
                if mem_faq_count != db_faq_count:
                    drift["ok"] = False
                    drift["warnings"].append(
                        f"FAQ 漂移：内存 {mem_faq_count} vs DB {db_faq_count}，"
                        f"可能外部修改了数据库，请调用 /api/rebuild 重建索引"
                    )

                # 文档：kb_docs 中知识文档部分 vs DB documents (is_deleted=FALSE)
                # kb_docs = 知识文档 + FAQ文档 + 报表文档，只比对知识文档
                db_doc_count = repo._execute_one(
                    "SELECT count(*) as cnt FROM documents WHERE is_deleted = FALSE"
                )["cnt"]
                mem_doc_count = len([d for d in main.search_engine.kb_docs
                                     if not d.get("path", "").startswith("data/faq/")
                                     and not d.get("path", "").startswith("data/reports/")])
                if mem_doc_count != db_doc_count:
                    drift["ok"] = False
                    drift["warnings"].append(
                        f"文档漂移：内存 {mem_doc_count} vs DB {db_doc_count}，"
                        f"可能外部修改了数据库，请调用 /api/rebuild 重建索引"
                    )

                # 关键词映射：内存 keyword_map 的 key 数 vs DB 有活跃映射的关键词词数
                # （keywords_v2 中无 mapping 的孤立词不在内存 keyword_map 中，属正常）
                db_kw_count = repo._execute_one(
                    "SELECT count(DISTINCT kw.keyword) as cnt "
                    "FROM keywords_v2 kw JOIN keyword_mappings km ON km.keyword_id = kw.id "
                    "WHERE kw.is_deleted = FALSE AND km.is_deleted = FALSE"
                )["cnt"]
                mem_kw_count = len(main.search_engine.keyword_map)
                if mem_kw_count != db_kw_count:
                    drift["ok"] = False
                    drift["warnings"].append(
                        f"关键词漂移：内存 {mem_kw_count} vs DB {db_kw_count}，"
                        f"可能外部修改了数据库，请调用 /api/rebuild 重建索引"
                    )

                # 模块：内存 module_map vs DB modules (is_deleted=FALSE)
                db_mod_count = repo._execute_one(
                    "SELECT count(*) as cnt FROM modules WHERE is_deleted = FALSE"
                )["cnt"]
                mem_mod_count = len(main.search_engine.module_map)
                if mem_mod_count != db_mod_count:
                    drift["ok"] = False
                    drift["warnings"].append(
                        f"模块漂移：内存 {mem_mod_count} vs DB {db_mod_count}，"
                        f"可能外部修改了数据库，请调用 /api/rebuild 重建索引"
                    )
            except Exception as e:
                drift["ok"] = False
                drift["warnings"].append(f"漂移检测失败: {e}")
    except Exception:
        counts = {"error": "数据库不可达"}

    return {
        "ok": True,
        "engine_ready": main.search_engine is not None,
        "db_type": db_kind,
        "schema_issues": schema_check(),
        "write_failures": WRITE_FAILURES,
        "counts": counts,
        "drift": drift,
    }
