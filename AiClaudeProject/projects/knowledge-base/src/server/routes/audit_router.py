"""审计日志路由"""
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import verify_token, require_admin
from repository import get_repo

router = APIRouter(tags=["审计日志"])
logger = logging.getLogger("audit")


@router.get("/audit/logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    username: str = Query("", description="按用户名筛选"),
    action_prefix: str = Query("", description="按操作前缀筛选（如 'user.', 'doc.', 'faq.'）"),
    user: str = Depends(require_admin),
):
    """查询审计日志（仅管理员）"""
    repo = get_repo()
    conditions = ["1=1"]
    params = {}

    if username:
        conditions.append("username = :u")
        params["u"] = username
    if action_prefix:
        conditions.append("action LIKE :a")
        params["a"] = f"{action_prefix}%"

    where = " AND ".join(conditions)

    # 总数
    count_row = repo._execute_one(f"SELECT count(*) as cnt FROM audit_logs WHERE {where}", params)
    total = count_row["cnt"] if count_row else 0

    # 分页查询
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset
    rows = repo._execute(
        f"SELECT id, username, action, target, detail, ip, created_at "
        f"FROM audit_logs WHERE {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
        params)

    logs = [{
        "id": r["id"],
        "username": r["username"],
        "action": r["action"],
        "target": r["target"],
        "detail": r["detail"],
        "ip": r["ip"],
        "created_at": str(r["created_at"]) if r["created_at"] else "",
    } for r in rows]

    return {"logs": logs, "total": total, "page": page, "page_size": page_size}
