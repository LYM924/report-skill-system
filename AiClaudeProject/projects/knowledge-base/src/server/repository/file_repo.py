"""
FileRepository - 文件系统数据访问实现

从 data/ 目录读取知识文档、FAQ、模块定义等。
这是 KnowledgeRepository 的当前实现，后续可替换为 DBRepository。
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

from .base import (
    Document, FAQ, KeywordEntry, ModuleInfo, Report, KnowledgeRepository
)

# 路径常量
HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent.parent  # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
CONFIG_DIR = PROJECT_DIR / "config"
RUNTIME_DIR = PROJECT_DIR / "runtime"


class FileRepository(KnowledgeRepository):
    """文件系统知识库数据访问"""

    def __init__(self):
        self._kb_dir = DATA_DIR / "knowledge"
        self._faq_dir = DATA_DIR / "faq"
        self._raw_dir = DATA_DIR / "raw-docs"
        self._modules_dir = DATA_DIR / "modules"
        self._synonyms_file = CONFIG_DIR / "synonyms.json"
        self._keyword_index_file = CONFIG_DIR / "keyword_index.md"
        self._feedback_file = RUNTIME_DIR / "feedback.jsonl"

    # ── Documents ──

    def get_all_documents(self) -> list[Document]:
        docs = []
        if not self._kb_dir.exists():
            return docs
        for md_file in sorted(self._kb_dir.rglob("*.md")):
            if md_file.name == "INDEX.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            doc = self._parse_document(text, str(md_file.relative_to(PROJECT_DIR)))
            if doc:
                docs.append(doc)
        return docs

    def _parse_document(self, text: str, rel_path: str) -> Optional[Document]:
        """解析单个知识文档的 frontmatter"""
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return None
        fm = fm_match.group(1)
        body = text[fm_match.end():]

        def get_field(name, default=""):
            m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else default

        keywords = get_field("keywords", "[]")
        if keywords.startswith("["):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = [k.strip() for k in keywords.strip("[]").split(",") if k.strip()]
        else:
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        return Document(
            path=rel_path,
            title=get_field("title", ""),
            content=body[:500] if body else "",  # 采样
            dept=get_field("dept", ""),
            module=get_field("module", ""),
            product=get_field("product", ""),
            product_line=get_field("product_line", ""),
            date=get_field("date", ""),
            keywords=keywords if isinstance(keywords, list) else [],
            appendix=get_field("appendix", ""),
        )

    # ── FAQs ──

    def get_all_faqs(self) -> list[FAQ]:
        faqs = []
        if not self._faq_dir.exists():
            return faqs
        for md_file in sorted(self._faq_dir.rglob("*.md")):
            if md_file.name in ("INDEX.md", "TEMPLATE.md"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            faq = self._parse_faq(text, str(md_file.relative_to(PROJECT_DIR)))
            if faq:
                faqs.append(faq)
        return faqs

    def _parse_faq(self, text: str, rel_path: str) -> Optional[FAQ]:
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return None
        fm = fm_match.group(1)
        body = text[fm_match.end():]

        def get_field(name, default=""):
            m = re.search(rf"^{name}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else default

        keywords = get_field("keywords", "[]")
        if keywords.startswith("["):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = []
        else:
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        return FAQ(
            id=get_field("id", ""),
            title=get_field("title", ""),
            content=body,
            path=rel_path,
            keywords=keywords if isinstance(keywords, list) else [],
            dept=get_field("dept", ""),
            sub_module=get_field("sub_module", ""),
            module=get_field("module", ""),
            scene=get_field("scene", ""),
            status=get_field("status", "active"),
        )

    def save_faq(self, faq: FAQ) -> str:
        """保存 FAQ 到文件系统"""
        dept_dir = faq.dept or "数智财务组"
        sub_dir = faq.sub_module or faq.module or "其他"
        target_dir = self._faq_dir / dept_dir / sub_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{faq.title}.md"
        file_path = target_dir / filename

        content = f"""---
id: {faq.id}
title: {faq.title}
keywords: {json.dumps(faq.keywords, ensure_ascii=False)}
module: {faq.module}
dept: {faq.dept}
sub_module: {faq.sub_module}
scene: "{faq.scene}"
status: {faq.status}
version_from: ""
created: {datetime.now().strftime('%Y-%m-%d')}
reviewed: {datetime.now().strftime('%Y-%m-%d')}
related: []
tickets: []
---

{faq.content}
"""
        file_path.write_text(content, encoding="utf-8")
        return str(file_path.relative_to(PROJECT_DIR))

    def delete_faq(self, path: str) -> bool:
        full_path = PROJECT_DIR / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    # ── Keywords ──

    def get_all_keywords(self) -> dict[str, list[dict]]:
        """解析关键词索引.md，返回 {keyword: [{module, dept, ...}]}"""
        keyword_map = defaultdict(list)
        if not self._keyword_index_file.exists():
            return dict(keyword_map)

        text = self._keyword_index_file.read_text(encoding="utf-8")
        current_dept = ""
        current_domain = ""

        for line in text.split("\n"):
            dept_match = re.match(r"^###\s+(.+?)\s*[·•]\s*(.+)$", line)
            if dept_match:
                current_dept = dept_match.group(1).strip()
                current_domain = dept_match.group(2).strip()
                continue

            if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 关键词"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 5 and cells[0] and cells[1]:
                    keyword = cells[0]
                    if len(cells) >= 7:
                        dept = cells[3] if cells[3] else current_dept
                        domain = cells[4] if cells[4] else current_domain
                        kb_path = cells[5] if len(cells) > 5 else ""
                    else:
                        dept = cells[2] if len(cells) > 2 and cells[2] else current_dept
                        domain = cells[3] if len(cells) > 3 and cells[3] else current_domain
                        kb_path = cells[4] if len(cells) > 4 and cells[4] else ""

                    keyword_map[keyword].append({
                        "module": cells[1],
                        "dept": dept,
                        "domain": domain,
                        "kb_path": kb_path,
                    })

        return dict(keyword_map)

    # ── Modules ──

    def get_all_modules(self) -> dict[str, ModuleInfo]:
        modules = {}
        if not self._modules_dir.exists():
            return modules
        for md_file in sorted(self._modules_dir.rglob("*.md")):
            if md_file.name in ("SKILL.md", "zlb_menu.md"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            info = self._parse_module_file(text, str(md_file.relative_to(PROJECT_DIR)), md_file.stem)
            if info:
                modules[info.name] = info
        return modules

    def _parse_module_file(self, text: str, rel_path: str, name: str) -> Optional[ModuleInfo]:
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        fm = fm_match.group(1) if fm_match else ""

        def get_field(key, default=""):
            m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip() if m else default

        # 关键词 section
        kw_match = re.search(r"## 关键词\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
        keywords = []
        if kw_match:
            keywords = [k.strip() for k in kw_match.group(1).strip().split(",") if k.strip()]

        # 菜单映射
        menus = []
        menu_section = re.search(r"## 菜单映射\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
        if menu_section:
            for line in menu_section.group(1).strip().split("\n"):
                if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 一级"):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    for c in cells:
                        if c and c != "-":
                            menus.append(c)

        return ModuleInfo(
            name=name,
            path=rel_path,
            dept=get_field("department", ""),
            domain=get_field("business_domain", ""),
            product=get_field("product", ""),
            keywords=keywords,
            menus=menus,
        )

    # ── Reports ──

    def get_all_reports(self) -> list[Report]:
        reports = []
        report_dir_new = DATA_DIR / "reports"
        report_dir = report_dir_new if report_dir_new.exists() else None
        if not report_dir:
            return reports
        for md_file in sorted(report_dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            title = ""
            for line in text.split("\n"):
                if line.startswith("# ") and not line.startswith("## "):
                    title = line[2:].strip()
                    break
            reports.append(Report(
                path=str(md_file.relative_to(PROJECT_DIR)),
                title=title,
                content=text[:500],
            ))
        return reports

    # ── Raw Docs ──

    def get_raw_docs(self) -> list[Document]:
        docs = []
        if not self._raw_dir.exists():
            return docs
        for md_file in sorted(self._raw_dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            docs.append(Document(
                path=str(md_file.relative_to(PROJECT_DIR)),
                title=md_file.stem,
                content=text[:500],
            ))
        return docs

    # ── Synonyms ──

    def get_synonyms(self) -> dict[str, list[str]]:
        if self._synonyms_file.exists():
            with open(self._synonyms_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # ── Feedback ──

    def save_feedback(self, query: str, result_id: str, result_path: str, feedback_type: str) -> None:
        record = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "result_id": result_id,
            "result_path": result_path,
            "type": feedback_type,
        }
        with open(self._feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")