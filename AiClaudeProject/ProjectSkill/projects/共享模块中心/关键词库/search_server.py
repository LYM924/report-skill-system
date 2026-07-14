#!/usr/bin/env python3
"""产品知识库搜索服务 - 启动本地 Web 搜索界面"""
import json, os, sys, logging
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote as url_quote

logging.getLogger().setLevel(logging.WARNING)
import jieba
jieba.setLogLevel(logging.WARNING)

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parents[3]  # AiClaudeProject/
sys.path.insert(0, str(HERE))
from search_engine import SearchEngine

engine = None

def get_engine():
    global engine
    if engine is None:
        engine = SearchEngine()
        if not engine.load_cache():
            engine._load_synonyms()
            engine._load_keyword_index()
            engine._load_module_files()
            engine._load_knowledge_base()
            engine._load_report_data()
            engine.save_cache()
    return engine


class SearchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "static"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            top = int(params.get("top", ["15"])[0])

            if not query:
                self._json({"error": "请提供查询参数 q"})
                return

            eng = get_engine()
            result = eng.search(query, top=top)
            self._json(result)
        elif parsed.path == "/api/rebuild":
            global engine
            engine = SearchEngine()
            engine._load_synonyms()
            engine._load_keyword_index()
            engine._load_module_files()
            engine._load_knowledge_base()
            engine._load_report_data()
            engine.save_cache()
            self._json({"ok": True, "message": "索引已重建"})
        elif parsed.path == "/api/claude-stream":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            context_json = params.get("context", ["{}"])[0]

            if not query:
                self._json({"error": "请提供查询参数 q"})
                return

            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._sse_send({"error": "未配置 ANTHROPIC_API_KEY 环境变量"})
                self._sse_done()
                return

            try:
                context = json.loads(context_json)
            except json.JSONDecodeError:
                context = {}

            self._handle_claude_stream(query, context, api_key)
            return
        elif parsed.path == "/api/stats":
            eng = get_engine()
            self._json({
                "keywords": len(eng.keyword_map),
                "modules": len(eng.module_map),
                "menus": len(eng.menu_map),
                "kb_docs": len(eng.kb_docs),
                "report_docs": len(eng.report_docs),
            })
        elif parsed.path == "/api/image":
            params = parse_qs(parsed.query)
            img_path = params.get("path", [""])[0]
            self._serve_image(img_path)
        elif parsed.path == "/api/document":
            params = parse_qs(parsed.query)
            doc_path = params.get("path", [""])[0]
            if not doc_path:
                self._json({"error": "请提供文档路径"})
                return
            self._serve_document(doc_path)
        else:
            super().do_GET()

    def _sse_start(self):
        """发送 SSE 响应头"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _sse_send(self, data):
        """发送一条 SSE 事件"""
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _sse_done(self):
        """发送 SSE 结束信号"""
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _handle_claude_stream(self, query, context, api_key):
        """调用 Anthropic API，流式推送 Claude 回答"""
        self._sse_start()

        try:
            import anthropic
        except ImportError:
            self._sse_send({"error": "请安装 anthropic SDK: pip install anthropic"})
            self._sse_done()
            return

        client = anthropic.Anthropic(api_key=api_key)

        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        system_prompt = context.get("system", "")
        messages = context.get("messages", [{"role": "user", "content": query}])

        full_response = ""

        try:
            with client.messages.stream(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    self._sse_send({"text": text})

            # 发送完整回答和元数据
            self._sse_send({
                "type": "complete",
                "full_response": full_response,
                "meta": context.get("_meta", {}),
            })

        except anthropic.APIError as e:
            self._sse_send({"error": f"API 错误: {str(e)}"})
        except Exception as e:
            self._sse_send({"error": f"调用失败: {str(e)}"})

        self._sse_done()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_document(self, doc_path):
        """返回文档完整内容"""
        import re
        full_path = PROJECT_DIR / doc_path
        if not full_path.exists():
            self._json({"error": f"文档不存在: {doc_path}"})
            return
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            self._json({"error": "无法读取文档"})
            return

        # 提取标题
        title = ""
        for line in content.split("\n"):
            if line.startswith("# ") and not line.startswith("## "):
                title = line[2:].strip()
                break

        # 提取 frontmatter
        fm = {}
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()

        # 去掉 frontmatter 后的正文
        body = content
        if fm_match:
            body = content[fm_match.end():].strip()

        # 将相对路径的图片转为可访问的路径
        # 图片路径如: ![xxx](https://...) 或相对路径
        doc_dir = full_path.parent
        def resolve_img(m):
            alt = m.group(1)
            src = m.group(2)
            if src.startswith("http"):
                return f"![{alt}]({src})"
            # 相对路径 → 相对于文档所在目录
            img_path = doc_dir / src
            if img_path.exists():
                return f"![{alt}](/api/image?path={url_quote(str(img_path.relative_to(PROJECT_DIR)))})"
            return f"![{alt}]({src})"
        body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", resolve_img, body)

        self._json({
            "path": doc_path,
            "title": title,
            "frontmatter": fm,
            "content": body,
        })

    def _serve_image(self, img_path):
        """返回图片文件"""
        full_path = PROJECT_DIR / img_path
        if not full_path.exists():
            self.send_error(404)
            return
        ext = full_path.suffix.lower()
        content_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
        }
        ct = content_types.get(ext, "application/octet-stream")
        try:
            data = full_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(("0.0.0.0", port), SearchHandler)
    print(f"\n  产品知识库搜索服务已启动")
    print(f"  打开浏览器访问: http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()