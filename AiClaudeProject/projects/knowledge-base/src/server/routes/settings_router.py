"""系统配置路由"""
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import verify_token, require_admin
from repository import get_repo

router = APIRouter(tags=["系统配置"])
logger = logging.getLogger("settings")


class SettingsUpdateBody(BaseModel):
    settings: dict  # {key: value, ...}


# 默认配置种子
DEFAULT_SETTINGS = {
    "sso_enabled": {"value": "1", "description": "SSO 开关（1=启用，0=禁用）", "category": "sso"},
    "confluence_base_url": {"value": "https://cf.cai-inc.com", "description": "Confluence 服务地址", "category": "sso"},
    "maintenance_mode": {"value": "0", "description": "维护模式（1=开启，前端显示维护提示）", "category": "general"},
    "default_dept": {"value": "数智财务组", "description": "FAQ/文档上传默认部门", "category": "general"},
    "default_module": {"value": "浙里报", "description": "FAQ/文档上传默认模块", "category": "general"},
    "search_result_limit": {"value": "10", "description": "搜索默认返回条数", "category": "search"},
    "ai_env_fallback": {"value": "1", "description": "AI 环境回退开关（1=未配置AI的用户可用服务器共享密钥，0=必须自行配置）", "category": "search"},
    "password_min_length": {"value": "6", "description": "密码最小长度", "category": "security"},
}


def _ensure_settings_seed():
    """首次启动时写入默认配置（已存在则跳过）"""
    repo = get_repo()
    for key, cfg in DEFAULT_SETTINGS.items():
        exists = repo._execute_one("SELECT key FROM system_settings WHERE key = ?", (key,))
        if not exists:
            repo._execute_write(
                "INSERT INTO system_settings (key, value, description, category) VALUES (?, ?, ?, ?)",
                (key, cfg["value"], cfg["description"], cfg.get("category", "general")))


@router.get("/settings")
async def get_settings(user: str = Depends(verify_token)):
    """获取所有系统配置（管理员可见全部，普通用户可见部分）"""
    _ensure_settings_seed()
    repo = get_repo()
    rows = repo._execute("SELECT key, value, description, category, updated_by, updated_at FROM system_settings ORDER BY category, key")

    is_admin_user = False
    try:
        from service import ai_config
        is_admin_user = ai_config.is_admin(user)
    except:
        pass

    settings = []
    for r in rows:
        # 非管理员只看 general 类别
        if not is_admin_user and r["category"] not in ("general",):
            continue
        settings.append({
            "key": r["key"],
            "value": r["value"],
            "description": r["description"] or "",
            "category": r["category"] or "general",
            "updated_by": r["updated_by"] or "",
            "updated_at": str(r["updated_at"]) if r["updated_at"] else "",
        })

    return {"settings": settings}


@router.put("/settings")
async def update_settings(body: SettingsUpdateBody, user: str = Depends(require_admin)):
    """批量更新系统配置（仅管理员）"""
    if not body.settings:
        return JSONResponse({"error": "无变更"}, status_code=422)

    repo = get_repo()
    updated = 0
    for key, value in body.settings.items():
        # 安全检查：只允许更新已存在的配置项
        exists = repo._execute_one("SELECT key FROM system_settings WHERE key = ?", (key,))
        if not exists:
            continue
        repo._execute_write(
            "UPDATE system_settings SET value = ?, updated_by = ?, updated_at = NOW() WHERE key = ?",
            (str(value), user, key))
        updated += 1

    if updated > 0:
        from service.audit import log_action
        log_action(user, "config.system_update", detail=json.dumps(body.settings, ensure_ascii=False))

    return {"ok": True, "updated": updated}


def get_system_setting(key: str, default: str = "") -> str:
    """运行时读取配置：DB > 环境变量 > 默认值"""
    try:
        repo = get_repo()
        row = repo._execute_one("SELECT value FROM system_settings WHERE key = ?", (key,))
        if row and row["value"]:
            return row["value"]
    except:
        pass
    import os
    env_val = os.getenv(key.upper(), "")
    return env_val or default
