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

import jieba
import logging
jieba.setLogLevel(logging.WARNING)
from pypinyin import lazy_pinyin, Style
from bm25_index import BM25Index

# ---------- paths ----------
HERE = Path(__file__).resolve().parent
SHARED_CENTER = HERE.parent  # 共享模块中心/
PROJECT_DIR = SHARED_CENTER.parents[2]  # AiClaudeProject/
KB_DIR = PROJECT_DIR / "2026产品业务知识库"
REPORT_DIR = PROJECT_DIR / "2026报表数据知识库"
SYNONYMS_FILE = HERE / "synonyms.json"
CACHE_FILE = HERE / "index_cache.json"
KEYWORD_INDEX_FILE = HERE / "关键词索引.md"


# ---------- engine ----------
class SearchEngine:
    def __init__(self):
        self.keyword_map = defaultdict(list)  # keyword -> [{module, dept, domain, kb_path, ...}]
        self.module_map = {}  # module_name -> {path, dept, domain, owners, keywords, menus, ...}
        self.menu_map = defaultdict(list)  # menu_name -> [module_name]
        self.kb_docs = []  # [{path, module, dept, domain, content_sample}]
        self.report_docs = []  # [{path, title, content_sample}]
        self.synonyms = {}  # word -> [aliases]
        self.faq_cache = {}  # 回答缓存: {fingerprint: {query, answer, keywords, module, saved_at}}
        self.faq_cache_file = HERE / "faq_cache.json"
        self.bm25 = None
        self.bm25_cache_file = HERE / "bm25_index.pkl"

    # -------- load --------

    def load_all(self):
        self._load_synonyms()
        self._load_keyword_index()
        self._load_module_files()
        self._load_knowledge_base()
        self._load_report_data()
        self._load_faq_cache()
        self._load_bm25_index()

    def _load_synonyms(self):
        if SYNONYMS_FILE.exists():
            with open(SYNONYMS_FILE, "r", encoding="utf-8") as f:
                self.synonyms = json.load(f)

    def _load_keyword_index(self):
        """解析关键词索引.md 中的表格，建立关键词→模块映射"""
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
        """加载所有模块 Skill 文件，提取 frontmatter 和关键信息"""
        module_dirs = [
            SHARED_CENTER / "数智财务组",
            SHARED_CENTER / "免疫规划组",
            SHARED_CENTER / "数字化支撑组",
            SHARED_CENTER / "电子档案组",
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

    def _load_knowledge_base(self):
        """索引知识库文档"""
        if not KB_DIR.exists():
            return
        for md_file in sorted(KB_DIR.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # 提取前 5000 字符作为内容样本（从 2000 提升，确保捕获更多业务内容）
            sample = text[:5000]
            rel_path = str(md_file.relative_to(PROJECT_DIR))

            # 推断所属业务域
            parts = md_file.relative_to(KB_DIR).parts
            dept = parts[0] if len(parts) > 0 else ""
            domain = parts[1] if len(parts) > 1 else ""

            self.kb_docs.append({
                "path": rel_path,
                "dept": dept,
                "domain": domain,
                "title": self._extract_title(text),
                "content_sample": sample,
            })

    def _load_report_data(self):
        """索引报表数据"""
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
                "title": self._extract_title(text),
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

    def _extract_title(self, text):
        """提取文档标题"""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()
        return ""

    # -------- search --------

    def search(self, query, top=10):
        query = query.strip()
        if not query:
            return {"query": query, "results": [], "suggestion": "请输入查询内容"}

        # 1. 分词
        tokens = list(jieba.cut(query))
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 1]

        # 2. 扩展查询词（同义词 + 拼音）
        expanded = self._expand_tokens(tokens)

        # 3. 多源搜索
        kw_results = self._search_keywords(query, expanded)
        mod_results = self._search_modules(query, expanded)
        kb_results = self._search_kb(query, expanded)
        report_results = self._search_reports(query, expanded)

        results = []
        results.extend(kw_results)
        results.extend(mod_results)
        results.extend(kb_results)
        results.extend(report_results)

        # 4. 去重 + 排序
        results = self._deduplicate(results)
        results = self._rank(results, query, expanded)

        # 5. 生成智能问答 - 使用全部结果做深度搜索
        answer = self._generate_answer(query, expanded, results)

        # 6. 构建过程追踪
        process = {
            "layer1_search": {
                "tokens": tokens,
                "expanded_terms": sorted(expanded, key=lambda x: len(x), reverse=True)[:15],
                "sources": {
                    "keyword_index": len(kw_results),
                    "module_match": len(mod_results),
                    "knowledge_base": len(kb_results),
                    "report_data": len(report_results),
                },
                "after_dedup_rank": len(results),
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

        return {
            "query": query,
            "tokens": tokens,
            "expanded_terms": list(expanded),
            "total": len(results) + (1 if answer else 0),
            "answer": answer,
            "results": results[:top],
            "process": process,
        }

    def _expand_tokens(self, tokens):
        """扩展查询词：加入同义词、拼音、bigram组合"""
        expanded = set(tokens)

        # bigram 组合（如 "预算"+"申报" → "预算申报"）
        for i in range(len(tokens) - 1):
            expanded.add(tokens[i] + tokens[i + 1])
        # 也加入完整查询字符串
        full = "".join(tokens)
        if len(full) <= 10:
            expanded.add(full)

        # 同义词扩展
        for token in tokens:
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
                    results.append({
                        "source": "module_name",
                        "match_type": "fuzzy",
                        "match_term": term,
                        "module": mod_name,
                        "dept": info["dept"],
                        "domain": info["domain"],
                        "module_file": info["path"],
                        "dev_owner": info["dev_owner"],
                        "module_owner": info["module_owner"],
                        "product": info["product"],
                        "appendix": info["appendix"],
                        "keywords": info["keywords"],
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

    def _search_kb(self, query, expanded):
        """在知识库文档中搜索"""
        results = []
        for doc in self.kb_docs:
            score = 0
            matched = []
            for term in expanded:
                if term in doc["content_sample"]:
                    score += 1
                    matched.append(term)
            if score > 0:
                # 提取匹配上下文
                snippets = self._extract_snippets(doc["content_sample"], expanded, max_snippets=2)
                results.append({
                    "source": "knowledge_base",
                    "match_type": "content",
                    "match_terms": matched,
                    "path": doc["path"],
                    "title": doc["title"],
                    "dept": doc["dept"],
                    "domain": doc["domain"],
                    "snippets": snippets,
                    "score": min(score * 2, 9),
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
                snippets = self._extract_snippets(doc["content_sample"], expanded, max_snippets=2)
                results.append({
                    "source": "report_data",
                    "match_type": "content",
                    "match_terms": matched,
                    "path": doc["path"],
                    "title": doc["title"],
                    "snippets": snippets,
                    "score": min(score * 2, 7),
                })
        return results

    def _extract_snippets(self, text, terms, max_snippets=2, context_len=60):
        """提取匹配关键词的上下文片段"""
        snippets = []
        for term in terms:
            idx = text.find(term)
            if idx >= 0:
                start = max(0, idx - context_len)
                end = min(len(text), idx + len(term) + context_len)
                snippet = text[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."
                snippets.append(snippet.strip())
                if len(snippets) >= max_snippets:
                    break
        return snippets

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
        """从检索结果中构建 Claude API 的 system prompt 和 user message。
        返回 dict: {"system": str, "messages": [{"role": "user", "content": str}]}
        """
        # 收集匹配的模块信息
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
                })

        # 深度搜索 KB（复用已有逻辑，但不生成 answer，只取上下文）
        # 计算分词和扩展词，确保深度搜索有匹配词可用
        tokens = list(jieba.cut(query))
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 1]
        expanded = self._expand_tokens(tokens) if tokens else set()

        kb_sections = []
        kb_files_searched = []
        priority_dirs = []
        for r in results:
            if r.get("source") == "keyword_index" and r.get("kb_path"):
                kb_dir = PROJECT_DIR / r["kb_path"]
                if kb_dir.exists():
                    priority_dirs.append(kb_dir)
        if priority_dirs or results:
            kb_sections, kb_files_searched, _ = self._deep_search_kb(
                query, expanded, results, priority_dirs
            )

        # 搜索原始产品文档
        raw_doc_sections = self._search_raw_docs(query, expanded)

        # 搜索报表
        report_sections = self._search_reports_deep(query, expanded, results)

        # 组装 system prompt
        system_parts = [
            "你是产品知识库助手，服务于数智财务（浙里报/孵化业务/徽报账）、电子档案、免疫规划、数字化支撑等全部业务模块的用户咨询。",
            "",
            "## 回答策略",
            "1. 仔细阅读下方提供的文档内容，从中提取与用户问题相关的信息",
            "2. 如果文档内容足够回答，直接给出准确答案，引用文档中的具体内容",
            "3. 如果文档内容部分相关但不够完整，先给出文档中的信息，再结合你的知识补充",
            "4. 如果文档完全不相关，不要编造，诚实说明知识库暂无此文档，然后基于你的知识给出参考回答",
            "",
            "## 回答要求",
            "- 用中文回答，详细、专业、完整",
            "- 如果有操作步骤，按步骤编号清晰列出",
            "- 给出明确的结论，不要含糊其辞",
            "- 结尾标注信息来源",
            "- 在回答末尾，用以下 JSON 格式输出建议补充的关键词（仅输出 JSON，不放 markdown 代码块中）：",
            '  {"keywords_to_add": ["关键词1", "关键词2"], "module": "所属模块名"}',
            "",
        ]

        if matched_modules:
            system_parts.append("## 匹配的模块")
            for mod in matched_modules[:3]:
                system_parts.append(
                    f"- {mod['name']}（{mod['dept']}/{mod['domain']}）"
                    f" | 研发: {mod.get('dev_owner', '未知')}"
                    f" | 模块负责人: {mod.get('module_owner', '未知')}"
                )
            system_parts.append("")

        if kb_sections:
            # 收集最相关的 KB 文件，读取完整内容（而非截断片段）
            seen_files = set()
            full_docs = []
            for sec in kb_sections:
                path = sec.get("path", "")
                if path and path not in seen_files:
                    seen_files.add(path)
                    try:
                        full_path = PROJECT_DIR / path
                        if full_path.exists():
                            full_content = full_path.read_text(encoding="utf-8")
                            # 限制单个文件最多 12000 字符
                            if len(full_content) > 12000:
                                full_content = full_content[:12000] + "\n\n...(内容过长，已截断)..."
                            full_docs.append({
                                "path": path,
                                "content": full_content,
                                "score": sec.get("score", 0),
                            })
                    except Exception:
                        pass
                if len(full_docs) >= 3:  # 从 2 提升到 3 个完整文件
                    break

            system_parts.append("## 知识库文档（完整内容）")
            for i, doc in enumerate(full_docs, 1):
                rel_path = doc["path"].replace("2026产品业务知识库/", "")
                system_parts.append(f"### 文档{i}: {rel_path}")
                system_parts.append(doc["content"])
                system_parts.append("")
            system_parts.append("")

        if raw_doc_sections:
            system_parts.append("## 原始产品文档")
            for i, sec in enumerate(raw_doc_sections[:2], 1):
                heading = sec["heading"].lstrip("#").strip()
                system_parts.append(f"### [{i}] {heading}")
                system_parts.append(sec["content"][:1000])
                system_parts.append("")
            system_parts.append("")

        if report_sections:
            system_parts.append("## 历史报表数据")
            for i, sec in enumerate(report_sections[:1], 1):
                system_parts.append(f"### [{i}] {sec['heading'].lstrip('#').strip()}")
                system_parts.append(sec["content"][:800])
            system_parts.append("")

        return {
            "system": "\n".join(system_parts),
            "messages": [{"role": "user", "content": query}],
            # 附带结构化数据，供后续 FAQ 保存使用
            "_meta": {
                "matched_modules": matched_modules,
                "kb_sections": kb_sections,
                "kb_files_searched": [str(p) for p in kb_files_searched],
            },
        }

    def _deep_search_kb(self, query, expanded, results, priority_dirs=None):
        """两阶段深度搜索 KB 文档。

        S1: BM25 文档级筛选 → Top-10 文档
        S2: 段落级精细匹配 → Top-5 段落
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

        # S2: 段落级精细匹配
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

                # 多维评分
                keyword_score = self._match_score(seg['content'], search_terms)
                heading_score = self._match_score(seg['heading'], search_terms) * 3
                parent_heading_score = self._match_score(
                    seg.get('parent_heading', ''), search_terms
                ) * 1.5

                # FAQ 区域加权
                is_faq = any(kw in seg['heading'] for kw in ['FAQ', '常见问题', '故障', '排查'])
                faq_bonus = 2.0 if is_faq else 0

                # 文档新鲜度
                doc_date = self._extract_date_from_path(path)
                freshness = 1.0
                if doc_date:
                    days_ago = (date.today() - doc_date).days
                    if days_ago > 365:
                        freshness = max(0.5, 1.0 - (days_ago - 365) / 365)

                total_score = (
                    keyword_score * 0.4
                    + heading_score * 0.25
                    + parent_heading_score * 0.15
                    + faq_bonus * 0.1
                ) * freshness

                if total_score >= 0.5:
                    images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', seg['content'])
                    sections.append({
                        'path': path,
                        'heading': seg['heading'],
                        'parent_heading': seg.get('parent_heading', ''),
                        'content': seg['content'][:1500],
                        'images': [{'alt': alt, 'src': src} for alt, src in images],
                        'score': total_score,
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
        raw_dir = PROJECT_DIR / "原始产品文档"
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
        """选择最佳模块：优先 keyword_index 匹配，其次 KB 部门匹配"""
        if not matched_modules:
            return "", {}

        # 优先：keyword_index 匹配的模块
        kw_modules = []
        for r in results:
            if r.get("source") == "keyword_index":
                kw_modules.append(r.get("module"))
        if kw_modules:
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

        # 最佳段落摘要
        if kb_sections:
            best = kb_sections[0]
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
            raw_rel = raw['path'].replace('原始产品文档/', '')
            parts.append(f'📄 原始文档：`{raw_rel}`')

        return '\n'.join(parts) if parts else f'关于「{query}」，未在知识库中找到直接相关内容。建议尝试更具体的关键词或联系相关模块负责人。'

    # -------- FAQ cache --------

    def check_faq_cache(self, query):
        """检查 FAQ 缓存中是否有匹配的回答。
        返回匹配的缓存条目 dict，或 None。
        """
        query_tokens = set(jieba.cut(query))
        query_tokens = {t.strip() for t in query_tokens if len(t.strip()) >= 2}

        best_match = None
        best_score = 0

        for fp, entry in self.faq_cache.items():
            entry_keywords = set(entry.get("keywords", []))
            if not entry_keywords:
                continue
            overlap = query_tokens & entry_keywords
            if len(overlap) >= 2:
                score = len(overlap)
                # 查询文本相似度加分
                if query.strip() == entry.get("query", "").strip():
                    score += 10
                elif query.strip() in entry.get("query", "") or entry.get("query", "") in query.strip():
                    score += 5
                if score > best_score:
                    best_score = score
                    best_match = entry

        if best_match and best_score >= 3:
            return best_match
        return None

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

    def _deduplicate(self, results):
        """去重，保留最高分的条目"""
        best = {}
        for r in results:
            key = (r.get("source"), r.get("module"), r.get("path"))
            if key not in best or r["score"] > best[key]["score"]:
                best[key] = r
        return list(best.values())

    def _rank(self, results, query, expanded):
        """相关性排序：精确匹配 > 模糊匹配 > 内容匹配"""
        return sorted(results, key=lambda r: r["score"], reverse=True)

    # -------- cache --------

    def save_cache(self):
        """保存索引缓存"""
        cache = {
            "keyword_map": {k: v for k, v in self.keyword_map.items()},
            "module_map": self.module_map,
            "menu_map": {k: v for k, v in self.menu_map.items()},
            "kb_docs": self.kb_docs,
            "report_docs": self.report_docs,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        # Also save BM25 index
        if self.bm25 and self.bm25.N > 0:
            self.bm25.save(str(self.bm25_cache_file))

    def load_cache(self):
        """加载索引缓存"""
        if not CACHE_FILE.exists():
            return False
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        self.keyword_map = defaultdict(list, cache.get("keyword_map", {}))
        self.module_map = cache.get("module_map", {})
        self.menu_map = defaultdict(list, cache.get("menu_map", {}))
        self.kb_docs = cache.get("kb_docs", [])
        self.report_docs = cache.get("report_docs", [])
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
        engine.save_cache()

    # Ensure BM25 is loaded (not stored in JSON cache)
    if engine.bm25 is None:
        engine._load_bm25_index()

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