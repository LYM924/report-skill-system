#!/usr/bin/env python3
"""
产品知识库智能检索引擎
用法: python3 search_engine.py "查询内容" [--top N] [--rebuild]
输出: JSON 格式结构化检索结果
"""

import json
import re
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import faiss
import jieba
import logging
jieba.setLogLevel(logging.WARNING)
from pypinyin import lazy_pinyin, Style
from bm25_index import BM25Index
from vector_index import VectorIndex
from search_utils import extract_title, extract_snippets, deduplicate, rank
from spell_corrector import SpellCorrector, create_corrector
from query_parser import QueryParser
from repository import DBRepository

# ---------- jieba 自定义词典：确保业务术语不被错误切分 ----------
_JIEBA_CUSTOM_TERMS = [
    # 报销/申请相关
    ("报销单", 100), ("差旅报销单", 100), ("申请单", 100),
    ("创建报销单", 80), ("我的单据", 80), ("报销申请", 80),
    ("差旅报销", 100), ("差旅申请单", 100), ("费用报销单", 100),
    # FAQ 相关术语
    ("选不到", 100), ("找不到", 100), ("无法选择", 100),
    ("无需报销", 100), ("不报销", 80), ("免报销", 80),
    ("关联单据", 100), ("关联申请单", 100), ("申请单列表", 80),
    ("选择列表", 80), ("选择不到", 100), ("审批通过", 80),
    # 银行/电子档案相关
    ("银行回单", 100), ("回单同步", 100), ("同步回单", 100),
    ("自动关联", 80), ("回单缺失", 80), ("回单关联", 80),
    ("四性检测", 100), ("核算云", 100), ("资料采集", 80),
    ("实体移交", 100), ("实体接收", 100), ("记账凭证", 100),
    ("凭证传输", 100), ("归档失败", 80), ("归档附件", 80),
    # 通用业务术语
    ("用款计划", 80), ("支付申请", 80), ("预算指标", 80),
    ("公务卡", 80), ("兑付报销", 80), ("批量报销", 80),
    ("指标同步", 80), ("发票后补", 80), ("财务审核", 80),
    ("出纳结算", 80), ("国库支付", 80), ("进项税额", 80),
    ("票据信息", 80), ("行程组件", 80), ("人脸采集", 80),
    ("单位管理", 80), ("人员管理", 80), ("运营后台", 80),
    ("财务管理", 80), ("数据监管", 80), ("工作台", 80),
    ("电子档案", 80), ("免疫规划", 80), ("数字化支撑", 80),
    ("浙里报", 100), ("徽报账", 100), ("数里通", 80),
    # 免疫规划专用术语
    ("接种证", 100), ("预防接种", 100), ("接种记录", 100),
    ("入学入托", 100), ("查验结果", 80), ("疫苗库存", 80),
]
for _term, _freq in _JIEBA_CUSTOM_TERMS:
    jieba.add_word(_term, freq=_freq, tag='n')

# 从 DB 自动加载 FAQ 关键词到 jieba 词典
def _load_jieba_from_db():
    """从数据库 faqs 表加载关键词到 jieba 词典"""
    try:
        import json as _json
        from repository import DBRepository
        repo = DBRepository()
        rows = repo._execute("SELECT DISTINCT tags FROM faqs WHERE is_deleted = FALSE")
        for row in rows:
            try:
                tags = _json.loads(row["tags"])
                for tag in tags:
                    if len(tag) >= 2:
                        jieba.add_word(tag, freq=80, tag='n')
            except Exception:
                pass
    except Exception:
        pass

_load_jieba_from_db()

# ---------- paths ----------
HERE = Path(__file__).resolve().parent  # src/server/
PROJECT_DIR = HERE.parent.parent  # knowledge-base/
DATA_DIR = PROJECT_DIR / "data"
CONFIG_DIR = PROJECT_DIR / "config"
RUNTIME_DIR = PROJECT_DIR / "runtime"

# 知识库目录
KB_DIR = DATA_DIR / "knowledge"

# 报表目录
REPORT_DIR = DATA_DIR / "reports"
SYNONYMS_FILE = CONFIG_DIR / "synonyms.json"
CACHE_FILE = RUNTIME_DIR / "cache" / "index_cache.json"
KEYWORD_INDEX_FILE = CONFIG_DIR / "keyword-index.md"

# FAQ 知识库目录
FAQ_DIR = DATA_DIR / "faq"


# ---------- engine ----------
class SearchEngine:
    def __init__(self, use_db=True):
        self.repo = DBRepository() if use_db else None
        self.keyword_map = defaultdict(list)
        self.module_map = {}  # module_name -> {path, dept, domain, owners, keywords, menus, ...}
        self.menu_map = defaultdict(list)  # menu_name -> [module_name]
        self.product_module_map = {}  # 产品模块映射（来自 module_map.json）：模块名 -> {dept2, dept1, product, product_line, domain}
        self.kb_docs = []  # [{path, module, dept, domain, content_sample}]
        self.report_docs = []  # [{path, title, content_sample}]
        self.synonyms = {}  # word -> [aliases]
        self.faq_cache = {}  # 回答缓存: {fingerprint: {query, answer, keywords, module, saved_at}}
        self.faq_cache_file = RUNTIME_DIR / "cache" / "faq_cache.json"
        self.faq_docs = []  # FAQ 知识库文档
        self.bm25 = None
        self.bm25_cache_file = RUNTIME_DIR / "cache" / "bm25_index.pkl"
        self.vector = None
        self.vector_index_file = RUNTIME_DIR / "cache" / "vector_index.faiss"
        self.vector_meta_file = RUNTIME_DIR / "cache" / "vector_meta.pkl"
        self.corrector = None  # 拼写纠错器（首次使用时懒加载）
        self.query_parser = QueryParser()  # 搜索语法解析器

    # -------- load --------

    def load_all(self):
        self._load_synonyms()
        self._load_keyword_index()
        self._load_module_files()
        self._load_product_module_map()
        self._load_knowledge_base()
        self._load_faq_knowledge()
        self._load_report_data()
        self._load_faq_cache()
        self._load_bm25_index()
        self._load_vector_index()

    def _load_synonyms(self):
        if self.repo:
            self.synonyms = self.repo.get_synonyms()
        elif SYNONYMS_FILE.exists():
            with open(SYNONYMS_FILE, "r", encoding="utf-8") as f:
                self.synonyms = json.load(f)

    def _load_keyword_index(self):
        """获取关键词→模块映射（从新表加载）"""
        if self.repo:
            self.keyword_map = defaultdict(list, self.repo.get_all_keywords_v2())
            return
        # 文件回退
        # 文件回退
        if not KEYWORD_INDEX_FILE.exists():
            return
        text = KEYWORD_INDEX_FILE.read_text(encoding="utf-8")

        current_dept = ""
        current_domain = ""
        current_kb_path = ""

        for line in text.split("\n"):
            # 跟踪当前部门/业务域
            dept_match = re.match(r"^###\s+(.+?)\s*[·•]\s*(.+)$", line)
            if dept_match:
                current_dept = dept_match.group(1).strip()
                current_domain = dept_match.group(2).strip()
                continue

            # 解析表格行 - 兼容新旧两种格式
            # 旧格式(6列): | 关键词 | 产品模块 | 所属部门 | 业务域 | 知识库路径 | 备注 |
            # 新格式(7列): | 关键词 | 产品模块 | 模块文件 | 所属部门 | 业务域 | 知识库路径 | 备注 |
            if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 关键词"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 5 and cells[0] and cells[1]:
                    keyword = cells[0]
                    module_name = cells[1]
                    if len(cells) >= 7:
                        # 新格式：模块文件在列2，部门/域/路径各后移一列
                        dept = cells[3] if cells[3] else current_dept
                        domain = cells[4] if cells[4] else current_domain
                        kb_path_val = cells[5] if cells[5] else current_kb_path
                        note = cells[6] if len(cells) > 6 else ""
                    else:
                        # 旧格式
                        dept = cells[2] if len(cells) > 2 and cells[2] else current_dept
                        domain = cells[3] if len(cells) > 3 and cells[3] else current_domain
                        kb_path_val = cells[4] if len(cells) > 4 and cells[4] else current_kb_path
                        note = cells[5] if len(cells) > 5 else ""

                    entry = {
                        "module": module_name,
                        "dept": dept,
                        "domain": domain,
                        "kb_path": kb_path_val,
                        "note": note,
                    }
                    self.keyword_map[keyword].append(entry)

    def _load_module_files(self):
        """加载所有模块信息（优先数据库）"""
        if self.repo:
            self.module_map = self.repo.get_all_modules()
            # 构建 menu_map
            self.menu_map = defaultdict(list)
            for mod_name, info in self.module_map.items():
                for menu in info.get('menus', []):
                    self.menu_map[menu].append(mod_name)
            return
        # 文件回退
        module_dirs = [
            DATA_DIR / "modules" / "数智财务组",
            DATA_DIR / "modules" / "免疫规划组",
            DATA_DIR / "modules" / "数字化支撑组",
            DATA_DIR / "modules" / "电子档案组",
        ]

        for md_dir in module_dirs:
            if not md_dir.exists():
                continue
            for md_file in sorted(md_dir.rglob("*.md")):
                if md_file.name == "SKILL.md" or md_file.name == "zlb_menu.md":
                    continue
                info = self._parse_module_file(md_file)
                if info:
                    self.module_map[info["name"]] = info

    def _parse_module_file(self, filepath):
        """解析单个模块 Skill 文件"""
        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception:
            return None

        info = {
            "name": filepath.stem,
            "path": str(filepath.relative_to(PROJECT_DIR)),
            "dept": "",
            "domain": "",
            "product": "",
            "dev_owner": "",
            "module_owner": "",
            "appendix": "",
            "keywords": [],
            "menus": [],
        }

        # 解析 frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.split("\n"):
                line = line.strip()
                if line.startswith("product:"):
                    info["product"] = line.split(":", 1)[1].strip()
                elif line.startswith("department:"):
                    info["dept"] = line.split(":", 1)[1].strip()
                elif line.startswith("business_domain:"):
                    info["domain"] = line.split(":", 1)[1].strip()
                elif line.startswith("dev_owner:"):
                    info["dev_owner"] = line.split(":", 1)[1].strip()
                elif line.startswith("module_owner:"):
                    info["module_owner"] = line.split(":", 1)[1].strip()
                elif line.startswith("appendix:"):
                    info["appendix"] = line.split(":", 1)[1].strip()

        # 解析关键词
        kw_match = re.search(r"## 关键词\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
        if kw_match:
            info["keywords"] = [k.strip() for k in kw_match.group(1).strip().split(",") if k.strip()]

        # 解析菜单映射
        menu_section = re.search(r"## 菜单映射\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
        if menu_section:
            for line in menu_section.group(1).strip().split("\n"):
                if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 一级"):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if cells:
                        for c in cells:
                            if c and c != "-":
                                info["menus"].append(c)
                                self.menu_map[c].append(info["name"])

        return info

    def _load_product_module_map(self):
        """加载产品模块映射表（module_map.json，由 product_module.xlsx 转换而来）"""
        map_file = CONFIG_DIR / "module_map.json"
        if map_file.exists():
            try:
                with open(map_file, "r", encoding="utf-8") as f:
                    self.product_module_map = json.load(f)
            except Exception:
                self.product_module_map = {}

    def _load_knowledge_base(self):
        """索引知识库文档（优先数据库）"""
        # 1. 从数据库读取（优先）
        if self.repo:
            try:
                docs = self.repo._execute("""
                    SELECT path, title, content, dept, module, product, date,
                           keywords, dept as dept3
                    FROM documents WHERE is_deleted = FALSE
                """)
                if docs:
                    for row in docs:
                        sample = (row["content"] or "")[:5000]
                        self.kb_docs.append({
                            "path": row["path"],
                            "dept": row["dept"] or "",
                            "dept3": row["dept3"] or "",
                            "domain": row["module"] or "",
                            "product": row["product"] or "",
                            "module": row["module"] or "",
                            "date": row["date"] or "",
                            "title": row["title"] or "",
                            "content_sample": sample,
                            "keywords": row["keywords"] if isinstance(row["keywords"], list) else [],
                        })
                    return
            except Exception:
                pass

        # 2. 文件系统回退
        if not KB_DIR.exists():
            return
        for md_file in sorted(KB_DIR.rglob("*.md")):
            if md_file.name == "INDEX.md" or md_file.name == "TEMPLATE.md":
                continue  # 跳过索引和模板文件
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            sample = text[:5000]
            rel_path = str(md_file.relative_to(PROJECT_DIR))

            parts = md_file.relative_to(KB_DIR).parts
            dept = parts[0] if len(parts) > 0 else ""
            # domain 不能从目录取（目录只有2级，parts[1]是文件名），
            # 需要从 frontmatter 或文档内容中提取产品模块
            domain = ""

            # 从 frontmatter 读取元数据
            fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            fm_dept, fm_dept3, fm_product, fm_product_raw, fm_kw, fm_module, fm_date = "", "", "", "", [], "", ""
            if fm_match:
                fm_text = fm_match.group(1)
                for line in fm_text.split("\n"):
                    line = line.strip()
                    if line.startswith("dept3:") or line.startswith("关联部门:"):
                        fm_dept3 = line.split(":", 1)[1].strip()
                    elif line.startswith("department:") or line.startswith("dept:"):
                        fm_dept = line.split(":", 1)[1].strip()
                    elif line.startswith("module:"):
                        fm_module = line.split(":", 1)[1].strip()
                        fm_product = fm_module  # 模块名优先作为产品模块
                    elif line.startswith("product:") or line.startswith("domain:"):
                        fm_product_raw = line.split(":", 1)[1].strip()
                        if not fm_product:
                            fm_product = line.split(":", 1)[1].strip()
                    elif line.startswith("date:"):
                        fm_date = line.split(":", 1)[1].strip()
                    elif line.startswith("keywords:"):
                        kw_str = line.split(":", 1)[1].strip()
                        kw_str = kw_str.strip("[]")
                        fm_kw = [k.strip().strip("'\"") for k in kw_str.split(",") if k.strip()]
            if fm_dept:
                dept = fm_dept
            if fm_product:
                domain = fm_product
            else:
                # 无 frontmatter 时，从文档表格中提取「产品」字段
                prod_match = re.search(r'\|\s*产品\s*\|\s*([^|\n]+)', text)
                if prod_match:
                    domain = prod_match.group(1).strip()

            # 预提取关键词（从 keyword_map 匹配，取前 5 个高频词）
            # frontmatter 中的关键词优先
            keywords = fm_kw if fm_kw else []
            if not keywords and self.keyword_map:
                from collections import Counter
                kw_counter = Counter()
                for kw in self.keyword_map:
                    if len(kw) >= 2 and kw in sample:
                        kw_counter[kw] += 1
                keywords = [kw for kw, _ in kw_counter.most_common(5)]

            self.kb_docs.append({
                "path": rel_path,
                "dept": dept,
                "dept3": fm_dept3,
                "domain": domain,
                "product": fm_product_raw,
                "module": fm_module,
                "date": fm_date,
                "title": extract_title(text),
                "content_sample": sample,
                "keywords": keywords,
            })

    def _load_faq_knowledge(self):
        """索引 FAQ 知识库文档（优先从 DB/Repo 获取）"""
        faqs = []
        if self.repo:
            try:
                faqs = self.repo.get_all_faqs()
            except Exception:
                faqs = []

        # 如果 repo 不可用或无数据，回退文件系统
        if not faqs and FAQ_DIR.exists():
            for md_file in sorted(FAQ_DIR.rglob("*.md")):
                if md_file.name == "TEMPLATE.md" or md_file.name == "INDEX.md":
                    continue
                try:
                    text = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue
                sample = text[:5000]
                rel_path = str(md_file.relative_to(PROJECT_DIR))
                parts = md_file.relative_to(FAQ_DIR).parts
                dept = parts[0] if len(parts) > 0 else ""
                sub_module = parts[1] if len(parts) > 1 else ""
                faq_id, keywords, title = "", [], ""
                fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if fm_match:
                    fm_text = fm_match.group(1)
                    for line in fm_text.split("\n"):
                        line = line.strip()
                        if line.startswith("id:"):
                            faq_id = line.split(":", 1)[1].strip()
                        elif line.startswith("keywords:"):
                            kw_str = line.split(":", 1)[1].strip()
                            kw_str = kw_str.strip("[]")
                            keywords = [k.strip().strip("'\"") for k in kw_str.split(",") if k.strip()]
                        elif line.startswith("title:"):
                            title = line.split(":", 1)[1].strip()
                if not title:
                    title = extract_title(text)
                self.faq_docs.append({
                    "path": rel_path, "faq_id": faq_id, "title": title,
                    "keywords": keywords, "dept": dept, "sub_module": sub_module,
                    "content_sample": sample,
                })
                self.kb_docs.append({
                    "path": rel_path, "dept": dept, "domain": sub_module,
                    "title": f"[FAQ] {title}", "content_sample": sample,
                })
            return

        # 从 repo 获取的 FAQ 对象
        for faq in faqs:
            sample = faq.faq_answer[:5000] if faq.faq_answer else (faq.content or "")[:5000]
            rel_path = faq.path or ""
            if not rel_path and faq.faq_code:
                rel_path = f"data/faq/{faq.dept}/{faq.sub_module}/{faq.faq_code}.md"
            self.faq_docs.append({
                "path": rel_path, "faq_id": faq.faq_code, "title": faq.faq_title,
                "keywords": faq.tags if isinstance(faq.tags, list) else [],
                "dept": faq.dept, "sub_module": faq.sub_module, "module": faq.module,
                "content_sample": sample,
                "view_count": faq.view_count if hasattr(faq, 'view_count') else 0,
            })
            self.kb_docs.append({
                "path": rel_path, "dept": faq.dept, "domain": faq.sub_module,
                "title": f"[FAQ] {faq.faq_title}", "content_sample": sample,
            })

    def _load_report_data(self):
        """索引报表数据（优先数据库）"""
        # 1. 从数据库读取（优先）
        if self.repo:
            try:
                rows = self.repo._execute("""
                    SELECT path, title, content FROM reports WHERE is_deleted = FALSE
                """)
                if rows:
                    for row in rows:
                        sample = (row["content"] or "")[:5000]
                        self.report_docs.append({
                            "path": row["path"] or "",
                            "title": row["title"] or "",
                            "content_sample": sample,
                        })
                    return
            except Exception:
                pass

        # 2. 文件系统回退
        if not REPORT_DIR.exists():
            return
        for md_file in sorted(REPORT_DIR.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            sample = text[:5000]
            rel_path = str(md_file.relative_to(PROJECT_DIR))

            self.report_docs.append({
                "path": rel_path,
                "title": extract_title(text),
                "content_sample": sample,
            })

    def _load_faq_cache(self):
        """加载 FAQ 回答缓存"""
        if self.faq_cache_file.exists():
            try:
                with open(self.faq_cache_file, "r", encoding="utf-8") as f:
                    self.faq_cache = json.load(f)
            except Exception:
                self.faq_cache = {}

    def seed_faq_cache(self):
        """从 KB 文件和模块文件提取种子 FAQ，批量写入 faq_cache.json。

        来源1: KB 文件中的 FAQ/常见问题章节
        来源2: 模块文件关键词 → 生成"什么是XX"类问题
        来源3: FAQ 知识库文件 → 提取 frontmatter + 摘要
        """
        import hashlib
        from datetime import datetime

        seeds = []
        seen_queries = set()

        # 来源1: KB 文件中的 FAQ 章节
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue

            # 查找 FAQ 章节
            faq_match = re.search(
                r'##\s*(?:FAQ|常见问题|故障库|常见问题&故障库).*?\n(.*?)(?=\n##\s+\w|\Z)',
                content, re.DOTALL
            )
            if faq_match:
                # 提取 Q&A 对
                qa_pairs = re.findall(
                    r'###\s*Q:\s*(.+?)\n(.*?)(?=\n###\s*Q:|\n##\s|\Z)',
                    faq_match.group(1), re.DOTALL
                )
                for q, a in qa_pairs:
                    q = q.strip()
                    if q in seen_queries:
                        continue
                    seen_queries.add(q)
                    seeds.append({
                        'query': q,
                        'answer': a.strip()[:800],
                        'keywords': [t.strip() for t in jieba.cut(q) if len(t.strip()) >= 2],
                        'module': doc.get('domain', ''),
                        'dept': doc.get('dept', ''),
                        'domain': doc.get('domain', ''),
                    })

        # 来源2: 模块文件关键词 → 生成基础问答
        for mod_name, info in self.module_map.items():
            keywords = info.get('keywords', [])
            for kw in keywords[:3]:
                q = f'{kw}是什么'
                if q in seen_queries:
                    continue
                seen_queries.add(q)
                dept = info.get('dept', '')
                domain = info.get('domain', '')
                owner = info.get('module_owner', '')
                dev = info.get('dev_owner', '')
                owner_str = f'{owner}（研发 {dev}）' if dev else owner
                answer = (
                    f'{kw}属于「{mod_name}」模块'
                    + (f'（{domain} / {dept}）' if domain else '')
                    + (f'，由{owner_str}负责。' if owner_str else '。')
                )
                seeds.append({
                    'query': q,
                    'answer': answer,
                    'keywords': [kw, mod_name],
                    'module': mod_name,
                    'dept': dept,
                    'domain': domain,
                })

        # 来源3: FAQ 知识库文件 → 提取标题+摘要
        for doc in self.faq_docs:
            title = doc.get('title', '')
            keywords = doc.get('keywords', [])
            if title:
                # 用标题作为查询
                q = title
                if q in seen_queries:
                    continue
                seen_queries.add(q)
                # 提取问题描述作为回答摘要
                faq_path = PROJECT_DIR / doc['path']
                answer = title
                if faq_path.exists():
                    try:
                        content = faq_path.read_text(encoding='utf-8')
                        match = re.search(r'## 问题描述\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
                        if match:
                            answer = match.group(1).strip()[:500]
                    except Exception:
                        pass
                seeds.append({
                    'query': q,
                    'answer': answer,
                    'keywords': keywords,
                    'module': doc.get('sub_module', ''),
                    'dept': doc.get('dept', ''),
                    'domain': doc.get('sub_module', ''),
                })
            # 同时用 faq_id 作为查询
            faq_id = doc.get('faq_id', '')
            if faq_id and faq_id not in seen_queries:
                seen_queries.add(faq_id)
                seeds.append({
                    'query': faq_id,
                    'answer': title,
                    'keywords': keywords,
                    'module': doc.get('sub_module', ''),
                    'dept': doc.get('dept', ''),
                    'domain': doc.get('sub_module', ''),
                })

        # 批量写入
        for seed in seeds:
            fp = hashlib.md5(seed['query'].encode()).hexdigest()[:12]
            if fp not in self.faq_cache:
                self.faq_cache[fp] = {
                    'query': seed['query'],
                    'answer': seed['answer'],
                    'keywords': seed['keywords'],
                    'module': seed['module'],
                    'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                }

        # 持久化
        with open(self.faq_cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.faq_cache, f, ensure_ascii=False, indent=2)

        return len(seeds)

    def _load_bm25_index(self):
        """加载或构建 BM25 索引"""
        self.bm25 = BM25Index()
        if self.bm25_cache_file.exists():
            self.bm25.load(str(self.bm25_cache_file))
            return

        # 首次构建：读取所有 KB 文件全文
        kb_contents = []
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                content = ''
            kb_contents.append({
                'path': doc['path'],
                'content': content,
                'dept': doc.get('dept', ''),
                'domain': doc.get('domain', ''),
            })

        if kb_contents:
            self.bm25.build(kb_contents)
            self.bm25.save(str(self.bm25_cache_file))

    def add_to_index(self, doc_path: str, content: str, dept: str = "", domain: str = ""):
        """增量添加单个文档到 BM25 索引（不重建整个索引）"""
        if self.bm25 is None:
            self._load_bm25_index()
        if self.bm25 and self.bm25.N > 0:
            self.bm25.add_document({
                'path': doc_path,
                'content': content,
                'dept': dept,
                'domain': domain,
            })
            self.bm25.save(str(self.bm25_cache_file))

    def _load_vector_index(self):
        """加载或构建向量索引"""
        self.vector = VectorIndex()
        if self.vector_index_file.exists() and self.vector_meta_file.exists():
            # 加载预构建的 FAISS 索引和元数据（模型已在 VectorIndex() 中初始化）
            self.vector.load(str(self.vector_index_file), str(self.vector_meta_file))
            return

        # 首次构建：对所有 KB 文档段落生成 embedding
        segments = []
        for doc in self.kb_docs:
            full_path = PROJECT_DIR / doc['path']
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue
            for seg in self._split_by_heading(content, doc['path']):
                if seg['heading'] == '(文档开头)' and len(seg['content']) < 100:
                    continue
                if len(seg['content']) >= 50:
                    segments.append({
                        'path': doc['path'],
                        'heading': seg['heading'],
                        'content': seg['content'],
                    })

        if segments:
            self.vector.build(segments)
            self.vector.save(str(self.vector_index_file), str(self.vector_meta_file))

    # -------- search --------

    # 查询意图映射：常见问题 → 目标模块（自动识别查询意图）
    QUERY_INTENT_MAP = {
        # 报销相关
        "报销": ["浙里报", "报销单"], "报销单": ["浙里报", "报销单"],
        "差旅": ["浙里报", "差旅报销单"], "出差": ["浙里报", "差旅报销单"],
        "申请单": ["浙里报", "差旅申请单"], "审批": ["浙里报", "报销单"],
        "预算": ["浙里报", "预算中心"], "指标": ["浙里报", "预算中心"],
        "发票": ["浙里报", "发票平台"], "票据": ["浙里报", "发票平台"],
        "合同": ["浙里报", "合同管理"], "用款": ["浙里报", "预算中心"],
        "支付": ["浙里报", "收费平台"], "兑付": ["浙里报", "报销单"],
        "公务卡": ["浙里报", "报销单"], "财务": ["浙里报"],
        "浙里报": ["浙里报"], "徽报账": ["徽报账"],
        # 免疫规划相关
        "接种": ["预防接种", "疫苗馆"], "疫苗": ["预防接种", "疫苗馆"],
        "免疫": ["预防接种", "免疫规划"], "门诊": ["智慧门诊", "数字化门诊"],
        "库存": ["疫苗馆"], "查验": ["入学入托查验"],
        "催种": ["智能催种"], "新生儿": ["预防接种"],
        "疫苗馆": ["疫苗馆"], "预防接种": ["预防接种"],
        # 电子档案相关
        "档案": ["电子档案"], "归档": ["电子档案"],
        "借阅": ["电子档案"], "案卷": ["电子档案"],
        # 数字化支撑相关
        "开票": ["发票平台"], "收费": ["收费平台"],
        "结算": ["结算平台"], "成本": ["成本平台"],
        "大屏": ["产研大屏"], "消息": ["消息平台"],
    }

    def _detect_intent(self, query: str, tokens: list) -> set:
        """检测查询意图，返回匹配的模块名集合"""
        intent_modules = set()
        query_lower = query.lower()
        for keyword, modules in self.QUERY_INTENT_MAP.items():
            if keyword in query or keyword in query_lower:
                intent_modules.update(modules)
        return intent_modules

    def _apply_freshness_boost(self, results: list) -> list:
        """时效性加权：新文档加分"""
        from datetime import date, timedelta
        today = date.today()
        for r in results:
            kb_path = r.get("kb_path", "") or r.get("path", "")
            # 从路径提取日期，如 20260609 → date(2026,6,9)
            import re
            m = re.search(r'(\d{4})(\d{2})(\d{2})', kb_path)
            if m:
                try:
                    doc_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    days_ago = (today - doc_date).days
                    if days_ago <= 90:      # 3个月内 +3
                        r["score"] = r.get("score", 0) + 3
                    elif days_ago <= 180:    # 半年内 +2
                        r["score"] = r.get("score", 0) + 2
                    elif days_ago <= 365:    # 一年内 +1
                        r["score"] = r.get("score", 0) + 1
                except ValueError:
                    pass
        return results

    def _apply_diversity(self, results: list) -> list:
        """结果多样性：同一部门最多展示 5 条，同一模块最多 3 条"""
        dept_counts = {}
        mod_counts = {}
        filtered = []
        for r in results:
            dept = r.get("dept", "") or "__unknown__"
            mod = r.get("module", "") or r.get("sub_module", "") or dept
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
            mod_counts[mod] = mod_counts.get(mod, 0) + 1
            if dept_counts[dept] <= 5 and mod_counts[mod] <= 3:
                filtered.append(r)
        return filtered

    def _compute_facets(self, results: list) -> dict:
        """计算搜索结果的分面聚合。

        返回按 dept、module、source 维度聚合的计数，用于前端分面筛选。
        """
        facets = {
            "dept": {},
            "module": {},
            "source": {},
        }

        for r in results:
            # 部门维度
            dept = r.get("dept", "") or "未知"
            if dept:
                facets["dept"][dept] = facets["dept"].get(dept, 0) + 1

            # 模块维度
            mod = r.get("module", "") or r.get("sub_module", "") or "未知"
            if mod:
                facets["module"][mod] = facets["module"].get(mod, 0) + 1

            # 来源维度
            source = r.get("source", "") or "未知"
            if source:
                facets["source"][source] = facets["source"].get(source, 0) + 1

        # 转换为排序后的列表格式
        result = {}
        for dim, counts in facets.items():
            sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            result[dim] = [{"value": k, "count": v} for k, v in sorted_items[:15]]

        return result

    def get_related_searches(self, query: str, limit: int = 6) -> list:
        """获取相关搜索推荐。

        策略：
        1. 基于关键词索引：找与查询共享模块的关键词
        2. 基于向量相似度：找语义相似的 FAQ 标题
        3. 基于搜索热词：找与查询相关的热门搜索

        返回: [{"query": "...", "source": "keyword|vector|hotword"}]
        """
        if not query or len(query) < 2:
            return []

        suggestions = []
        seen = {query}

        # 1. 关键词索引匹配：找与查询关键词共享模块的其他关键词
        tokens = [t.strip() for t in jieba.cut(query) if len(t.strip()) >= 2]
        related_modules = set()
        for token in tokens:
            if token in self.keyword_map:
                for entry in self.keyword_map[token][:3]:
                    related_modules.add(entry.get("module", ""))

        for mod in related_modules:
            for kw, entries in self.keyword_map.items():
                if kw in seen or len(kw) < 2:
                    continue
                for entry in entries:
                    if entry.get("module") == mod and kw != query:
                        suggestions.append({"query": kw, "source": "keyword"})
                        seen.add(kw)
                        break
                if len(suggestions) >= limit:
                    break
            if len(suggestions) >= limit:
                break

        # 2. 向量相似度：找语义相似的 FAQ 标题
        if len(suggestions) < limit and self.vector and self.vector.model:
            try:
                query_emb = self.vector.encode(query)
                faq_titles = [doc.get("title", "") for doc in self.faq_docs if doc.get("title")]
                if faq_titles:
                    # 编码所有 FAQ 标题并计算相似度
                    title_embs = []
                    for title in faq_titles:
                        try:
                            emb = self.vector.encode(title[:128])
                            title_embs.append(emb)
                        except Exception:
                            title_embs.append(None)

                    import numpy as np
                    for i, (title, emb) in enumerate(zip(faq_titles, title_embs)):
                        if emb is None or title in seen:
                            continue
                        try:
                            sim = float(np.dot(query_emb, emb.T)[0][0])
                            if sim > 0.7:
                                suggestions.append({"query": title, "source": "vector"})
                                seen.add(title)
                        except Exception:
                            pass
            except Exception:
                pass

        # 3. FAQ 标题关键词匹配（fallback）
        if len(suggestions) < limit:
            for doc in self.faq_docs:
                title = doc.get("title", "")
                if title in seen or len(title) < 3:
                    continue
                # 检查是否有共享的关键词
                for token in tokens:
                    if token in title:
                        suggestions.append({"query": title, "source": "faq_title"})
                        seen.add(title)
                        break
                if len(suggestions) >= limit:
                    break

        return suggestions[:limit]

    def search(self, query, top=10):
        query = query.strip()
        if not query:
            return {"query": query, "results": [], "suggestion": "请输入查询内容"}

        # 0. 搜索语法解析：检测高级语法（字段过滤、排除、短语）
        parsed = self.query_parser.parse(query)
        has_advanced = self.query_parser.has_advanced_syntax(query)

        # 1. 分词（如果有短语，保留短语不拆分；如果有高级语法，用 raw_query 分词）
        if has_advanced:
            # 高级语法：用解析后的关键词文本分词，短语也加入 tokens
            raw_text = parsed.get("raw_query", "") or query
            tokens = list(jieba.cut(raw_text))
        else:
            tokens = list(jieba.cut(query))
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 1]
        # 添加精确短语作为整体 token
        for phrase in parsed.get("phrases", []):
            if phrase and phrase not in tokens:
                tokens.append(phrase)

        # 1b. 拼写纠错：仅当原始查询无高级语法时触发
        correction = None
        if not has_advanced:
            if self.corrector is None:
                self.corrector = create_corrector(self)
            correction = self.corrector.correct(query)
            if correction and correction.get("has_correction"):
                # 用纠正后的查询重新分词
                corrected_query = correction.get("corrected", query)
                corrected_tokens = list(jieba.cut(corrected_query))
                corrected_tokens = [t.strip() for t in corrected_tokens if len(t.strip()) >= 1]
                # 如果纠正后的分词与原文不同，使用纠正后的分词
                if corrected_tokens != tokens:
                    # 合并原始 token 和纠正 token（保留用户意图）
                    tokens = list(set(tokens + corrected_tokens))

        # 1c. 查询意图检测：识别查询指向的业务模块
        intent_modules = self._detect_intent(query, tokens)

        # 2. 扩展查询词（同义词 + 拼音）
        expanded = self._expand_tokens(tokens)

        # 3. 多源并行搜索：BM25 统一搜文档 + 关键词 + 模块 + 向量
        bm25_results, kw_results, mod_results, vec_results = [], [], [], []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self._search_bm25_unified, query, expanded, 30): 'bm25',
                executor.submit(self._search_keywords, query, expanded): 'kw',
                executor.submit(self._search_modules, query, expanded): 'mod',
                executor.submit(self._search_vector, query, expanded): 'vec',
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = []
                if key == 'bm25':
                    bm25_results = result
                elif key == 'kw':
                    kw_results = result
                elif key == 'mod':
                    mod_results = result
                elif key == 'vec':
                    vec_results = result

        # 4. RRF 融合：BM25 + 关键词 + 向量 → 统一排名
        results = self._rrf_fusion([
            bm25_results,   # 主：BM25 全文搜索（文档+FAQ+报表统一评分）
            kw_results,     # 辅：关键词索引匹配
            mod_results,    # 辅：模块名匹配
            vec_results,    # 辅：语义向量搜索
        ])

        # 3b. 意图模块加权：匹配到的模块结果加分
        if intent_modules:
            for r in results:
                if r.get("module") in intent_modules:
                    r["score"] = r.get("score", 0) + 2

        # 4. 后处理：去重 + 降权 + 时效性 + 多样性
        results = deduplicate(results)
        for r in results:
            if r.get("source") == "keyword_index" and not r.get("path"):
                r["score"] = r.get("score", 0) // 2
        results = self._apply_freshness_boost(results)

        # 4b. 应用高级语法过滤和排除
        if parsed.get("filters"):
            results = self.query_parser.apply_filters(results, parsed["filters"])
        if parsed.get("excludes"):
            results = self.query_parser.apply_excludes(results, parsed["excludes"])

        results = self._apply_diversity(results)

        # 4c. 计算分面聚合（在去重和过滤后）
        facets = self._compute_facets(results)

        # 5. 生成智能问答 - 使用全部结果做深度搜索
        answer = self._generate_answer(query, expanded, results)

        # 6. 构建过程追踪
        process = {
            "layer1_search": {
                "tokens": tokens,
                "expanded_terms": sorted(expanded, key=lambda x: len(x), reverse=True)[:15],
                "sources": {
                    "bm25_unified": len(bm25_results),
                    "keyword_index": len(kw_results),
                    "module_match": len(mod_results),
                    "vector_search": len(vec_results),
                },
                "after_rrf_fusion": len(results),
            },
            "layer2_deep_search": {
                "kb_files_searched": answer.get("_kb_files_searched", []) if answer else [],
                "sections_found": len(answer.get("kb_sections", [])) if answer else 0,
                "top_sections": [
                    {"heading": s["heading"].lstrip("#").strip(), "score": s["score"]}
                    for s in (answer.get("kb_sections", [])[:3] if answer else [])
                ],
            },
            "layer3_answer_gen": {
                "best_section": (answer.get("kb_sections", [{}])[0].get("heading", "").lstrip("#").strip()) if answer and answer.get("kb_sections") else "",
                "has_takeaway": "✏️" in (answer.get("summary", "") if answer else ""),
            } if answer else {},
        }
        if answer:
            answer.pop("_kb_files_searched", None)

        result = {
            "query": query,
            "tokens": tokens,
            "expanded_terms": list(expanded),
            "total": len(results) + (1 if answer else 0),
            "answer": answer,
            "results": results[:top],
            "facets": facets,
            "process": process,
        }

        # 添加拼写纠错建议
        if correction and correction.get("has_correction"):
            result["correction"] = {
                "original": correction["original"],
                "corrected": correction["corrected"],
                "corrections": correction.get("corrections", []),
                "has_correction": True,
            }

        return result

    def _expand_tokens(self, tokens):
        """扩展查询词：加入同义词、拼音、bigram组合、子词拆分"""
        expanded = set(tokens)

        # bigram 组合（如 "预算"+"申报" → "预算申报"）
        for i in range(len(tokens) - 1):
            expanded.add(tokens[i] + tokens[i + 1])
        # 也加入完整查询字符串
        full = "".join(tokens)
        if len(full) <= 10:
            expanded.add(full)

        # 子词拆分：对复合词（如"差旅报销单"），用 lcut_for_search 获取子词
        for token in list(tokens):
            if len(token) >= 3:
                sub_tokens = jieba.lcut_for_search(token)
                sub_tokens = [t.strip() for t in sub_tokens if len(t.strip()) >= 1]
                # 如果子词拆分结果与原 token 不同，说明是复合词，加入子词
                if len(sub_tokens) > 1:
                    for st in sub_tokens:
                        if len(st) >= 1:
                            expanded.add(st)
                    # 也加入子词 bigram
                    for i in range(len(sub_tokens) - 1):
                        expanded.add(sub_tokens[i] + sub_tokens[i + 1])

        # 同义词扩展
        for token in list(expanded):  # 遍历扩展后的全部词（包含子词）
            if token in self.synonyms:
                for alias in self.synonyms[token]:
                    expanded.add(alias)
            # 反向查找：token 是否是某个词的别名
            for key, aliases in self.synonyms.items():
                if token in aliases:
                    expanded.add(key)
                    for a in aliases:
                        expanded.add(a)

        # 拼音首字母扩展（搜索关键词、模块名、菜单名）
        for token in tokens:
            if token.isascii() and token.isalpha():
                token_lower = token.lower()
                # 搜索关键词索引
                for kw in self.keyword_map:
                    py_initials = "".join(
                        p[0] for p in lazy_pinyin(kw, style=Style.FIRST_LETTER)
                    )
                    if py_initials == token_lower:
                        expanded.add(kw)
                # 搜索模块名
                for mod_name in self.module_map:
                    py_initials = "".join(
                        p[0] for p in lazy_pinyin(mod_name, style=Style.FIRST_LETTER)
                    )
                    if py_initials == token_lower:
                        expanded.add(mod_name)
                # 搜索菜单名
                for menu_name in self.menu_map:
                    py_initials = "".join(
                        p[0] for p in lazy_pinyin(menu_name, style=Style.FIRST_LETTER)
                    )
                    if py_initials == token_lower:
                        expanded.add(menu_name)
                # 全拼匹配
                all_terms = list(self.keyword_map.keys()) + list(self.module_map.keys()) + list(self.menu_map.keys())
                for term in all_terms:
                    py_full = "".join(lazy_pinyin(term))
                    if py_full == token_lower:
                        expanded.add(term)

        return expanded

    def _search_keywords(self, query, expanded):
        """在关键词索引中搜索"""
        results = []
        for term in expanded:
            if term in self.keyword_map:
                for entry in self.keyword_map[term]:
                    module_info = self.module_map.get(entry["module"], {})
                    # 评分：精确匹配(15) > bigram匹配(12) > 单token匹配(10) > 同义词(8)
                    if term == query:
                        score = 15
                    elif len(term) >= 3 and term in query:
                        score = 12
                    elif term in query:
                        score = 10
                    else:
                        score = 8
                    results.append({
                        "source": "keyword_index",
                        "match_type": "exact" if term in query else "synonym",
                        "match_term": term,
                        "module": entry["module"],
                        "dept": entry["dept"],
                        "domain": entry["domain"],
                        "kb_path": entry["kb_path"],
                        "note": entry.get("note", ""),
                        "dev_owner": module_info.get("dev_owner", ""),
                        "module_owner": module_info.get("module_owner", ""),
                        "module_file": module_info.get("path", ""),
                        "product": module_info.get("product", ""),
                        "appendix": module_info.get("appendix", ""),
                        "score": score,
                    })
        return results

    def _search_modules(self, query, expanded):
        """在模块文件中搜索（模块名、菜单名、关键词）"""
        results = []
        seen = set()

        for term in expanded:
            # 匹配模块名
            for mod_name, info in self.module_map.items():
                if term in mod_name and mod_name not in seen:
                    seen.add(mod_name)
                    # info 可能是 dict 或 ModuleInfo 对象，统一用 get 安全访问
                    if isinstance(info, dict):
                        results.append({
                            "source": "module_name",
                            "match_type": "fuzzy",
                            "match_term": term,
                            "module": mod_name,
                            "dept": info.get("dept", ""),
                            "domain": info.get("domain", ""),
                            "module_file": info.get("path", ""),
                            "dev_owner": info.get("dev_owner", ""),
                            "module_owner": info.get("module_owner", ""),
                            "product": info.get("product", ""),
                            "appendix": info.get("appendix", ""),
                            "keywords": info.get("keywords", []),
                            "score": 7,
                        })
                    else:
                        # ModuleInfo dataclass
                        results.append({
                            "source": "module_name",
                            "match_type": "fuzzy",
                            "match_term": term,
                            "module": mod_name,
                            "dept": getattr(info, "dept", ""),
                            "domain": getattr(info, "domain", ""),
                            "module_file": getattr(info, "path", ""),
                            "dev_owner": "",
                            "module_owner": "",
                            "product": getattr(info, "product", ""),
                            "appendix": "",
                            "keywords": getattr(info, "keywords", []),
                            "score": 7,
                        })

            # 匹配菜单名
            for menu_name, mod_names in self.menu_map.items():
                if term in menu_name:
                    for mn in mod_names:
                        if mn not in seen:
                            seen.add(mn)
                            info = self.module_map.get(mn, {})
                            results.append({
                                "source": "menu_match",
                                "match_type": "fuzzy",
                                "match_term": term,
                                "menu": menu_name,
                                "module": mn,
                                "dept": info.get("dept", ""),
                                "domain": info.get("domain", ""),
                                "module_file": info.get("path", ""),
                                "dev_owner": info.get("dev_owner", ""),
                                "module_owner": info.get("module_owner", ""),
                                "score": 6,
                            })

        return results

    def _search_bm25_unified(self, query, expanded, top_k=30):
        """BM25 统一搜索：跨所有文档源（KB + FAQ + 报表），同一尺度评分"""
        results = []
        if not self.bm25 or self.bm25.N == 0:
            return results

        # 用扩展词做 BM25 搜索
        bm25_results = self.bm25.search(expanded, k=top_k)

        # 构建 path → doc 查找表
        doc_by_path = {}
        for doc in self.kb_docs:
            doc_by_path[doc.get('path', '')] = doc
        for doc in self.faq_docs:
            doc_by_path[doc.get('path', '')] = doc
        for doc in self.report_docs:
            doc_by_path[doc.get('path', '')] = doc

        for path, bm25_score in bm25_results:
            doc = doc_by_path.get(path, {})
            if not doc:
                continue

            # 根据路径判断来源类型
            if path.startswith('data/faq/'):
                source = 'faq_knowledge'
                match_type = 'faq'
                title = doc.get('title', '')
                faq_id = doc.get('faq_id', '')
            elif path.startswith('data/reports/'):
                source = 'report_data'
                match_type = 'report'
                title = doc.get('title', '')
                faq_id = ''
            else:
                source = 'knowledge_base'
                match_type = 'content'
                title = doc.get('title', '')
                faq_id = ''

            # 提取匹配的关键词
            content_sample = doc.get('content_sample', '')
            matched = [t for t in expanded if t in content_sample]

            # 提取摘要
            snippets = extract_snippets(content_sample, expanded, max_snippets=3)

            results.append({
                "source": source,
                "match_type": match_type,
                "match_terms": matched,
                "path": path,
                "faq_id": faq_id,
                "title": title,
                "dept": doc.get('dept', ''),
                "domain": doc.get('domain', doc.get('sub_module', '')),
                "module": doc.get('module', doc.get('sub_module', '')),
                "snippets": snippets,
                "bm25_score": round(bm25_score, 2),
                "score": 0,  # 后续由 RRF 填充
            })

        return results

    @staticmethod
    def _rrf_fusion(result_lists, k=60):
        """Reciprocal Rank Fusion：将多个排序列表融合为统一排名

        result_lists: list of list of dict, 每个 dict 需有 'path' 键
        k: RRF 常数，默认 60
        """
        scores = {}
        docs = {}

        for rlist in result_lists:
            for rank, r in enumerate(rlist, start=1):
                path = r.get('path', '') or f"{r.get('source','')}:{r.get('title','')}:{rank}"
                rrf = 1.0 / (k + rank)
                scores[path] = scores.get(path, 0) + rrf
                if path not in docs:
                    docs[path] = r
                else:
                    # 保留第一次出现的 doc（通常是 BM25 结果，信息更全）
                    if docs[path].get('bm25_score', 0) == 0 and r.get('bm25_score', 0) > 0:
                        docs[path] = r

        # 按 RRF 分数排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        merged = []
        for path, rrf_score in ranked:
            doc = docs[path]
            doc['score'] = round(rrf_score * 100, 1)  # 放大到可读范围
            doc['rrf_score'] = round(rrf_score, 4)
            # 确保有 title（向量搜索和关键词索引结果可能没有）
            if not doc.get('title'):
                doc['title'] = doc.get('module', '') or doc.get('note', '') or doc.get('path', '') or '(无标题)'
            merged.append(doc)

        return merged
        """在知识库文档中搜索（内容匹配 + 标题匹配，与 FAQ 评分对齐）"""
        results = []
        for doc in self.kb_docs:
            score = 0
            matched = []

            # 1. 标题匹配（标题是最精确的匹配，权重高）
            title = doc.get("title", "")
            title_matched = 0
            for term in expanded:
                if term in title:
                    title_matched += 1
            if title_matched > 0:
                score += title_matched * 5 + (title_matched * 2)

            # 2. 内容匹配
            for term in expanded:
                if term in doc["content_sample"]:
                    score += 1
                    matched.append(term)

            if score > 0:
                snippets = extract_snippets(doc["content_sample"], expanded, max_snippets=2)
                results.append({
                    "source": "knowledge_base",
                    "match_type": "content",
                    "match_terms": matched,
                    "path": doc["path"],
                    "title": doc["title"],
                    "dept": doc["dept"],
                    "domain": doc["domain"],
                    "snippets": snippets,
                    "score": score * 3,  # 移除上限，与 FAQ 对齐
                })
        return results

    def _search_reports(self, query, expanded):
        """在报表数据中搜索"""
        results = []
        for doc in self.report_docs:
            score = 0
            matched = []
            for term in expanded:
                if term in doc["content_sample"]:
                    score += 1
                    matched.append(term)
            if score > 0:
                snippets = extract_snippets(doc["content_sample"], expanded, max_snippets=2)
                results.append({
                    "source": "report_data",
                    "match_type": "content",
                    "match_terms": matched,
                    "path": doc["path"],
                    "title": doc["title"],
                    "snippets": snippets,
                    "score": score * 3,  # 移除上限，与 KB 文档对齐
                })
        return results

    def _search_faq(self, query, expanded):
        """在 FAQ 知识库中搜索（结构化匹配 + 内容匹配，结果优先）"""
        results = []
        for doc in self.faq_docs:
            score = 0
            matched = []

            # 1. 关键词匹配（frontmatter keywords，高权重）
            for kw in doc.get("keywords", []):
                for term in expanded:
                    if term == kw:
                        score += 5  # 精确匹配
                    elif len(term) >= 3 and term in kw:
                        score += 3  # 搜索词是关键词的子串（如"接种证"在"接种证打印"中）
                    elif len(kw) >= 3 and kw in term:
                        score += 1  # 关键词是搜索词的子串（弱匹配，如关键词"支付"在搜索词"支付限额"中）

            # 2. 标题匹配（标题是最精确的匹配，权重最高）
            title = doc.get("title", "")
            title_matched = 0
            for term in expanded:
                if term in title:
                    title_matched += 1
            if title_matched > 0:
                # 标题匹配越多，加分越多（非线性加权）
                score += title_matched * 5 + (title_matched * 2)  # 基础5分 + 额外2分/词

            # 3. 内容匹配（基础权重）
            for term in expanded:
                if term in doc["content_sample"]:
                    score += 1
                    matched.append(term)

            if score > 0:
                snippets = extract_snippets(doc["content_sample"], expanded, max_snippets=3)
                # FAQ 有结构化优势（关键词+标题），不再额外加基础分，让评分公平竞争
                results.append({
                    "source": "faq_knowledge",
                    "match_type": "faq",
                    "match_terms": matched,
                    "path": doc["path"],
                    "faq_id": doc.get("faq_id", ""),
                    "title": doc["title"],
                    "dept": doc["dept"],
                    "domain": doc["sub_module"],
                    "module": doc.get("module", doc.get("sub_module", "")),
                    "snippets": snippets,
                    "score": score,
                })
        return results

    def _search_vector(self, query, expanded):
        """向量语义检索 KB 段落"""
        results = []
        if self.vector is None or self.vector.index is None or self.vector.model is None:
            return results

        vec_results = self.vector.search(query, k=10)
        for sec in vec_results:
            results.append({
                'source': 'vector_search',
                'match_type': 'semantic',
                'match_term': query,
                'path': sec['path'],
                'heading': sec['heading'],
                'snippets': [sec['content'][:200]],
                'score': sec.get('score', 0) * 10,  # 移除上限，让语义匹配结果公平竞争
            })

        return results

    # -------- answer generation --------

    def _generate_answer(self, query, expanded, results):
        """深度搜索知识库，提取相关内容生成智能回答"""
        if not results:
            return None

        # 收集所有匹配的关键词
        matched_keywords = []
        for r in results:
            if r.get("source") == "keyword_index":
                matched_keywords.append(r.get("match_term", ""))

        # 收集所有匹配的模块
        matched_modules = []
        seen_mod = set()
        for r in results:
            m = r.get("module")
            if m and m not in seen_mod:
                seen_mod.add(m)
                info = self.module_map.get(m, {})
                matched_modules.append({
                    "name": m,
                    "dept": info.get("dept", ""),
                    "domain": info.get("domain", ""),
                    "dev_owner": info.get("dev_owner", ""),
                    "module_owner": info.get("module_owner", ""),
                    "module_file": info.get("path", ""),
                })

        # 深度搜索知识库：读取匹配的 KB 文件全文，提取相关段落
        # 收集关键词匹配的模块目录，优先搜索
        priority_dirs = []
        for r in results:
            if r.get("source") == "keyword_index" and r.get("kb_path"):
                kb_dir = PROJECT_DIR / r["kb_path"]
                if kb_dir.exists():
                    priority_dirs.append(kb_dir)
        kb_sections, kb_files_searched, chapter_group = self._deep_search_kb(
            query, expanded, results, priority_dirs
        )

        # 搜索原始产品文档
        raw_doc_sections = self._search_raw_docs(query, expanded)

        # 搜索报表中的相关内容
        report_sections = self._search_reports_deep(query, expanded, results)

        # 从 KB 搜索结果推断最佳部门
        kb_dept = self._infer_dept_from_kb(kb_sections, raw_doc_sections)

        # 选择最佳模块：优先 keyword_index 匹配，其次 KB 部门匹配的模块
        best_module, best_info = self._select_best_module(
            matched_modules, results, kb_dept
        )

        answer = {
            "source": "qa_answer",
            "question": query,
            "module": best_module,
            "dept": best_info.get("dept", ""),
            "domain": best_info.get("domain", ""),
            "dev_owner": best_info.get("dev_owner", ""),
            "module_owner": best_info.get("module_owner", ""),
            "module_file": best_info.get("module_file", ""),
            "matched_keywords": matched_keywords[:8],
            "matched_modules": matched_modules[:5],
            "kb_sections": kb_sections,
            "raw_doc_sections": raw_doc_sections,
            "report_sections": report_sections,
            "_kb_files_searched": kb_files_searched,
            "score": 20,
        }

        # 生成回答摘要文本
        # 验证：如果最佳章节来自不同部门，不使用章节组
        if chapter_group and best_info:
            cg_dept = self._infer_dept_from_path(chapter_group["path"])
            if cg_dept and best_info.get("dept") and cg_dept != best_info.get("dept"):
                chapter_group = None  # 章节组与最佳模块部门不匹配，回退

        answer["summary"] = self._build_summary(
            query, matched_modules, kb_sections, raw_doc_sections, report_sections, chapter_group
        )

        # 提取图片（从最佳匹配段落）
        best_kb = kb_sections[0] if kb_sections else None
        answer["images"] = best_kb.get("images", []) if best_kb else []

        return answer

    def build_claude_prompt(self, query, results):
        """构建结构化 Claude API prompt。

        返回 dict: {"system": str, "messages": [{"role": "user", "content": str}]}
        """
        # 收集匹配的模块信息
        matched_modules = []
        seen_mod = set()
        for r in results:
            m = r.get('module')
            if m and m not in seen_mod:
                seen_mod.add(m)
                info = self.module_map.get(m, {})
                matched_modules.append({
                    'name': m,
                    'dept': info.get('dept', ''),
                    'domain': info.get('domain', ''),
                    'dev_owner': info.get('dev_owner', ''),
                    'module_owner': info.get('module_owner', ''),
                })

        # 深度搜索 KB
        tokens = list(jieba.cut(query))
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 1]
        expanded = self._expand_tokens(tokens) if tokens else set()

        priority_dirs = []
        for r in results:
            if r.get("source") == "keyword_index" and r.get("kb_path"):
                kb_dir = PROJECT_DIR / r["kb_path"]
                if kb_dir.exists():
                    priority_dirs.append(kb_dir)

        kb_sections, kb_files_searched, _ = self._deep_search_kb(
            query, expanded, results, priority_dirs
        )
        raw_doc_sections = self._search_raw_docs(query, expanded)
        report_sections = self._search_reports_deep(query, expanded, results)

        # 结构化 system prompt
        system = """你是产品知识库助手，服务于数智财务（浙里报/孵化业务/徽报账）、电子档案、免疫规划、数字化支撑等全部业务模块的用户咨询。

## 回答策略
根据问题类型采用不同策略：
- **功能咨询**（怎么用/在哪里/如何操作）：说明功能位置、菜单路径、操作步骤，按步骤编号列出
- **问题排查**（报错/不能用/故障）：列出常见原因、排查步骤、负责人
- **概念解释**（什么是/功能说明/介绍）：给出定义、适用范围、相关配置
- **模块查询**（谁负责/归属哪个模块）：给出模块名、部门、负责人

## 回答格式要求
1. 先给出 1-2 句明确结论
2. 如有操作步骤，用编号清晰列出每一步
3. 如有注意事项/限制条件，单独列出
4. 结尾标注信息来源文档路径

## 重要规则
- 用中文回答，详细、专业、完整
- 如果文档内容足够回答，直接给出准确答案
- 如果文档内容部分相关但不完整，先给出文档中的信息，再结合你的知识补充
- 如果文档完全不相关，不要编造，诚实说明

## 在回答末尾输出以下 JSON（不要放在 markdown 代码块中，直接输出）
{"keywords_to_add": ["建议补充的关键词1", "关键词2"], "module": "所属模块名", "confidence": "high|medium|low"}
"""

        # 组装 user message
        user_parts = [f"## 用户问题\n{query}\n"]

        if matched_modules:
            user_parts.append("## 匹配的模块")
            for mod in matched_modules[:3]:
                user_parts.append(
                    f"- {mod['name']}（{mod['dept']}/{mod['domain']}）"
                    f" | 研发: {mod.get('dev_owner', '未知')}"
                    f" | 模块负责人: {mod.get('module_owner', '未知')}"
                )
            user_parts.append("")

        if kb_sections:
            seen_files = set()
            full_docs = []
            for sec in kb_sections:
                path = sec.get('path', '')
                if path and path not in seen_files:
                    seen_files.add(path)
                    try:
                        full_path = PROJECT_DIR / path
                        if full_path.exists():
                            full_content = full_path.read_text(encoding='utf-8')
                            if len(full_content) > 12000:
                                full_content = full_content[:12000] + '\n\n...(内容过长，已截断)...'
                            full_docs.append({
                                'path': path,
                                'content': full_content,
                                'score': sec.get('score', 0),
                            })
                    except Exception:
                        pass
                if len(full_docs) >= 3:
                    break

            user_parts.append("## 知识库文档（完整内容）")
            for i, doc in enumerate(full_docs, 1):
                rel_path = doc['path'].replace('2026产品业务知识库/', '').replace('projects/knowledge-base/knowledge/', '')
                user_parts.append(f"### 文档{i}: {rel_path}")
                user_parts.append(doc['content'])
                user_parts.append("")

        if raw_doc_sections:
            user_parts.append("## 原始产品文档")
            for i, sec in enumerate(raw_doc_sections[:2], 1):
                heading = sec['heading'].lstrip('#').strip()
                user_parts.append(f"### [{i}] {heading}")
                user_parts.append(sec['content'][:1000])
                user_parts.append("")

        if report_sections:
            user_parts.append("## 历史报表数据")
            for i, sec in enumerate(report_sections[:1], 1):
                user_parts.append(f"### [{i}] {sec['heading'].lstrip('#').strip()}")
                user_parts.append(sec['content'][:800])
            user_parts.append("")

        user_parts.append("请根据以上文档内容回答用户问题。")

        return {
            'system': system,
            'messages': [{'role': 'user', 'content': '\n'.join(user_parts)}],
            '_meta': {
                'matched_modules': matched_modules,
                'kb_sections': kb_sections,
                'kb_files_searched': [str(p) for p in kb_files_searched],
            },
        }

    def build_rag_prompt(self, query, results):
        """构建 RAG 增强 prompt，侧重检索增强和来源引用。

        返回 dict: {"system": str, "messages": [...], "sources": [...]}
        """
        # 过滤：优先 FAQ 和知识库文档，排除无内容的 keyword_index 结果
        faq_results = [r for r in results if r.get('source') == 'faq_knowledge' and r.get('path')]
        kb_results = [r for r in results if r.get('source') in ('kb_document', 'report_data') and r.get('path')]
        other_results = [r for r in results if r not in faq_results and r not in kb_results and r.get('path')]

        # 排序：FAQ 优先，然后 KB 文档，然后其他
        sorted_results = faq_results + kb_results + other_results
        top_results = sorted_results[:5]

        sources = []
        context_parts = []

        for i, r in enumerate(top_results):
            path = r.get('path', '')
            title = r.get('title', '')
            dept = r.get('dept', '')
            faq_id = r.get('faq_id', '')
            snippets = r.get('snippets', [])
            snippet = snippets[0] if snippets else r.get('snippet', '')[:300]

            # 跳过无标题且无路径的结果
            if not title and not path:
                continue
            if not title:
                title = path.split('/')[-1].replace('.md', '')

            source = {
                'index': len(sources) + 1,
                'title': title,
                'path': path,
                'dept': dept,
                'faq_id': faq_id,
                'snippet': snippet[:200] if snippet else '',
            }
            sources.append(source)

            # 读取完整文档内容
            full_content = ""
            if path:
                full_path = PROJECT_DIR / path
                if full_path.exists():
                    try:
                        full_content = full_path.read_text(encoding='utf-8')
                        if len(full_content) > 8000:
                            full_content = full_content[:8000] + '\n...(内容过长已截断)'
                    except Exception:
                        full_content = snippet

            context_parts.append(
                f"### 来源 [{source['index']}]: {title}\n"
                f"路径: {path}\n"
                f"{'FAQ ID: ' + faq_id + ' | ' if faq_id else ''}部门: {dept}\n"
                f"内容:\n{full_content or snippet}\n"
            )

        system = """你是产品知识库智能助手，服务于数智财务（浙里报/孵化业务/徽报账）、电子档案、免疫规划、数字化支撑等业务模块。

## 回答规则
1. **优先使用知识库文档中的信息**，不要编造。如果文档有明确答案，直接引用并标注来源编号 [1] [2]
2. 如果文档部分相关但不完整，先给出文档信息，再说明"其他情况建议提交工单进一步排查"
3. 如果所有文档都不相关，诚实说明"当前知识库中未找到直接相关的信息，建议提交工单或联系技术支持"
4. 用中文回答，详细、专业、步骤清晰
5. 如有操作步骤，用编号列出

## 引用格式
- 每个要点后标注来源：如"银行回单通过浙里办票同步到浙里报 [1]"
- 多来源提到同一信息时标注多个编号 [1][3]

## 回答末尾输出（JSON 格式，不要放在代码块中）
{"sources": [{"index": 1, "title": "...", "relevance": "high|medium|low"}]}
"""

        user_content = f"## 用户问题\n{query}\n\n"
        if context_parts:
            user_content += "## 知识库检索结果\n\n" + "\n---\n".join(context_parts)
            user_content += "\n\n请基于以上知识库文档回答用户问题，标注来源编号。"
        else:
            user_content += "\n（知识库中未找到相关文档，请基于你的知识简要回答，并建议用户提交工单获取更准确的信息）\n"

        return {
            'system': system,
            'messages': [{'role': 'user', 'content': user_content}],
            'sources': sources,
        }

    def _deep_search_kb(self, query, expanded, results, priority_dirs=None):
        """两阶段深度搜索 KB 文档。

        S1: BM25 文档级筛选 → Top-10 文档
        S2: 段落级精细匹配 → Top-5 段落
        多维评分：关键词 40% + 向量相似度 35% + 位置/标题 15% + 新鲜度 10%
        """
        sections = []
        search_terms = list(expanded) + [query]

        # S1: BM25 文档级筛选
        if self.bm25 and self.bm25.N > 0:
            doc_results = self.bm25.search(search_terms, k=10)
            doc_paths = [p for p, score in doc_results]
        else:
            # Fallback: 使用原有的 priority_dirs + kb_paths 逻辑
            doc_paths = self._collect_kb_paths_fallback(results, priority_dirs)

        # 预计算 query 向量，用于 S2 段落级语义匹配
        query_emb = None
        if self.vector and self.vector.model and self.vector.index is not None:
            try:
                query_emb = self.vector.encode(query)
            except Exception:
                pass

        # S2: 段落级精细匹配（多维评分）
        for path in doc_paths[:10]:
            full_path = PROJECT_DIR / path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                continue

            segments = self._split_by_heading(content, path)
            for seg in segments:
                if seg['heading'] == '(文档开头)':
                    continue

                # 1. 关键词匹配分数（40%）- 归一化到 [0, 1]
                keyword_score = self._match_score(seg['content'], search_terms)
                keyword_norm = min(keyword_score / 10.0, 1.0)

                # 2. 向量语义相似度（35%）
                vector_sim = 0.0
                if query_emb is not None and len(seg['content']) >= 50:
                    try:
                        seg_emb = self.vector.encode(seg['content'][:512])
                        faiss.normalize_L2(seg_emb)
                        vector_sim = float(np.dot(query_emb, seg_emb.T)[0][0])
                    except Exception:
                        pass

                # 3. 位置/标题匹配（15%）- 归一化到 [0, 1]
                heading_score = self._match_score(seg['heading'], search_terms) * 3
                parent_heading_score = self._match_score(
                    seg.get('parent_heading', ''), search_terms
                ) * 1.5
                is_faq = any(kw in seg['heading'] for kw in ['FAQ', '常见问题', '故障', '排查'])
                faq_bonus = 2.0 if is_faq else 0
                position_score = min((heading_score + parent_heading_score + faq_bonus) / 10.0, 1.0)

                # 4. 文档新鲜度（10%）
                doc_date = self._extract_date_from_path(path)
                freshness = 1.0
                if doc_date:
                    days_ago = (date.today() - doc_date).days
                    if days_ago <= 90:
                        freshness = 1.0
                    elif days_ago <= 365:
                        freshness = 0.8
                    else:
                        freshness = max(0.5, 1.0 - (days_ago - 365) / 365)

                total_score = (
                    keyword_norm * 0.40
                    + vector_sim * 0.35
                    + position_score * 0.15
                    + freshness * 0.10
                )

                # 5. 主题不匹配惩罚：段落标题/内容与查询指向不同业务场景时降权
                # 例如查询"差旅报销单"但标题是"采购报销单关联附件优化"→ 惩罚
                is_mismatch, topic_penalty = self._check_topic_mismatch(
                    query, seg['heading'], seg['content']
                )
                if is_mismatch:
                    total_score *= (1.0 - topic_penalty)  # 默认 0.5 惩罚，即分数减半

                if total_score >= 0.15:
                    images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', seg['content'])
                    sections.append({
                        'path': path,
                        'heading': seg['heading'],
                        'parent_heading': seg.get('parent_heading', ''),
                        'content': seg['content'][:1500],
                        'images': [{'alt': alt, 'src': src} for alt, src in images],
                        'score': round(total_score, 3),
                        'line_start': seg.get('line_start', 0),
                    })

        sections.sort(key=lambda s: s['score'], reverse=True)

        chapter_group = None
        if sections:
            chapter_group = self._build_chapter_group(sections[0])

        return sections[:5], doc_paths[:10], chapter_group

    def _collect_kb_paths_fallback(self, results, priority_dirs=None):
        """Fallback: 当 BM25 不可用时，从 results 和 priority_dirs 收集 KB 文档路径"""
        paths = []
        if priority_dirs:
            for d in priority_dirs:
                for f in sorted(d.rglob('*.md'), reverse=True):  # reverse for date-descending filenames like 2026-07-07_*.md
                    paths.append(str(f.relative_to(PROJECT_DIR)))
        for r in results:
            if r.get('source') == 'knowledge_base' and r.get('path'):
                if r['path'] not in paths:
                    paths.append(r['path'])
        # Also search KB directories linked to matched modules
        for r in results:
            module = r.get('module')
            if module:
                info = self.module_map.get(module, {})
                dept = info.get('dept', '')
                domain = info.get('domain', '')
                if dept and domain:
                    kb_dir = self._domain_to_kb_dir(dept, domain)
                    if kb_dir and kb_dir.exists():
                        for f in kb_dir.rglob('*.md'):
                            fpath = str(f.relative_to(PROJECT_DIR))
                            if fpath not in paths:
                                paths.append(fpath)
        return paths

    def _extract_date_from_path(self, path):
        """从文件路径中提取日期，如 2026-07-07_版本迭代.md → date(2026, 7, 7)"""
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', path)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    def _search_raw_docs(self, query, expanded):
        """搜索原始产品文档。
        排序策略：优先按文件名中的日期排序（最新日期在前），确保最新文档被优先搜索。
        """
        # 优先新路径，兼容旧路径
        raw_dir_new = DATA_DIR / "raw-docs"
        raw_dir = raw_dir_new if raw_dir_new.exists() else None
        if not raw_dir.exists():
            return []

        sections = []
        search_terms = list(expanded) + [query]

        # 按日期降序排列文件（最新在前），文件名如 2026-07-07.md
        all_files = sorted(raw_dir.rglob("*.md"), reverse=True)

        for f in all_files[:15]:  # 上限从 8 提升到 15
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            segments = self._split_by_heading(content, str(f.relative_to(PROJECT_DIR)))
            for seg in segments:
                if seg["heading"] == "(文档开头)" and len(seg["content"]) < 200:
                    continue
                score = self._match_score(seg["content"], search_terms)
                heading_score = self._match_score(seg["heading"], search_terms) * 2
                score += heading_score
                if score >= 2:
                    sections.append({
                        "path": str(f.relative_to(PROJECT_DIR)),
                        "heading": seg["heading"],
                        "content": seg["content"][:1500],
                        "score": score,
                        "line_start": seg.get("line_start", 0),
                    })

        sections.sort(key=lambda s: (
            s["heading"] != "(文档开头)" and self._match_score(s["heading"], search_terms) > 0,
            self._match_score(s.get("parent_heading", ""), search_terms),
            s["score"]
        ), reverse=True)
        return sections[:3]

    def _search_reports_deep(self, query, expanded, results):
        """搜索报表中的相关内容"""
        sections = []
        search_terms = list(expanded) + [query]

        report_paths = set()
        for r in results:
            if r.get("source") == "report_data" and r.get("path"):
                report_paths.add(r["path"])

        for path in sorted(report_paths)[:3]:
            full_path = PROJECT_DIR / path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except Exception:
                continue
            segments = self._split_by_heading(content, path)
            for seg in segments:
                score = self._match_score(seg["content"], search_terms)
                if score >= 2:
                    sections.append({
                        "path": path,
                        "heading": seg["heading"],
                        "content": seg["content"][:600],
                        "score": score,
                        "line_start": seg.get("line_start", 0),
                    })

        sections.sort(key=lambda s: (
            s["heading"] != "(文档开头)" and self._match_score(s["heading"], search_terms) > 0,
            self._match_score(s.get("parent_heading", ""), search_terms),
            s["score"]
        ), reverse=True)
        return sections[:3]

    def _split_by_heading(self, content, path):
        """按 ### 标题将文档拆分为段落，记录行号和父级章节标题"""
        lines = content.split("\n")
        segments = []
        current_heading = "(文档开头)"
        current_section = "(文档开头)"  # 最近的章节级 ### 标题（如 一、二、三）
        current_content = []
        current_line = 1
        heading_line = 1

        # 章节标题模式：匹配 "### 一、XXX"、"### 二、XXX" 等
        section_pattern = re.compile(r"^###\s+[一二三四五六七八九十]+[、．.]")

        for line in lines:
            if re.match(r"^##\s+", line):
                current_section = line.strip()
            elif re.match(r"^###\s+", line):
                if current_content:
                    text = "\n".join(current_content).strip()
                    if len(text) > 20:
                        segments.append({
                            "heading": current_heading,
                            "parent_heading": current_section,
                            "content": text,
                            "line_start": heading_line,
                        })
                current_heading = line.strip()
                current_content = []
                heading_line = current_line
                # 如果是章节级标题，更新 current_section
                if section_pattern.match(line):
                    current_section = line.strip()
            else:
                current_content.append(line)
            current_line += 1

        # 最后一段
        if current_content:
            text = "\n".join(current_content).strip()
            if len(text) > 20:
                segments.append({
                    "heading": current_heading,
                    "parent_heading": current_section,
                    "content": text,
                    "line_start": heading_line,
                })

        return segments

    # 高频通用词列表，这些词在大量文档中出现，匹配时降低权重
    COMMON_TERMS = {
        "信息", "操作", "管理", "配置", "查询", "设置", "数据", "统计",
        "记录", "维护", "处理", "功能", "页面", "按钮", "点击", "进入",
        "怎么", "如何", "什么", "可以", "是否", "支持", "有没有",
        "显示", "展示", "使用", "选择", "添加", "删除", "修改", "编辑",
        "列表", "详情", "新增", "创建", "保存", "提交", "取消", "确认",
        "搜索", "筛选", "导出", "导入", "下载", "上传", "预览", "打印",
        "系统", "单位", "用户", "角色", "权限", "菜单", "部门", "人员",
        "说明", "描述", "备注", "内容", "规则", "逻辑", "流程", "状态",
        "执行", "发布", "版本", "更新", "优化", "修复", "新增功能",
    }

    # 业务场景关键词：用于判断查询和段落标题是否指向同一业务主题
    # 当查询和标题各自包含不同的场景关键词时，说明段落内容与查询不相关
    BUSINESS_SCENARIO_KEYWORDS = {
        # 报销单类型
        "差旅报销单", "差旅报销", "差旅申请单", "差旅", "出差",
        "采购报销单", "采购", "通用采购", "办公用品",
        "会议报销单", "会议", "接待",
        "出国报销单", "出国", "因公出国",
        "公务用车", "用车", "维修", "租赁",
        # 通用业务场景
        "报销单", "申请单", "报销", "培训", "劳务",
        "咨询", "印刷", "物业", "借款", "还款", "预付款", "保证金",
        "合同", "兑付", "兑付报销", "一般事项", "专项支出", "工程", "资产",
        "收入", "预算", "指标", "用款计划", "支付申请",
        # 配置/管理类
        "关账", "限制报销", "发票后补", "票据信息", "凭证",
        # 操作类
        "创建报销单", "批量报销", "财务审核", "出纳结算",
    }

    def _match_score(self, text, terms):
        """计算文本与搜索词的匹配分数，高频通用词降权"""
        score = 0
        for term in terms:
            if len(term) < 2:
                continue
            count = text.count(term)
            if count > 0:
                # 高频通用词权重减半，领域特有词保持原权重
                weight = 0.5 if term in self.COMMON_TERMS else 1.0
                score += min(count, 3) * weight
        return score

    def _extract_topic_keywords(self, text):
        """从文本中提取业务场景关键词，用于判断段落主题是否与查询相关。

        返回 set of str，如 {"差旅", "报销单"} 或 {"采购", "报销单"}。
        当查询和段落标题各自包含不同的场景关键词时，说明段落讲的是另一个主题。
        """
        tokens = set(jieba.cut(text))
        tokens = {t.strip() for t in tokens if len(t.strip()) >= 2}
        return tokens & self.BUSINESS_SCENARIO_KEYWORDS

    def _check_topic_mismatch(self, query, heading, content=""):
        """检查段落标题/内容与查询是否指向不同业务主题。

        返回 (is_mismatch: bool, penalty: float)

        策略：
        1. 标题是段落主题的最强信号。如果标题明确指向另一个业务场景，
           即使正文中提及查询关键词（作为背景/对比），也应判定为不匹配。
        2. 当查询和标题各自包含不同的场景关键词时，即使有共同词（如"报销单"），
           也应判定为不匹配（如"差旅报销单" vs "采购报销单"）。
        3. 只有当标题中无场景关键词时，才回退检查内容。
        """
        query_topics = self._extract_topic_keywords(query)

        if not query_topics:
            return False, 0.0  # 查询中无业务场景关键词，不做主题判断

        heading_topics = self._extract_topic_keywords(heading)

        if heading_topics:
            # 标题中有场景关键词 → 以标题为准
            common = query_topics & heading_topics
            query_specific = query_topics - heading_topics
            heading_specific = heading_topics - query_topics

            if common:
                # 有共同词，但需要检查是否有冲突的场景词
                # 例如：查询"差旅报销单" vs 标题"采购报销单" → 共同词"报销单"
                # 但"差旅"≠"采购"，应判定为不匹配
                if query_specific and heading_specific:
                    # 双方各有不同的场景词 → 不匹配
                    return True, 0.5
                # 查询有额外场景词，但标题中的场景词都是查询的子集 → 可能匹配
                # 检查查询特定词是否直接出现在标题中
                for qt in query_specific:
                    if qt in heading:
                        continue  # 查询词出现在标题中，可能匹配
                # 所有查询特定词都不在标题中，检查是否都在内容中
                if query_specific and not heading_specific:
                    return False, 0.0  # 标题场景词是查询的子集，可能匹配
                return False, 0.0

            # 无共同词，检查是否查询主题词作为子串出现在标题中
            for qt in query_topics:
                if qt in heading:
                    return False, 0.0
            # 标题明确指向不同主题 → 强不匹配
            return True, 0.5

        # 标题中无场景关键词 → 回退检查内容
        if not content:
            return False, 0.0

        content_topics = self._extract_topic_keywords(content[:500])

        if not content_topics:
            # 内容和标题都无场景关键词，检查查询主题词是否直接出现
            for qt in query_topics:
                if qt in heading or qt in content[:500]:
                    return False, 0.0
            return False, 0.0

        # 内容有场景关键词，检查是否与查询一致
        if query_topics & content_topics:
            return False, 0.0  # 内容与查询主题一致

        # 查询主题词是否直接出现在内容中
        for qt in query_topics:
            if qt in content[:500]:
                return False, 0.0

        return True, 0.5

    def _domain_to_kb_dir(self, dept, domain):
        """将部门+业务域映射到知识库目录"""
        mapping = {
            ("数智财务组", "浙里报"): KB_DIR / "数智财务组" / "浙里报",
            ("数智财务组", "孵化业务"): KB_DIR / "数智财务组" / "孵化业务",
            ("数智财务组", "徽报账"): KB_DIR / "数智财务组" / "徽报账",
            ("数智财务组", "直属"): KB_DIR / "数智财务组" / "数智财务组-直属",
            ("电子档案组", "电子档案组"): KB_DIR / "电子档案组",
            ("免疫规划组", "免疫规划组"): KB_DIR / "免疫规划组",
            ("数字化支撑组", "数字化支撑组"): KB_DIR / "数字化支撑组",
        }
        return mapping.get((dept, domain))

    def _infer_dept_from_kb(self, kb_sections, raw_doc_sections):
        """从 KB 搜索结果推断最相关的部门"""
        dept_scores = defaultdict(int)
        for s in kb_sections:
            path = s.get("path", "")
            # 路径格式: 2026产品业务知识库/{部门}/...
            parts = path.split("/")
            if len(parts) >= 2:
                dept = parts[1]  # 部门名
                dept_scores[dept] += s.get("score", 0)
        for s in raw_doc_sections:
            path = s.get("path", "")
            parts = path.split("/")
            if len(parts) >= 2:
                dept = parts[1]
                dept_scores[dept] += s.get("score", 0)
        if dept_scores:
            return max(dept_scores, key=dept_scores.get)
        return ""

    def _infer_dept_from_path(self, path):
        """从文件路径推断部门"""
        if not path:
            return ""
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[1]
        return ""

    def _select_best_module(self, matched_modules, results, kb_dept):
        """选择最佳模块：优先 keyword_index 匹配，其次 KB 部门匹配。
        改进：当有多个 keyword_index 匹配时，优先选择与查询主题最相关的模块。
        """
        if not matched_modules:
            return "", {}

        # 优先：keyword_index 匹配的模块
        kw_modules = []
        for r in results:
            if r.get("source") == "keyword_index":
                kw_modules.append(r.get("module"))

        if kw_modules:
            # 收集查询中的业务场景关键词，用于判断哪个模块更相关
            query_topics = self._extract_topic_keywords(
                " ".join(r.get("match_term", "") for r in results)
            )

            # 对 keyword_index 匹配的模块打分
            best_mod = None
            best_score = -1
            for mod in matched_modules:
                if mod["name"] not in kw_modules:
                    continue
                score = 0
                # 模块名匹配查询主题词
                mod_text = mod["name"] + mod.get("domain", "") + mod.get("dept", "")
                for qt in query_topics:
                    if qt in mod_text:
                        score += 3
                # 模块的 domain/dept 与 KB 推断的部门一致
                if kb_dept and mod.get("dept") == kb_dept:
                    score += 2
                # 模块名精确出现在查询词中
                for r in results:
                    if r.get("source") == "keyword_index" and r.get("match_term") in mod["name"]:
                        score += 1
                if score > best_score:
                    best_score = score
                    best_mod = mod

            if best_mod and best_score > 0:
                return best_mod["name"], best_mod

            # 如果主题评分无差异，退回使用第一个 keyword_index 匹配
            for mod in matched_modules:
                if mod["name"] in kw_modules:
                    return mod["name"], mod

        # 其次：KB 部门匹配的模块
        if kb_dept:
            for mod in matched_modules:
                if mod.get("dept") == kb_dept:
                    return mod["name"], mod

        # 再次：KB 深度搜索中出现的模块
        for r in results:
            if r.get("source") == "knowledge_base" and r.get("dept") == kb_dept:
                for mod in matched_modules:
                    if mod.get("dept") == kb_dept:
                        return mod["name"], mod

        # 兜底：第一个模块
        return matched_modules[0]["name"], matched_modules[0]

    def _build_chapter_group(self, best_section):
        """为最佳匹配段落构建章节组：读取完整文档，返回同父章节下所有子节"""
        path = best_section.get("path", "")
        parent = best_section.get("parent_heading", "")
        if not path or not parent or parent == "(文档开头)":
            return None

        # 只处理真正的章节标题（如 "### 二、人脸采集能力"）
        if not re.match(r"[一二三四五六七八九十]+[、．.]", parent.lstrip("#").strip()):
            return None

        full_path = PROJECT_DIR / path
        if not full_path.exists():
            return None

        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            return None

        segments = self._split_by_heading(content, path)

        # 元数据章节关键词，这些不应该是业务内容
        META_KEYWORDS = ["模块基础信息", "双向链接", "版本迭代时间线", "总目录"]

        children = []
        for seg in segments:
            if seg.get("parent_heading") == parent:
                heading_text = seg["heading"].lstrip("#").strip()
                # 跳过元数据子节
                if any(kw in heading_text for kw in META_KEYWORDS):
                    continue
                children.append({
                    "heading": heading_text,
                    "content": seg["content"],
                    "line_start": seg.get("line_start", 0),
                })

        if not children:
            return None

        return {
            "parent_heading": parent.lstrip("#").strip(),
            "path": path,
            "children": children,
            "score": best_section.get("score", 0),
        }

    def _build_summary(self, query, matched_modules, kb_sections,
                       raw_doc_sections, report_sections, chapter_group=None):
        """快速摘要：只做模块定位 + 关键信息提取，完整回答交给 Claude。

        精简为 ~50 行，仅做 3 件事：
        1. 模块定位
        2. 提取最佳段落前 200 字
        3. 组装返回
        """
        parts = []

        # 判断问题类型
        is_how = any(kw in query for kw in ['怎么', '如何', '怎样', '怎么办', '操作'])
        is_what = any(kw in query for kw in ['什么是', '是什么', '功能说明', '介绍'])
        is_yes_no = any(kw in query for kw in ['可以', '能不能', '是否', '支持', '有没有', '会不会'])

        if is_yes_no:
            parts.append('✅ **支持。**' if any(
                kw in (kb_sections[0]['content'] if kb_sections else '')
                for kw in ['支持', '新增', '增加', '可以']
            ) else '❌ **暂不支持。**')
        elif is_how:
            parts.append(f'🔧 **关于「{query}」的处理方案：**')
        elif is_what:
            parts.append(f'📖 **关于「{query}」的说明：**')
        else:
            parts.append(f'📖 **查询结果：**')

        # 模块定位
        if matched_modules:
            mod = matched_modules[0]
            parts.append(
                f'📍 所属模块：「{mod["name"]}」'
                + (f'（{mod.get("domain", "")} / {mod.get("dept", "")}）' if mod.get('domain') else '')
                + (f'，负责人：{mod.get("module_owner", "")}' if mod.get('module_owner') else '')
                + (f'（研发 {mod.get("dev_owner", "")}）' if mod.get('dev_owner') else '')
            )

        # 最佳段落摘要：优先选择与查询主题最相关的段落
        if kb_sections:
            # 提取查询中的业务场景关键词，用于优选段落
            query_topics = self._extract_topic_keywords(query)

            # 第一轮：跳过主题不匹配的段落，同时记录是否包含查询主题词
            candidates = []
            for sec in kb_sections:
                is_mismatch, _ = self._check_topic_mismatch(
                    query, sec['heading'], sec.get('content', '')
                )
                if is_mismatch:
                    continue
                # 检查段落标题/内容是否包含查询主题词
                has_topic = any(
                    qt in sec['heading'] or qt in sec.get('content', '')[:500]
                    for qt in query_topics
                ) if query_topics else False
                candidates.append((sec, has_topic))

            if not candidates:
                # 所有段落都被判定为不匹配，退回使用第一个
                best = kb_sections[0]
                parts.append(f'\n⚠️ 以下内容可能与查询不完全匹配，建议参考更具体的文档：')
            else:
                # 优先选择包含查询主题词的段落，否则使用第一个候选
                best = next((s for s, has_t in candidates if has_t), candidates[0][0])

            content = best['content']
            # 简单清理：去图片语法、去 markdown 标记
            content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
            content = re.sub(r'\*\*', '', content)
            content = re.sub(r'#{1,4}\s+', '', content)
            if len(content) > 200:
                content = content[:200] + '...'
            parts.append(f'\n{content.strip()}')

            # 文档位置
            kb_rel = best['path'].replace('2026产品业务知识库/', '')
            parts.append(f'\n📁 知识库：`{kb_rel}` (第{best.get("line_start", "?")}行附近)')

        # 原始文档引用
        if raw_doc_sections:
            raw = raw_doc_sections[0]
            raw_rel = raw['path'].replace('原始产品文档/', '').replace('projects/knowledge-base/raw-docs/', '')
            parts.append(f'📄 原始文档：`{raw_rel}`')

        return '\n'.join(parts) if parts else f'关于「{query}」，未在知识库中找到直接相关内容。建议尝试更具体的关键词或联系相关模块负责人。'

    # -------- FAQ cache --------

    def check_faq_cache(self, query):
        """用 embedding 相似度匹配 FAQ 缓存。"""
        if not self.faq_cache:
            return None

        if self.vector and self.vector.model:
            query_emb = self.vector.encode(query)
        else:
            return self._check_faq_cache_fallback(query)

        best_score = 0
        best_entry = None

        for fp, entry in self.faq_cache.items():
            cached_emb = entry.get('embedding')
            if cached_emb is None:
                continue
            cached_emb = np.array(cached_emb).astype('float32').reshape(1, -1)
            faiss.normalize_L2(cached_emb)
            sim = float(np.dot(query_emb, cached_emb.T)[0][0])

            if sim > 0.85:
                return entry
            if sim > best_score:
                best_score = sim
                best_entry = entry

        return best_entry if best_score > 0.75 else None

    def _check_faq_cache_fallback(self, query):
        """关键词交集 fallback"""
        query_tokens = set(jieba.cut(query))
        query_tokens = {t.strip() for t in query_tokens if len(t.strip()) >= 2}

        best_match = None
        best_score = 0

        for fp, entry in self.faq_cache.items():
            entry_keywords = set(entry.get('keywords', []))
            if not entry_keywords:
                continue

            # 1. 精确查询匹配（最高优先级）
            if query.strip() == entry.get('query', '').strip():
                return entry

            # 2. 关键词重叠匹配
            overlap = query_tokens & entry_keywords
            score = len(overlap) * 2  # 每个重叠词 2 分

            # 3. 子串匹配：查询词出现在关键词中
            for qt in query_tokens:
                for ek in entry_keywords:
                    if qt in ek or ek in qt:
                        score += 1

            if score >= 2 and score > best_score:
                best_score = score
                best_match = entry

        return best_match if best_score >= 2 else None

    def save_faq(self, query, claude_answer, module_name, dept, domain, keywords):
        """保存 Claude 回答到 FAQ 缓存和知识库 FAQ 文件。
        返回: {"saved": bool, "cache_key": str, "faq_path": str}
        """
        import hashlib
        from datetime import datetime
        fp = hashlib.md5(query.encode()).hexdigest()[:12]

        # 去重：如果已有相同 query 的缓存，跳过
        if fp in self.faq_cache:
            return {"saved": False, "reason": "duplicate", "cache_key": fp}

        entry = {
            "query": query,
            "answer": claude_answer,
            "keywords": keywords,
            "module": module_name,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        # 附带 embedding 向量
        if self.vector and self.vector.model:
            try:
                emb = self.vector.encode(query)
                entry['embedding'] = emb.tolist()[0]
            except Exception:
                pass
        self.faq_cache[fp] = entry

        # 持久化缓存
        try:
            with open(self.faq_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.faq_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 2. 保存到 FAQ 知识库文件
        kb_dir = self._domain_to_kb_dir(dept, domain)
        if not kb_dir:
            kb_dir = KB_DIR / dept if dept else KB_DIR / "其他"
        kb_dir.mkdir(parents=True, exist_ok=True)
        faq_file = kb_dir / "FAQ.md"

        # 格式化 FAQ 条目
        date_str = datetime.now().strftime("%Y-%m-%d")
        tag_keywords = "、".join(keywords) if keywords else query
        faq_entry = f"""
### Q: {query}
**关键词：** {tag_keywords}
**模块：** {module_name}
**日期：** {date_str}

{claude_answer}

---
"""

        # 追加到 FAQ 文件（先去重检查）
        try:
            if faq_file.exists():
                existing = faq_file.read_text(encoding="utf-8")
                if f"### Q: {query}" in existing:
                    return {"saved": True, "reason": "faq_exists", "cache_key": fp, "faq_path": str(faq_file.relative_to(PROJECT_DIR))}
            else:
                existing = ""
            faq_file.write_text(
                (existing + faq_entry).strip() + "\n",
                encoding="utf-8"
            )
        except Exception:
            pass

        return {
            "saved": True,
            "cache_key": fp,
            "faq_path": str(faq_file.relative_to(PROJECT_DIR)),
        }

    # -------- cache --------

    def _dir_hash(self):
        """计算所有源文件路径 + 内容摘要的哈希（用于检测文件增删/移动/内容变更）"""
        import hashlib
        h = hashlib.md5()
        for d in [KB_DIR, FAQ_DIR, REPORT_DIR]:
            if d.exists():
                for f in sorted(d.rglob("*.md")):
                    h.update(str(f.relative_to(PROJECT_DIR)).encode())
                    try:
                        h.update(f.read_bytes()[:2048])
                    except Exception:
                        pass
        if self.repo:
            try:
                row = self.repo._execute_one(
                    "SELECT MAX(update_time) as latest FROM faqs WHERE is_deleted = FALSE"
                )
                if row and row["latest"]:
                    h.update(str(row["latest"]).encode())
            except Exception:
                pass
        return h.hexdigest()

    def _get_cache_version(self):
        """从 DB 获取缓存版本号（由 migration 更新）"""
        if self.repo:
            try:
                row = self.repo._execute_one(
                    "SELECT value FROM search_counter WHERE key = 'cache_version'"
                )
                return int(row["value"]) if row else 0
            except Exception:
                return 0
        return 0

    def save_cache(self):
        """保存索引缓存（含文件路径哈希用于自动过期检测）"""
        _kb_raw = len(list(KB_DIR.rglob("*.md"))) if KB_DIR.exists() else 0
        _faq_raw = len([f for f in FAQ_DIR.rglob("*.md")
                       if f.name not in ("TEMPLATE.md", "INDEX.md")]) if FAQ_DIR.exists() else 0
        _report_raw = len(list(REPORT_DIR.rglob("*.md"))) if REPORT_DIR.exists() else 0
        cache = {
            "_meta": {
                "kb_count": _kb_raw,
                "faq_count": _faq_raw,
                "report_count": _report_raw,
                "path_hash": self._dir_hash(),
                "cache_version": self._get_cache_version(),
                "updated": __import__('datetime').datetime.now().isoformat(),
            },
            "keyword_map": {k: v for k, v in self.keyword_map.items()},
            "module_map": self.module_map,
            "product_module_map": self.product_module_map,
            "menu_map": {k: v for k, v in self.menu_map.items()},
            "kb_docs": self.kb_docs,
            "faq_docs": self.faq_docs,
            "report_docs": self.report_docs,
            "synonyms": self.synonyms,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        # Also save BM25 index
        if self.bm25 and self.bm25.N > 0:
            self.bm25.save(str(self.bm25_cache_file))

    def load_cache(self):
        """加载索引缓存（自动检测文件变更，过期则重建）"""
        if not CACHE_FILE.exists():
            return False

        # 快速新鲜度检查：对比各目录 .md 文件数与缓存记录
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            return False

        meta = cache.get("_meta", {})
        if meta:
            # 缓存版本检查（DB 数据变更后自动失效）
            db_version = self._get_cache_version()
            if db_version > 0 and db_version != meta.get("cache_version", 0):
                return False
            # FAQ 文件同时加入 kb_docs 和 faq_docs，用总数对比
            kb_count = len(list(KB_DIR.rglob("*.md"))) if KB_DIR.exists() else 0
            faq_count = len([f for f in FAQ_DIR.rglob("*.md")
                           if f.name not in ("TEMPLATE.md", "INDEX.md")]) if FAQ_DIR.exists() else 0
            report_count = len(list(REPORT_DIR.rglob("*.md"))) if REPORT_DIR.exists() else 0
            # kb_docs = KB_DIR + FAQ_DIR（_load_faq_knowledge 会同时写入 kb_docs）
            if (kb_count != meta.get("kb_count", -1) or
                faq_count != meta.get("faq_count", -1) or
                report_count != meta.get("report_count", -1)):
                return False  # 文件数变化，缓存过期
            # 路径哈希检查（检测文件移动/重命名，仅计数检查不够）
            if meta.get("path_hash") and self._dir_hash() != meta["path_hash"]:
                return False

        self.keyword_map = defaultdict(list, cache.get("keyword_map", {}))
        self.module_map = cache.get("module_map", {})
        self.product_module_map = cache.get("product_module_map", {})
        self.menu_map = defaultdict(list, cache.get("menu_map", {}))
        self.kb_docs = cache.get("kb_docs", [])
        self.faq_docs = cache.get("faq_docs", [])
        self.report_docs = cache.get("report_docs", [])
        self.synonyms = cache.get("synonyms", {})
        return True


# ---------- CLI ----------
def main():
    import argparse

    parser = argparse.ArgumentParser(description="产品知识库智能检索引擎")
    parser.add_argument("query", nargs="?", default="", help="查询内容")
    parser.add_argument("--top", type=int, default=10, help="返回结果数")
    parser.add_argument("--rebuild", action="store_true", help="重建索引缓存")
    parser.add_argument("--seed-faq", action="store_true", help="填充 FAQ 种子数据")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()

    engine = SearchEngine()

    if args.seed_faq:
        engine._load_synonyms()
        engine._load_keyword_index()
        engine._load_module_files()
        engine._load_knowledge_base()
        engine._load_faq_cache()
        count = engine.seed_faq_cache()
        print(f"FAQ 种子数据已填充，共 {count} 条")
        sys.exit(0)

    if args.rebuild or not engine.load_cache():
        engine._load_synonyms()
        engine._load_keyword_index()
        engine._load_module_files()
        engine._load_knowledge_base()
        engine._load_report_data()
        engine._load_bm25_index()
        engine._load_vector_index()
        engine.save_cache()

    # Ensure BM25 is loaded (not stored in JSON cache)
    if engine.bm25 is None:
        engine._load_bm25_index()
    if engine.vector is None:
        engine._load_vector_index()

    if not args.query:
        print(json.dumps({"error": "请提供查询内容"}, ensure_ascii=False))
        sys.exit(1)

    result = engine.search(args.query, top=args.top)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 人性化输出
        print(f"\n🔍 查询: {result['query']}")
        print(f"   分词: {', '.join(result['tokens'])}")
        if result["expanded_terms"] != result["tokens"]:
            print(f"   扩展: {', '.join(result['expanded_terms'])}")
        print(f"   共找到 {result['total']} 条结果\n")

        for i, r in enumerate(result["results"], 1):
            source_labels = {
                "keyword_index": "📌 关键词",
                "module_name": "📦 模块",
                "menu_match": "📋 菜单",
                "knowledge_base": "📚 知识库",
                "report_data": "📊 报表",
            }
            label = source_labels.get(r["source"], r["source"])
            print(f"{i}. {label} | 匹配: {r.get('match_term', '')}")
            if r.get("module"):
                print(f"   模块: {r['module']}")
                print(f"   部门: {r.get('dept', '')} / {r.get('domain', '')}")
                if r.get("dev_owner"):
                    print(f"   负责人: 研发={r['dev_owner']}, 模块={r.get('module_owner', '')}")
                if r.get("module_file"):
                    print(f"   文件: {r['module_file']}")
            if r.get("title"):
                print(f"   标题: {r['title']}")
            if r.get("path"):
                print(f"   路径: {r['path']}")
            if r.get("snippets"):
                for s in r["snippets"]:
                    print(f"   片段: {s[:120]}")
            print()


if __name__ == "__main__":
    main()