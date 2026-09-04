"""学习服务层：知识提取、自动学习、审核沉淀、过期清理

自学习闭环：
  1. 用户咨询 → AI 回答 → 自动提取知识 → 学习候选池
  2. 用户 👍 反馈 → 触发学习建议 → 学习候选池
  3. 管理员审核 → 通过 → 自动创建 FAQ → 重建索引
"""
import json
import logging
import datetime
from typing import Optional

from service import claude_stream as claude_service
from service import ai_config as ai_cfg

logger = logging.getLogger("learning")

# 知识提取 Prompt
LEARNING_EXTRACT_PROMPT = """你是一个知识提取专家。请从以下问答中提炼出一条可复用的知识条目。

用户问题：{query}
AI回答：{answer}

请输出JSON格式（不要输出其他内容）：
{{
  "title": "简明标题（10-30字，可作为FAQ标题）",
  "summary": "知识摘要（100-300字，去除对话语气，保留核心事实和步骤）",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "dept": "最可能的部门（数智财务组/免疫规划组/电子档案组/数字化支撑组）",
  "module": "最可能的业务模块",
  "worth_learning": true
}}

要求：
1. summary 要独立可读，去掉"你好""根据您的描述""希望对你有帮助"等对话套话
2. keywords 提取3-8个核心词，便于后续检索
3. 如果回答是闲聊、寒暄、无实质业务内容，设置 worth_learning 为 false
4. 只输出 JSON，不要任何解释文字"""


async def extract_knowledge(query: str, answer: str, user: str = "") -> Optional[dict]:
    """从问答中提取结构化知识（调用 AI）

    Returns:
        提取结果 dict（title/summary/keywords/dept/module/worth_learning），
        如果无可用 AI 或提取失败返回 None
    """
    cfg = ai_cfg.resolve_ai_config(user or "")
    if not cfg:
        logger.warning("extract_knowledge: 无可用 AI 配置，跳过提取")
        return None

    prompt = LEARNING_EXTRACT_PROMPT.format(query=query[:500], answer=answer[:2000])
    system = "你是一个精确的知识提取工具，只输出 JSON，不输出任何其他内容。"

    # 收集流式输出
    full_text = ""
    try:
        async for chunk in claude_service.sse_generate_cfg(
            cfg, system=system,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        ):
            if chunk.startswith("data: "):
                data = chunk[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                    if parsed.get("error"):
                        logger.warning(f"extract_knowledge AI 错误: {parsed}")
                        return None
                    if parsed.get("text"):
                        full_text += parsed["text"]
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        logger.warning(f"extract_knowledge 异常: {e}")
        return None

    if not full_text.strip():
        return None

    # 解析 AI 输出的 JSON
    result = _parse_extract_json(full_text)
    if not result:
        logger.warning(f"extract_knowledge JSON 解析失败: {full_text[:200]}")
        return None

    if not result.get("worth_learning", True):
        return None

    return result


def _parse_extract_json(text: str) -> Optional[dict]:
    """从 AI 输出中提取 JSON（容错：处理 markdown 代码块包裹等）"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 JSON 部分
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def save_candidate(repo, query: str, answer: str, source: str = "ai_answer",
                   summary: str = "", dept: str = "", module: str = "",
                   keywords: list = None, feedback_id: int = 0,
                   session_id: str = "", created_by: str = "") -> dict:
    """保存学习候选到数据库

    Returns:
        {"ok": True, "id": int} 或 {"ok": False, "error": str}
    """
    try:
        kw_json = json.dumps(keywords or [], ensure_ascii=False)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            result = conn.execute(sql_text("""
                INSERT INTO learning_candidates
                    (source, query, answer, summary, dept, module, keywords,
                     status, feedback_id, session_id, created_by, create_time, update_time)
                VALUES
                    (:source, :query, :answer, :summary, :dept, :module, :keywords,
                     0, :feedback_id, :session_id, :created_by, :now, :now)
            """), {
                "source": source, "query": query[:2000], "answer": answer[:5000],
                "summary": summary[:1000], "dept": dept[:100], "module": module[:200],
                "keywords": kw_json, "feedback_id": feedback_id,
                "session_id": session_id[:50], "created_by": created_by[:100],
                "now": now,
            })
            conn.commit()
            candidate_id = result.lastrowid
        return {"ok": True, "id": candidate_id}
    except Exception as e:
        logger.error(f"save_candidate 失败: {e}")
        return {"ok": False, "error": str(e)}


def list_candidates(repo, status: int = None, page: int = 1, page_size: int = 20) -> dict:
    """列出学习候选（支持按状态过滤、分页）

    Returns:
        {"candidates": [...], "total": int, "page": int}
    """
    try:
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            where = "1=1"
            params = {}
            if status is not None:
                where += " AND status = :status"
                params["status"] = status

            # 总数
            count_row = conn.execute(
                sql_text(f"SELECT COUNT(*) FROM learning_candidates WHERE {where}"),
                params
            ).fetchone()
            total = count_row[0] if count_row else 0

            # 分页查询
            offset = (page - 1) * page_size
            rows = conn.execute(
                sql_text(f"""
                    SELECT id, source, query, answer, summary, dept, module, keywords,
                           status, review_note, reviewed_by, reviewed_at,
                           feedback_id, session_id, faq_code, created_by,
                           create_time, update_time
                    FROM learning_candidates
                    WHERE {where}
                    ORDER BY
                        CASE status WHEN 0 THEN 0 ELSE 1 END,
                        create_time DESC
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": page_size, "offset": offset}
            ).fetchall()

            candidates = []
            for row in rows:
                kw_raw = row[7] or "[]"
                try:
                    kw_list = json.loads(kw_raw) if isinstance(kw_raw, str) else kw_raw
                except (json.JSONDecodeError, TypeError):
                    kw_list = []
                candidates.append({
                    "id": row[0],
                    "source": row[1],
                    "query": row[2],
                    "answer": row[3],
                    "summary": row[4],
                    "dept": row[5],
                    "module": row[6],
                    "keywords": kw_list,
                    "status": row[8],
                    "review_note": row[9],
                    "reviewed_by": row[10],
                    "reviewed_at": row[11],
                    "feedback_id": row[12],
                    "session_id": row[13],
                    "faq_code": row[14],
                    "created_by": row[15],
                    "create_time": row[16],
                    "update_time": row[17],
                })

        return {"candidates": candidates, "total": total, "page": page}
    except Exception as e:
        logger.error(f"list_candidates 失败: {e}")
        return {"candidates": [], "total": 0, "page": page}


def approve_candidate(repo, candidate_id: int, reviewer: str = "",
                      edits: dict = None) -> dict:
    """审核通过学习候选 → 自动创建 FAQ

    Args:
        edits: 可选的修改内容，如 {"summary": "...", "dept": "...", "keywords": [...]}}

    Returns:
        {"ok": True, "faq_id": str, "faq_path": str} 或 {"ok": False, "error": str}
    """
    try:
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            row = conn.execute(
                sql_text("SELECT * FROM learning_candidates WHERE id = :id"),
                {"id": candidate_id}
            ).fetchone()

            if not row:
                return {"ok": False, "error": "候选不存在"}

            # 读取字段（按列序）
            cols = ["id", "source", "query", "answer", "summary", "dept", "module",
                    "keywords", "status", "review_note", "reviewed_by", "reviewed_at",
                    "feedback_id", "session_id", "faq_code", "created_by",
                    "create_time", "update_time"]
            candidate = dict(zip(cols, row))

            if candidate["status"] != 0:
                return {"ok": False, "error": f"候选状态非待审核（status={candidate['status']}）"}

            # 应用编辑
            title = candidate["query"][:200]  # 默认标题取问题
            summary = candidate["summary"] or candidate["answer"]
            dept = candidate["dept"]
            module = candidate["module"]
            kw_raw = candidate["keywords"] or "[]"
            try:
                keywords = json.loads(kw_raw) if isinstance(kw_raw, str) else kw_raw
            except (json.JSONDecodeError, TypeError):
                keywords = []

            if edits:
                if edits.get("title"):
                    title = edits["title"][:200]
                if edits.get("summary"):
                    summary = edits["summary"]
                if edits.get("dept"):
                    dept = edits["dept"]
                if edits.get("module"):
                    module = edits["module"]
                if edits.get("keywords"):
                    keywords = edits["keywords"]

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 更新候选状态为已通过
            conn.execute(sql_text("""
                UPDATE learning_candidates
                SET status = 1, reviewed_by = :reviewer, reviewed_at = :now,
                    update_time = :now, summary = :summary, dept = :dept,
                    module = :module, keywords = :keywords
                WHERE id = :id
            """), {
                "reviewer": reviewer, "now": now, "id": candidate_id,
                "summary": summary, "dept": dept, "module": module,
                "keywords": json.dumps(keywords, ensure_ascii=False),
            })
            conn.commit()

        # 复用 FAQ 保存逻辑创建 FAQ 条目
        from routes.faq import save_faq as faq_save_endpoint, _reload_after_faq_change, DEPT_CODES, STATUS_MAP
        from repository.base import FAQ as FAQModel
        from repository.dept_mapping import get_dept_path, get_submodule_path
        from config import settings

        dept_path = get_dept_path(dept) or "other"
        sub_path = get_submodule_path(module) if module else ""
        faq_dir = settings.DATA_DIR / "faq" / dept_path / sub_path
        faq_dir.mkdir(parents=True, exist_ok=True)

        # 生成 FAQ 编码
        dept_code = DEPT_CODES.get(dept, "XX")
        mod_code = (module[:3] if module else "XXX")
        existing = list(faq_dir.glob("*.md"))
        faq_code = f"FAQ-{dept_code}-{mod_code}-{len(existing) + 1:03d}"

        # 解析 dept_id / module_id
        resolved_d_id = repo.resolve_dept_id(dept) if dept else 0
        resolved_m_id = repo.resolve_module_id(module, dept_name=dept) if module else None

        # 关键词提取（如果为空则自动提取）
        if not keywords and summary:
            try:
                from keyword_extractor import get_extractor, build_extractor_idf
                extractor = get_extractor()
                if not extractor._built:
                    build_extractor_idf(str(settings.DATA_DIR))
                keywords = extractor.extract(summary, top_k=10)
            except Exception:
                keywords = []

        today = datetime.date.today().isoformat()
        file_content = f"""---
id: {faq_code}
title: {title}
keywords: {json.dumps(keywords, ensure_ascii=False)}
module: {module}
dept: {dept}
sub_module: {module}
scene: ""
status: active
version_from: "自学习沉淀"
created: {today}
reviewed: {today}
related: []
tickets: []
---

# {title}

{summary}
"""
        file_path = faq_dir / f"{faq_code}.md"
        file_path.write_text(file_content, encoding="utf-8")
        rel_path = str(file_path.relative_to(settings.PROJECT_DIR))

        # 写 faqs 表
        faq_obj = FAQModel(
            faq_code=faq_code, faq_title=title, faq_question=title, faq_answer=summary,
            content=file_content, path=rel_path, tags=keywords, dept=dept,
            dept_id=resolved_d_id or 0, sub_module=module, module=module,
            module_id=resolved_m_id or 0, scene="",
            status=1, sort_num=0, view_count=0,
            source_file_name=f"{faq_code}.md", version_from="自学习沉淀",
            related=[], tickets=[],
            update_time=now, is_deleted=0,
        )
        try:
            repo.save_faq(faq_obj, write_file=False)
        except Exception as e:
            logger.warning(f"approve_candidate FAQ 写库失败（文件已写入）: {e}")

        # 关键词双表写入
        try:
            m_id = resolved_m_id or 0
            d_id = resolved_d_id or 0
            for kw in keywords:
                repo.add_keyword(kw, m_id, d_id, dept, kb_path=rel_path)
        except Exception:
            pass

        # 更新候选的 faq_code
        try:
            with repo.engine.connect() as conn:
                from sqlalchemy import text as sql_text
                conn.execute(sql_text("""
                    UPDATE learning_candidates SET faq_code = :faq_code WHERE id = :id
                """), {"faq_code": faq_code, "id": candidate_id})
                conn.commit()
        except Exception:
            pass

        # 重建搜索索引
        _reload_after_faq_change()

        # 审计日志
        from service.audit import log_action
        log_action(reviewer, "learning.approve", target=str(candidate_id),
                   detail=f"faq_code={faq_code}")

        return {"ok": True, "faq_id": faq_code, "faq_path": rel_path}

    except Exception as e:
        logger.error(f"approve_candidate 失败: {e}")
        return {"ok": False, "error": str(e)}


def reject_candidate(repo, candidate_id: int, reviewer: str = "",
                     note: str = "") -> dict:
    """审核拒绝学习候选"""
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            result = conn.execute(sql_text("""
                UPDATE learning_candidates
                SET status = 2, reviewed_by = :reviewer, reviewed_at = :now,
                    review_note = :note, update_time = :now
                WHERE id = :id AND status = 0
            """), {"reviewer": reviewer, "now": now, "note": note, "id": candidate_id})
            conn.commit()
            if result.rowcount == 0:
                return {"ok": False, "error": "候选不存在或非待审核状态"}
        from service.audit import log_action
        log_action(reviewer, "learning.reject", target=str(candidate_id))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_learning_stats(repo) -> dict:
    """学习中心统计数据"""
    try:
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            row = conn.execute(sql_text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 0) AS pending,
                    COUNT(*) FILTER (WHERE status = 1) AS approved,
                    COUNT(*) FILTER (WHERE status = 2) AS rejected,
                    COUNT(*) FILTER (WHERE status = 3) AS expired,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 1
                        AND create_time >= CURRENT_TIMESTAMP - INTERVAL '7 days') AS week_approved
                FROM learning_candidates
            """)).fetchone()

            if not row:
                return {"pending": 0, "approved": 0, "rejected": 0,
                        "expired": 0, "total": 0, "week_approved": 0}

            return {
                "pending": row[0] or 0,
                "approved": row[1] or 0,
                "rejected": row[2] or 0,
                "expired": row[3] or 0,
                "total": row[4] or 0,
                "week_approved": row[5] or 0,
            }
    except Exception:
        # SQLite 不支持 FILTER 语法，用兼容写法
        try:
            with repo.engine.connect() as conn:
                from sqlalchemy import text as sql_text
                pending = conn.execute(sql_text(
                    "SELECT COUNT(*) FROM learning_candidates WHERE status = 0"
                )).scalar() or 0
                approved = conn.execute(sql_text(
                    "SELECT COUNT(*) FROM learning_candidates WHERE status = 1"
                )).scalar() or 0
                rejected = conn.execute(sql_text(
                    "SELECT COUNT(*) FROM learning_candidates WHERE status = 2"
                )).scalar() or 0
                expired = conn.execute(sql_text(
                    "SELECT COUNT(*) FROM learning_candidates WHERE status = 3"
                )).scalar() or 0
                total = conn.execute(sql_text(
                    "SELECT COUNT(*) FROM learning_candidates"
                )).scalar() or 0
                return {
                    "pending": pending, "approved": approved,
                    "rejected": rejected, "expired": expired,
                    "total": total, "week_approved": 0,
                }
        except Exception as e:
            logger.error(f"get_learning_stats 失败: {e}")
            return {"pending": 0, "approved": 0, "rejected": 0,
                    "expired": 0, "total": 0, "week_approved": 0}


def expire_old_candidates(repo, days: int = 30) -> int:
    """将超期未审核的候选标记为过期

    Returns:
        过期条数
    """
    try:
        with repo.engine.connect() as conn:
            from sqlalchemy import text as sql_text
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime(
                "%Y-%m-%d %H:%M:%S")
            result = conn.execute(sql_text("""
                UPDATE learning_candidates
                SET status = 3, update_time = :now
                WHERE status = 0 AND create_time < :cutoff
            """), {"now": now, "cutoff": cutoff})
            conn.commit()
            expired = result.rowcount
            if expired > 0:
                logger.info(f"已过期 {expired} 条学习候选（>{days}天未审核）")
            return expired
    except Exception as e:
        logger.error(f"expire_old_candidates 失败: {e}")
        return 0
