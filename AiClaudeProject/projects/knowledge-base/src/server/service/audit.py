"""操作审计日志服务

记录系统中所有管理操作（用户创建/删除、文档上传/删除、FAQ 编辑、索引重建等）。
写失败不阻断业务，仅告警。
"""
import json
import logging

from repository import get_repo

logger = logging.getLogger("audit")


def log_action(username: str, action: str, target: str = "", detail: str = "", ip: str = ""):
    """记录审计日志（非阻塞，写失败不影响业务）

    Args:
        username: 操作人
        action: 操作类型，如 'user.create', 'doc.delete', 'faq.save', 'system.rebuild'
        target: 操作对象标识（用户名/文档路径/FAQ code 等）
        detail: 变更详情（JSON 字符串或纯文本）
        ip: 客户端 IP
    """
    try:
        repo = get_repo()
        repo._execute_write(
            "INSERT INTO audit_logs (username, action, target, detail, ip) VALUES (?, ?, ?, ?, ?)",
            (username, action, target, detail, ip))
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")


def log_action_dict(username: str, action: str, target: str = "", detail: dict = None, ip: str = ""):
    """记录审计日志（detail 为 dict，自动转 JSON）"""
    detail_json = json.dumps(detail, ensure_ascii=False) if detail else ""
    log_action(username, action, target, detail_json, ip)
