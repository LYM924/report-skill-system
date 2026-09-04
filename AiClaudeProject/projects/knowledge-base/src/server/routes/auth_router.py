"""认证路由"""
import logging
import secrets

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

from auth import create_token, verify_token, check_credentials
from config import settings
from repository import get_repo
from service import ai_config
from service.audit import log_action

router = APIRouter(tags=["认证"])
logger = logging.getLogger("auth")


class LoginBody(BaseModel):
    username: str
    password: str


class SSOConfluenceBody(BaseModel):
    username: str
    display_name: str = ""
    email: str = ""


@router.post("/auth/login")
async def login(body: LoginBody):
    """登录：优先校验用户表（多用户各自账号），回退环境 ADMIN_USER/ADMIN_PASS"""
    username = body.username.strip()
    if not username or not body.password:
        return JSONResponse({"error": "用户名和密码不能为空"}, status_code=401)
    # 1. 用户表校验
    row = ai_config.get_user(username)
    if row and ai_config.verify_password(body.password, row["password_hash"]):
        token = create_token(username)
        log_action(username, "auth.login")
        return {"token": token, "token_type": "bearer", "role": row["role"]}
    # 2. 环境管理员账号回退
    if check_credentials(username, body.password):
        token = create_token(username)
        log_action(username, "auth.login")
        return {"token": token, "token_type": "bearer", "role": "admin"}
    return JSONResponse({"error": "用户名或密码错误"}, status_code=401)


@router.get("/auth/me")
async def me(user: str = Depends(verify_token)):
    """当前用户信息（含角色，前端用于菜单显隐）"""
    role = "admin" if ai_config.is_admin(user) else "user"
    return {"user": user or "anonymous", "role": role}


# ─── Confluence SSO ─────────────────────────────────────────────────────

@router.get("/auth/sso/status")
async def sso_status():
    """返回 SSO 配置状态（前端用于判断是否显示 SSO 登录按钮）"""
    return {
        "enabled": settings.SSO_ENABLED,
        "confluence_url": settings.CONFLUENCE_BASE_URL if settings.SSO_ENABLED else "",
    }


@router.get("/auth/sso/confluence-proxy")
async def sso_confluence_proxy(request: Request):
    """后端代理 Confluence 用户 API：转发浏览器 Cookie 检测登录状态。

    仅在同域部署（cf.cai-inc.com/kb/）下生效：
    - 同域 → 浏览器自动带 Confluence Cookie → 代理能识别用户 → 自动登录
    - 跨域 → Cookie 不会带到 KB → 返回 anonymous → 需走手动 SSO 流程
    """
    if not settings.SSO_ENABLED:
        return JSONResponse({"error": "SSO 未启用"}, status_code=403)

    cookie_header = request.headers.get("cookie", "")
    headers = {}
    if cookie_header:
        headers["Cookie"] = cookie_header

    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            resp = await client.get(
                f"{settings.CONFLUENCE_BASE_URL}/rest/api/user/current",
                headers=headers,
            )
            data = resp.json()
    except Exception as e:
        logger.warning(f"Confluence 代理请求失败: {e}")
        return {"type": "error", "error": f"Confluence 不可达: {e}"}

    if data.get("type") == "known" and data.get("username"):
        return {
            "type": "known",
            "username": data["username"],
            "display_name": data.get("displayName", data["username"]),
            "email": data.get("email", f"{data['username']}@cai-inc.com"),
        }
    return {"type": "anonymous"}


@router.post("/auth/sso/confluence")
async def sso_confluence(body: SSOConfluenceBody):
    """Confluence SSO 登录：接收 Confluence 用户名，查找/创建 KB 用户，返回 JWT。

    两种调用场景：
    1. 代理检测到 Confluence 已登录 → 前端自动调用 → 无感登录
    2. 手动输入 Confluence 用户名 → 前端手动调用 → 快捷登录（首次自动创建账号）
    """
    if not settings.SSO_ENABLED:
        return JSONResponse({"error": "SSO 未启用"}, status_code=403)

    username = body.username.strip()
    if not username:
        return JSONResponse({"error": "缺少 Confluence 用户名"}, status_code=422)

    # 查找已有用户
    existing = ai_config.get_user(username)
    if existing:
        token = create_token(username)
        role = existing.get("role", "user")
        logger.info(f"SSO 登录（已有用户）: {username}")
        log_action(username, "auth.sso_login")
        return {"token": token, "token_type": "bearer", "role": role, "sso": True}

    # 检查是否有软删除的同名用户 → 恢复而非新建
    repo = get_repo()
    deleted = repo._execute_one(
        "SELECT id FROM users WHERE username = :u AND is_deleted = TRUE", {"u": username})
    if deleted:
        repo._execute_write(
            "UPDATE users SET is_deleted = FALSE, password_hash = :ph, "
            "role = 'user', updated_at = NOW() WHERE id = :id",
            {"ph": ai_config.hash_password(secrets.token_hex(16)), "id": deleted["id"]})
        token = create_token(username)
        logger.info(f"SSO 恢复已删除用户: {username}")
        log_action(username, "auth.sso_login")
        return {"token": token, "token_type": "bearer", "role": "user", "sso": True}

    # 首次 SSO → 自动创建账号
    random_pass = secrets.token_hex(16)
    result = ai_config.create_user(username, random_pass, "user")
    if result.get("error"):
        existing2 = ai_config.get_user(username)
        if existing2:
            token = create_token(username)
            return {"token": token, "token_type": "bearer", "role": "user", "sso": True}
        return JSONResponse({"error": result["error"]}, status_code=500)

    token = create_token(username)
    logger.info(f"SSO 自动创建用户: {username} (displayName={body.display_name}, email={body.email})")
    log_action(username, "auth.sso_login")
    return {"token": token, "token_type": "bearer", "role": "user", "sso": True}


@router.get("/auth/sso/confluence-callback")
async def sso_confluence_callback():
    """Confluence SSO 回调页。

    用户在 Confluence 登录后，Confluence 通过 os_destination 跳到此页面。
    页面自动：1. 调代理检测 Confluence 用户 → 2. 换 JWT → 3. 写 localStorage
    → 4. 通知主页面（BroadcastChannel）→ 5. 关闭自身。

    跨域时代理返回 anonymous → 显示用户名确认表单作为回退。
    """
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SSO 登录中</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; }
  .card { background: #fff; border-radius: 12px; padding: 36px 32px; box-shadow: 0 1px 4px rgba(0,0,0,.08); text-align: center; max-width: 380px; width: 90%; }
  h2 { color: #1a1a2e; margin: 0 0 10px; font-size: 18px; }
  p { color: #606266; font-size: 14px; line-height: 1.5; margin: 0 0 16px; }
  .spinner { width: 28px; height: 28px; border: 3px solid #e2e8f0; border-top-color: #0D9488; border-radius: 50%; animation: spin .7s linear infinite; margin: 0 auto 14px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .ok { color: #0D9488; }
  .err { color: #e53e3e; }
  input { width: 100%; height: 40px; border-radius: 8px; border: 1px solid #d9d9d9; padding: 0 12px; font-size: 14px; outline: none; }
  input:focus { border-color: #0D9488; box-shadow: 0 0 0 2px rgba(13,148,136,.15); }
  button { width: 100%; height: 40px; border-radius: 8px; border: none; background: linear-gradient(135deg,#0D9488,#2DD4BF); color: #fff; font-size: 15px; cursor: pointer; margin-top: 10px; }
  button:hover { opacity: .9; }
  .fade { opacity: 0; transition: opacity .3s; }
  .fade.show { opacity: 1; }
</style>
</head>
<body>
<div class="card" id="app">
  <div class="spinner" id="spinner"></div>
  <h2 id="title">SSO 登录验证中</h2>
  <p id="msg">正在检测 Confluence 登录状态...</p>
  <div id="fallback" class="fade" style="display:none">
    <input id="usernameInput" placeholder="Confluence 用户名" />
    <button id="manualBtn">确认登录</button>
  </div>
</div>
<script>
const title = document.getElementById('title');
const msg = document.getElementById('msg');
const spinner = document.getElementById('spinner');
const fallback = document.getElementById('fallback');
const usernameInput = document.getElementById('usernameInput');
const manualBtn = document.getElementById('manualBtn');

/** 通知主页面登录状态已变化，然后关闭自身 */
function notifyAndClose() {
  try {
    const bc = new BroadcastChannel('kb-auth');
    bc.postMessage('auth-changed');
    bc.close();
  } catch(e) {}
  // 兼容不支持 BroadcastChannel 的浏览器
  try { window.opener?.postMessage('kb-auth-changed', '*'); } catch(e) {}
  setTimeout(() => window.close(), 800);
  // 如果 window.close() 被浏览器拦截，2秒后显示手动关闭提示
  setTimeout(() => {
    title.textContent = '登录成功';
    msg.textContent = '已自动登录，可关闭此页面';
    msg.className = 'ok';
    spinner.style.display = 'none';
  }, 1500);
}

/** 用用户名完成登录 */
async function doLogin(username, displayName) {
  try {
    const resp = await fetch('/api/auth/sso/confluence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, display_name: displayName || username }),
    });
    const data = await resp.json();
    if (data.token) {
      localStorage.setItem('kb_token', data.token);
      title.textContent = '登录成功';
      msg.textContent = '欢迎 ' + (displayName || username) + '，正在返回知识库...';
      msg.className = 'ok';
      spinner.style.display = 'none';
      notifyAndClose();
      return true;
    }
    msg.textContent = '登录失败: ' + (data.error || '未知错误');
    msg.className = 'err';
    return false;
  } catch(e) {
    msg.textContent = '网络错误: ' + e.message;
    msg.className = 'err';
    return false;
  }
}

(async () => {
  try {
    // 1. 调后端代理检测 Confluence 登录状态
    const resp = await fetch('/api/auth/sso/confluence-proxy', { credentials: 'include' });
    const data = await resp.json();

    if (data.type === 'known' && data.username) {
      // 2a. 代理成功 → 自动登录
      msg.textContent = '检测到 Confluence 用户: ' + data.display_name;
      await doLogin(data.username, data.display_name);
    } else if (data.type === 'anonymous') {
      // 2b. 跨域部署 → 代理拿不到 → 显示用户名确认
      spinner.style.display = 'none';
      title.textContent = '请确认用户名';
      msg.textContent = 'Confluence 已登录，请输入用户名完成知识库登录';
      fallback.style.display = 'block';
      setTimeout(() => fallback.classList.add('show'), 50);
      setTimeout(() => usernameInput.focus(), 200);
    } else {
      spinner.style.display = 'none';
      title.textContent = '检测失败';
      msg.className = 'err';
      msg.textContent = data.error || 'Confluence 不可达';
    }
  } catch(e) {
    spinner.style.display = 'none';
    title.textContent = '网络错误';
    msg.className = 'err';
    msg.textContent = e.message;
  }
})();

// 手动输入用户名
manualBtn.addEventListener('click', async () => {
  const u = usernameInput.value.trim();
  if (!u) { usernameInput.focus(); return; }
  manualBtn.disabled = true;
  manualBtn.textContent = '登录中...';
  spinner.style.display = 'block';
  title.textContent = 'SSO 登录中';
  msg.className = '';
  msg.textContent = '正在登录...';
  fallback.style.display = 'none';
  await doLogin(u, u);
});
usernameInput.addEventListener('keydown', e => { if (e.key === 'Enter') manualBtn.click(); });
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
