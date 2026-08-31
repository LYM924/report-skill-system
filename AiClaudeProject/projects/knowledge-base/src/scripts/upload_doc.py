#!/usr/bin/env python3
"""终端命令行文档上传脚本（与 Web 上传共用统一模板）

用法:
    python3 upload_doc.py --file /path/to/文档.md --dept 电子卖场 --module 合同
    python3 upload_doc.py --file 文档.md --dept 数智财务组 --module 浙里报 --server http://localhost:8000

认证（优先级从高到低）:
    1. --token 参数
    2. AUTH_TOKEN 环境变量
    3. 用 .env 的 JWT_SECRET_KEY 自签 JWT（与 auth.verify_token 一致）

说明:
    脚本只做「读文件 + POST /api/document/upload」，模板重排、关键词提取、
    documents 表落库、部门关联、索引更新全部由服务端统一处理，
    与 Web 页面上传走完全相同的代码路径，保证模板一致。
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # knowledge-base/


def _load_env_value(key: str) -> str:
    """读取 .env 中指定键（不覆盖已有环境变量）"""
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        return ""
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key and k.strip() not in os.environ:
                return v.strip().strip('"').strip("'")
    return ""


def _mint_jwt() -> str:
    """用 .env 的 JWT_SECRET_KEY 自签 HS256 JWT（与 auth.verify_token 校验一致）"""
    secret = _load_env_value("JWT_SECRET_KEY") or "dev-secret-key"
    b64 = lambda d: base64.urlsafe_b64encode(d).rstrip(b"=")  # noqa: E731
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({"sub": "upload_doc_cli", "exp": 9999999999}).encode())
    sig = b64(hmac.new(secret.encode(), header + b"." + payload, hashlib.sha256).digest())
    return (header + b"." + payload + b"." + sig).decode()


def upload(server: str, token: str, file_path: Path, dept: str, module: str,
           filename: str = "") -> dict:
    """POST /api/document/upload（JSON body），返回服务端响应"""
    if not file_path.exists():
        return {"error": f"文件不存在: {file_path}"}
    content = file_path.read_text(encoding="utf-8")
    body = {
        "filename": filename or file_path.name,
        "content": content,
        "dept": dept,
        "module": module,
    }
    req = urllib.request.Request(
        f"{server.rstrip('/')}/api/document/upload",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"}
    except Exception as e:
        return {"error": f"请求失败: {e}"}


def main():
    parser = argparse.ArgumentParser(description="知识库文档上传（统一模板，与 Web 上传同路径）")
    parser.add_argument("--file", required=True, help="本地 Markdown 文件路径")
    parser.add_argument("--dept", default="", help="所属部门（默认 数智财务组）")
    parser.add_argument("--module", default="", help="产品模块（默认 浙里报）")
    parser.add_argument("--filename", default="", help="入库文件名（默认取原文件名）")
    parser.add_argument("--server", default=os.environ.get("KB_SERVER", "http://localhost:8000"),
                        help="知识库服务地址（默认 http://localhost:8000）")
    parser.add_argument("--token", default="", help="鉴权 Token（默认取 AUTH_TOKEN 环境变量或 .env 自签）")
    args = parser.parse_args()

    token = args.token or os.environ.get("AUTH_TOKEN", "") or _mint_jwt()
    result = upload(args.server, token, Path(args.file).resolve(),
                    args.dept, args.module, args.filename)
    if "error" in result:
        print(f"✗ {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ 上传成功: {result.get('path')}")
    print(f"  文件名: {result.get('filename')}")
    print(f"  部门: {result.get('dept')}  模块: {result.get('module')}")


if __name__ == "__main__":
    main()
