#!/usr/bin/env python3
"""
FAQ 知识库静态 HTML 导出工具

用法:
    python3 faq_export.py                    # 生成 FAQ 知识库静态页面
    python3 faq_export.py --output 路径/     # 指定输出目录
    python3 faq_export.py --serve            # 生成并启动本地服务器预览

输出:
    - FAQ知识库/export/index.html  (单文件，可直接浏览器打开)
"""

import os
import re
import sys
import json
import http.server
import socketserver
import webbrowser
from pathlib import Path
from datetime import date
from collections import defaultdict

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
FAQ_DIR = PROJECT_DIR / "data" / "faq"
OUTPUT_DIR = FAQ_DIR / "export"
INDEX_FILE = FAQ_DIR / "INDEX.md"


def parse_frontmatter(text):
    """解析 YAML frontmatter"""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}
    fm_text = fm_match.group(1)
    data = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "keywords":
            value = value.strip("[]")
            data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
        elif key == "related":
            value = value.strip("[]")
            data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
        else:
            data[key] = value
    return data


def extract_body(text):
    """提取 markdown body（去掉 frontmatter）"""
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def simple_md_to_html(text):
    """简单的 Markdown 转 HTML（处理基本语法）"""
    # 标题
    text = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)

    # 粗体、斜体
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"「(.+?)」", r'<span class="highlight">\1</span>', text)

    # 代码块
    text = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", text, flags=re.DOTALL)

    # 行内代码
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 列表
    text = re.sub(r"^\d+\.\s+(.+)$", r"<li>\1</li>", text, flags=re.MULTILINE)
    text = re.sub(r"^-\s+(.+)$", r"<li>\1</li>", text, flags=re.MULTILINE)

    # 表格
    lines = text.split("\n")
    result = []
    in_table = False
    for i, line in enumerate(lines):
        if line.startswith("|") and "---" not in line:
            if not in_table:
                result.append("<table>")
                in_table = True
            cells = line.split("|")[1:-1]
            tag = "th" if i > 0 and lines[i-1].startswith("|--") else "td"
            row = "".join(f"<{tag}>{c.strip()}</{tag}>" for c in cells)
            result.append(f"<tr>{row}</tr>")
        else:
            if in_table and not line.startswith("|--"):
                result.append("</table>")
                in_table = False
            if not line.startswith("|--"):
                result.append(line)
    if in_table:
        result.append("</table>")
    text = "\n".join(result)

    # 段落
    paragraphs = []
    for p in text.split("\n\n"):
        p = p.strip()
        if not p:
            continue
        if not p.startswith("<"):
            p = f"<p>{p}</p>"
        paragraphs.append(p)
    text = "\n".join(paragraphs)

    return text


def collect_faqs():
    """收集所有 FAQ 文件"""
    faqs = []
    if not FAQ_DIR.exists():
        return faqs

    for md_file in sorted(FAQ_DIR.rglob("*.md")):
        if md_file.name in ("TEMPLATE.md", "INDEX.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            body = extract_body(text)
            html_body = simple_md_to_html(body)

            rel = md_file.relative_to(FAQ_DIR)
            parts = rel.parts

            faqs.append({
                "id": fm.get("id", ""),
                "title": fm.get("title", md_file.stem),
                "keywords": fm.get("keywords", []),
                "module": fm.get("module", ""),
                "dept": parts[0] if len(parts) > 0 else "",
                "sub_module": parts[1] if len(parts) > 1 else "",
                "scene": fm.get("scene", ""),
                "status": fm.get("status", "active"),
                "updated": fm.get("reviewed", ""),
                "html": html_body,
                "path": str(rel),
            })
        except Exception as e:
            print(f"Warning: 无法处理 {md_file}: {e}")

    return faqs


def build_html(faqs):
    """构建完整的 HTML 页面"""
    # 按部门+子模块分组
    groups = defaultdict(list)
    for f in faqs:
        key = f"{f['dept']}/{f['sub_module']}"
        groups[key].append(f)

    # 构建导航
    nav_html = ""
    for key in sorted(groups.keys()):
        dept, sub = key.split("/")
        nav_html += f'<div class="nav-group"><h3>{dept} · {sub}</h3><ul>\n'
        for f in groups[key]:
            status_cls = f"status-{f['status']}"
            kw_tags = " ".join(f'<span class="kw-tag">{k}</span>' for k in f['keywords'])
            nav_html += f"""<li>
  <a href="#{f['id']}" class="{status_cls}">{f['title']}</a>
  <div class="kw-row">{kw_tags}</div>
</li>\n"""
        nav_html += "</ul></div>\n"

    # 构建内容
    content_html = ""
    for f in faqs:
        status_badge = f'<span class="badge badge-{f["status"]}">{f["status"]}</span>'
        id_badge = f'<span class="badge badge-id">{f["id"]}</span>'
        kw_tags = " ".join(f'<span class="kw-tag">{k}</span>' for k in f['keywords'])
        content_html += f"""<article id="{f['id']}" class="faq-card">
  <div class="faq-header">
    {id_badge} {status_badge}
    <span class="faq-meta">{f['dept']} / {f['sub_module']} · 更新于 {f['updated']}</span>
  </div>
  <div class="faq-body">{f['html']}</div>
  <div class="faq-footer">
    <div class="kw-row">{kw_tags}</div>
  </div>
</article>\n"""

    # 统计
    total = len(faqs)
    active = sum(1 for f in faqs if f['status'] == 'active')
    outdated = sum(1 for f in faqs if f['status'] == 'outdated')
    deprecated = sum(1 for f in faqs if f['status'] == 'deprecated')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FAQ 知识库 - 产品技术支持</title>
<style>
:root {{
  --bg: #ffffff; --bg-secondary: #f8f9fa; --text: #1a1a2e; --text-secondary: #6b7280;
  --border: #e5e7eb; --accent: #2563eb; --accent-light: #dbeafe; --red: #dc2626;
  --yellow: #d97706; --green: #059669; --red-light: #fef2f2; --yellow-light: #fffbeb;
  --green-light: #ecfdf5; --shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a2e; --bg-secondary: #16213e; --text: #e5e7eb; --text-secondary: #9ca3af;
    --border: #374151; --accent: #60a5fa; --accent-light: #1e3a5f; --shadow: 0 1px 3px rgba(0,0,0,0.3);
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* 布局 */
.layout {{ display: flex; min-height: 100vh; }}
.sidebar {{ width: 320px; min-width: 320px; background: var(--bg-secondary); border-right: 1px solid var(--border); padding: 20px; overflow-y: auto; max-height: 100vh; position: sticky; top: 0; }}
.main {{ flex: 1; padding: 30px 40px; max-width: 900px; }}

/* 搜索 */
.search-box {{ position: sticky; top: 0; background: var(--bg-secondary); padding-bottom: 12px; z-index: 10; }}
.search-box input {{ width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; background: var(--bg); color: var(--text); }}
.search-box input:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }}

/* 导航 */
.nav-group {{ margin-bottom: 16px; }}
.nav-group h3 {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
.nav-group ul {{ list-style: none; }}
.nav-group li {{ margin-bottom: 4px; }}
.nav-group li a {{ display: block; padding: 6px 10px; border-radius: 6px; font-size: 14px; transition: background 0.15s; }}
.nav-group li a:hover {{ background: var(--accent-light); text-decoration: none; }}
.nav-group li a.status-deprecated {{ color: var(--text-secondary); text-decoration: line-through; }}

/* 顶栏 */
.topbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
.topbar h1 {{ font-size: 24px; }}
.stats {{ display: flex; gap: 16px; font-size: 13px; color: var(--text-secondary); }}

/* FAQ 卡片 */
.faq-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 24px; margin-bottom: 20px; box-shadow: var(--shadow); }}
.faq-header {{ display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }}
.faq-meta {{ font-size: 12px; color: var(--text-secondary); margin-left: auto; }}
.faq-body h1 {{ font-size: 20px; margin-bottom: 12px; }}
.faq-body h2 {{ font-size: 17px; margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
.faq-body h3 {{ font-size: 15px; margin: 16px 0 8px; }}
.faq-body p {{ margin-bottom: 10px; }}
.faq-body table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
.faq-body th, .faq-body td {{ border: 1px solid var(--border); padding: 8px 12px; text-align: left; font-size: 14px; }}
.faq-body th {{ background: var(--bg-secondary); font-weight: 600; }}
.faq-body code {{ background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
.faq-body pre {{ background: var(--bg-secondary); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 12px 0; }}
.faq-body pre code {{ background: none; padding: 0; }}
.faq-body li {{ margin-bottom: 4px; }}
.faq-body .highlight {{ background: var(--accent-light); color: var(--accent); padding: 0 2px; border-radius: 2px; font-weight: 500; }}

/* 标签 */
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
.badge-active {{ background: var(--green-light); color: var(--green); }}
.badge-outdated {{ background: var(--yellow-light); color: var(--yellow); }}
.badge-deprecated {{ background: var(--red-light); color: var(--red); }}
.badge-id {{ background: var(--accent-light); color: var(--accent); font-family: monospace; }}
.faq-footer {{ margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); }}

/* 关键词 */
.kw-row {{ display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }}
.kw-tag {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; background: var(--accent-light); color: var(--accent); }}

/* 响应式 */
@media (max-width: 768px) {{
  .layout {{ flex-direction: column; }}
  .sidebar {{ width: 100%; min-width: 100%; max-height: none; position: static; border-right: none; border-bottom: 1px solid var(--border); }}
  .main {{ padding: 20px; }}
}}

/* 搜索高亮 */
mark {{ background: #fef08a; padding: 0 2px; border-radius: 2px; }}
.hidden {{ display: none !important; }}
.no-results {{ text-align: center; padding: 40px; color: var(--text-secondary); }}
</style>
</head>
<body>
<div class="layout">
  <nav class="sidebar">
    <div class="search-box">
      <input type="text" id="search" placeholder="🔍 搜索 FAQ..." oninput="filterFAQs()">
    </div>
    <div id="nav-tree">{nav_html}</div>
  </nav>
  <main class="main" id="search-results">
    <div class="topbar">
      <h1>📚 FAQ 知识库</h1>
      <div class="stats">
        <span>共 {total} 条 FAQ</span>
        <span style="color:var(--green)">● {active} active</span>
        {f'<span style="color:var(--yellow)">● {outdated} outdated</span>' if outdated else ''}
        {f'<span style="color:var(--red)">● {deprecated} deprecated</span>' if deprecated else ''}
      </div>
    </div>
    <div id="faq-list">{content_html}</div>
    <div class="no-results hidden" id="no-results">未找到匹配的 FAQ</div>
  </main>
</div>

<script>
function filterFAQs() {{
  const query = document.getElementById('search').value.toLowerCase().trim();
  const cards = document.querySelectorAll('.faq-card');
  const navLinks = document.querySelectorAll('.nav-group li');
  const noResults = document.getElementById('no-results');
  let found = 0;

  cards.forEach(card => {{
    const text = card.textContent.toLowerCase();
    if (!query || text.includes(query)) {{
      card.classList.remove('hidden');
      found++;
      // 高亮
      if (query) {{
        const body = card.querySelector('.faq-body');
        const regex = new RegExp(`(${{query.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&')}})`, 'gi');
        body.innerHTML = body.innerHTML.replace(/<mark>|<\\/mark>/g, '');
        body.innerHTML = body.innerHTML.replace(regex, '<mark>$1</mark>');
      }}
    }} else {{
      card.classList.add('hidden');
    }}
  }});

  // 更新导航高亮
  navLinks.forEach(li => {{
    const a = li.querySelector('a');
    const href = a.getAttribute('href');
    if (!query) {{
      li.classList.remove('hidden');
      return;
    }}
    const card = document.querySelector(href);
    if (card && !card.classList.contains('hidden')) {{
      li.classList.remove('hidden');
    }} else {{
      li.classList.add('hidden');
    }}
  }});

  noResults.classList.toggle('hidden', found > 0 || !query);
}}

// 初始加载
document.addEventListener('DOMContentLoaded', () => {{
  const hash = window.location.hash;
  if (hash) {{
    const card = document.querySelector(hash);
    if (card) card.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }}
}});
</script>
</body>
</html>"""

    return html


def main():
    args = sys.argv[1:]
    output_dir = None
    do_serve = "--serve" in args

    for i, arg in enumerate(args):
        if arg == "--output" and i + 1 < len(args):
            output_dir = Path(args[i + 1])
        elif arg == "--serve":
            do_serve = True

    if not output_dir:
        output_dir = OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    faqs = collect_faqs()
    if not faqs:
        print("没有找到 FAQ 文件")
        return

    html = build_html(faqs)
    output_file = output_dir / "index.html"
    output_file.write_text(html, encoding="utf-8")
    print(f"✅ 已生成: {output_file}")
    print(f"   FAQ 数量: {len(faqs)}")
    print(f"   文件大小: {output_file.stat().st_size / 1024:.1f} KB")

    if do_serve:
        os.chdir(str(output_dir))
        port = 8899

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(output_dir), **kwargs)

        print(f"\n🌐 启动本地服务器: http://localhost:{port}")
        print(f"   按 Ctrl+C 停止")

        try:
            with socketserver.TCPServer(("", port), Handler) as httpd:
                webbrowser.open(f"http://localhost:{port}")
                httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


if __name__ == "__main__":
    main()