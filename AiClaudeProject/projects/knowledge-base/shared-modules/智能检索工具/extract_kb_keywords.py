#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 KB 文档提取关键词，写入文档「## 关键词」区块，并更新关键词索引。

用法:
  python3 extract_kb_keywords.py          # 扫描所有 KB 文档，提取关键词
  python3 extract_kb_keywords.py --dry-run  # 仅预览，不写入
"""

import re, os, sys, json
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).resolve().parent
SHARED_CENTER = HERE.parent  # shared-modules/
PROJECT_DIR = HERE.parents[3]  # AiClaudeProject/

# 知识库目录（优先新路径，兼容旧路径）
_KB_NEW = HERE.parents[1] / "knowledge"  # projects/knowledge-base/knowledge/
_KB_OLD = PROJECT_DIR / "2026产品业务知识库"
KB_DIR = _KB_NEW if _KB_NEW.exists() else _KB_OLD
KEYWORD_INDEX_FILE = SHARED_CENTER / "关键词库" / "关键词索引.md"

# ── 停用词 ──
STOP_WORDS = {
    "版本", "迭代", "内容", "功能", "描述", "支持", "新增", "优化",
    "修复", "问题", "需求", "背景", "说明", "备注", "注意", "范围",
    "权限", "菜单", "路径", "界面", "步骤", "规则", "统计", "数据",
    "进行", "查询", "展示", "查看", "使用", "操作", "处理", "配置",
    "根据", "目前", "当前", "相关", "对应", "其中", "包括", "以及",
    "或者", "通过", "可以", "需要", "已经", "用于", "并且", "如果",
    "这个", "那个", "一个", "一种", "所有", "各个", "每个", "其他",
    "不同", "部分", "首页", "新增", "改造", "解决", "上报", "管理",
    "实现", "提供", "完成", "之后", "之前", "增加", "修改", "调整",
    "去掉", "删除", "后续", "未来", "2025", "2026", "版本迭代",
    "规则说明", "需求描述", "版本概述", "交互说明", "方案说明",
    "目标", "交付", "入口", "用户", "单位", "系统", "平台", "服务",
    "业务", "产品", "项目", "需求单号", "版本内容",
    "影响范围", "发放对象", "需求影响", "需求背景",
    # 元数据/表格字段
    "关联部门", "二级部门", "产品线", "附录", "字段", "链接类型",
    "关键词索引", "模块文件", "报表", "中央枢纽", "双向链接",
    "总目录", "来源", "模块基础信息", "版本迭代时间线",
    "产品业务版本内容关键词", "版本所属一级菜单", "二级菜单",
    "版本迭代时间", "链接", "目标", "值", "类型",
    "知识库", "关键词", "索引", "文件", "路径",
    "模块", "部门", "业务域", "菜单映射", "关联信息",
    "所属产品", "产品模块", "模块名称", "功能名称",
    "研发负责人", "模块负责人", "周报附录",
    "一级菜单", "三级菜单", "菜单路径",
    # 额外过滤
    "改造优化", "需求优化", "功能优化", "版本优化",
    "紧急", "修复问题", "优化改造", "需求改造",
}

# ── 模块文件索引 ──
def load_module_files():
    """加载所有模块文件的 frontmatter 和菜单映射"""
    modules = []
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
            if md_file.name in ("SKILL.md", "zlb_menu.md", "ymg_menu.md"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            info = {
                "name": md_file.stem,
                "path": str(md_file.relative_to(PROJECT_DIR)),
                "dept": "",
                "domain": "",
                "product": "",
                "dev_owner": "",
                "module_owner": "",
                "appendix": "",
                "keywords": [],
                "menus": [],
            }

            # frontmatter
            fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if fm_match:
                for line in fm_match.group(1).split("\n"):
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

            # 关键词 section
            kw_match = re.search(r"## 关键词\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
            if kw_match:
                info["keywords"] = [k.strip() for k in kw_match.group(1).strip().split(",") if k.strip()]

            # 菜单映射
            menu_section = re.search(r"## 菜单映射\s*\n(.+?)(?:\n##|\n\Z)", text, re.DOTALL)
            if menu_section:
                for line in menu_section.group(1).strip().split("\n"):
                    if line.startswith("|") and not line.startswith("|--") and not line.startswith("| 一级"):
                        cells = [c.strip() for c in line.split("|")[1:-1]]
                        if cells:
                            for c in cells:
                                if c and c != "-":
                                    info["menus"].append(c)

            modules.append(info)
    return modules


def extract_keywords_from_doc(filepath):
    """从单个 KB 文档提取关键词"""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return set()

    keywords = set()

    # A: 「版本迭代时间线【总目录】」表格中的关键词列
    in_timeline = False
    for line in text.split("\n"):
        stripped = line.strip()
        if "版本迭代时间线" in stripped and "总目录" in stripped:
            in_timeline = True
            continue
        if in_timeline and stripped.startswith("|---"):
            continue
        if in_timeline and stripped == "":
            in_timeline = False
            continue
        if in_timeline and stripped.startswith("|") and not stripped.startswith("| 版本迭代时间"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= 4:
                # 最后一列是关键词
                kw_cell = cells[-1] if cells[-1] else ""
                if kw_cell and kw_cell not in ("-", "产品业务版本内容关键词"):
                    for kw in re.split(r"[，,、\s/]+", kw_cell):
                        kw = kw.strip()
                        if 2 <= len(kw) <= 12 and kw not in STOP_WORDS:
                            keywords.add(kw)
                # 一级菜单名
                if len(cells) >= 2 and cells[1] and cells[1] != "-":
                    menu = cells[1]
                    if menu not in STOP_WORDS and len(menu) >= 2:
                        keywords.add(menu)

    # B: 所有标题中的【模块名】
    heading_modules = re.findall(r"【(.+?)】", text)
    for m in heading_modules:
        m = m.strip()
        if 2 <= len(m) <= 20 and m not in STOP_WORDS:
            # 排除太通用的词
            if not re.match(r"^\d+$", m) and "紧急" not in m:
                keywords.add(m)

    # C: 版本概述中的功能关键词
    overview_match = re.search(r"版本概述\s*\n+(.+?)(?=\n###\s|\n---|\Z)", text, re.DOTALL)
    if overview_match:
        overview_text = overview_match.group(1)
        # 提取功能列表项
        func_items = re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]\s*(.+?)(?:[。；;]|\n)", overview_text)
        for item in func_items:
            item = item.strip()
            # 取关键功能名（前 8 字）
            if len(item) >= 4:
                short = item[:10].rstrip("，。,.")
                if short not in STOP_WORDS:
                    keywords.add(short)

    # D: 从「版本内容关键词」中提取（在 免疫规划组 的文档中可能存在）
    # 表格行格式: | 日期 | 一级菜单 | 二级菜单 | 关键词 |
    for match in re.finditer(r"\|\s*([\d\-]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|\s*([^|]+)\s*\|", text):
        kw_cell = match.group(4).strip()
        if kw_cell and kw_cell not in ("-", "产品业务版本内容关键词"):
            for kw in re.split(r"[，,、\s/]+", kw_cell):
                kw = kw.strip()
                if 2 <= len(kw) <= 12 and kw not in STOP_WORDS:
                    keywords.add(kw)

    # 过滤
    filtered = set()
    for kw in keywords:
        if kw.isdigit():
            continue
        if re.match(r"^[\d\.\-\+/%]+$", kw):
            continue
        if len(kw) < 2 or len(kw) > 20:
            continue
        if kw in STOP_WORDS:
            continue
        # 过滤纯英文缩写（太短）
        if len(kw) <= 3 and kw.isascii() and kw.isalpha():
            continue
        # 过滤 markdown 语法残留
        if kw.startswith("**") or kw.startswith("[") or kw.startswith("http"):
            continue
        if kw.startswith("![") or kw.startswith("]("):
            continue
        # 过滤纯标点
        if re.match(r"^[^\w一-鿿]+$", kw):
            continue
        filtered.add(kw)

    return filtered


def infer_dept_domain(filepath):
    """从 KB 文档路径推断部门和业务域"""
    rel = filepath.relative_to(KB_DIR)
    parts = rel.parts
    dept = parts[0] if len(parts) > 0 else ""
    # 数智财务组有子目录
    if dept == "数智财务组" and len(parts) > 1:
        domain = parts[1]
    else:
        domain = dept
    return dept, domain


def match_module(keyword, modules, dept, domain):
    """将关键词匹配到最相关的产品模块"""
    best_score = 0
    best_module = None

    for mod in modules:
        score = 0
        # 部门匹配加分
        if mod["dept"] == dept:
            score += 3
        if mod["domain"] == domain:
            score += 2

        # 关键词在模块名中
        if keyword == mod["name"]:
            score += 10
        elif keyword in mod["name"]:
            score += 8
        elif mod["name"] in keyword:
            score += 5

        # 关键词在模块关键词列表中
        for kw in mod.get("keywords", []):
            if kw == keyword or keyword in kw:
                score += 8
                break

        # 关键词在菜单中
        for menu in mod.get("menus", []):
            if keyword == menu or keyword in menu:
                score += 4
                break

        if score > best_score:
            best_score = score
            best_module = mod

    return best_module if best_score >= 5 else None


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("步骤 1: 加载模块文件索引")
    modules = load_module_files()
    print(f"  加载了 {len(modules)} 个模块文件")

    print("\n步骤 2: 扫描 KB 文档，提取关键词")
    kb_docs = list(KB_DIR.rglob("*.md"))
    print(f"  找到 {len(kb_docs)} 个 KB 文档")

    total_keywords = 0
    new_index_entries = []
    doc_kw_map = {}
    docs_with_keywords = 0

    for doc_path in sorted(kb_docs):
        keywords = extract_keywords_from_doc(doc_path)
        if not keywords:
            continue

        docs_with_keywords += 1
        dept, domain = infer_dept_domain(doc_path)
        kb_rel_path = str(doc_path.relative_to(PROJECT_DIR))
        doc_kw_map[doc_path] = keywords
        total_keywords += len(keywords)

        # 为每个关键词匹配模块
        for kw in sorted(keywords):
            mod = match_module(kw, modules, dept, domain)
            if mod:
                new_index_entries.append({
                    "keyword": kw,
                    "module": mod["name"],
                    "module_file": mod["path"],
                    "dept": dept,
                    "domain": domain,
                    "kb_path": kb_rel_path,
                    "note": f"来自 {doc_path.stem}",
                })

    print(f"  有关键词的文档: {docs_with_keywords}/{len(kb_docs)}")
    print(f"  提取了 {total_keywords} 个关键词（去重前）")
    print(f"  匹配到 {len(new_index_entries)} 个关键词→模块映射")

    if dry_run:
        print("\n[Dry-run] 预览前 30 个关键词:")
        # 按部门分组展示
        by_dept = defaultdict(list)
        for entry in new_index_entries:
            by_dept[entry["dept"]].append(entry)
        for dept, entries in sorted(by_dept.items()):
            print(f"\n  [{dept}] ({len(entries)} 条)")
            for entry in entries[:10]:
                print(f"    {entry['keyword']} → {entry['module']} ({entry['domain']})")
        return

    # ── 步骤 3: 在 KB 文档中插入关键词区块 ──
    print("\n步骤 3: 在 KB 文档中插入「## 关键词」区块")
    updated_count = 0
    for doc_path, keywords in doc_kw_map.items():
        try:
            text = doc_path.read_text(encoding="utf-8")
        except Exception:
            continue

        # 检查是否已有「## 关键词」区块
        if re.search(r"^## 关键词\s*$", text, re.MULTILINE):
            continue

        # 在「模块基础信息」表格之后插入
        lines = text.split("\n")
        insert_pos = None
        in_info_table = False
        for i, line in enumerate(lines):
            if "模块基础信息" in line:
                in_info_table = True
                continue
            if in_info_table and line.startswith("|"):
                continue
            if in_info_table and line.strip() == "":
                # 跳过表头前的空行，继续找表格结束
                continue
            if in_info_table and not line.startswith("|") and not line.startswith("## 关键词"):
                # 表格结束，在此插入
                insert_pos = i
                break

        if insert_pos is None:
            # fallback: 在「双向链接」之前
            for i, line in enumerate(lines):
                if line.startswith("## 双向链接"):
                    insert_pos = i
                    break

        if insert_pos is None:
            # fallback: 在第一个 ## 标题之后
            for i, line in enumerate(lines):
                if line.startswith("## ") and i > 0:
                    insert_pos = i
                    break

        if insert_pos is None:
            continue

        kw_str = ", ".join(sorted(keywords)[:30])
        kw_block = f"\n## 关键词\n\n{kw_str}\n"

        new_lines = lines[:insert_pos] + [kw_block] + lines[insert_pos:]
        new_text = "\n".join(new_lines)

        doc_path.write_text(new_text, encoding="utf-8")
        updated_count += 1

    print(f"  更新了 {updated_count} 个 KB 文档")

    # ── 步骤 4: 更新关键词索引 ──
    print("\n步骤 4: 更新关键词索引")
    if not KEYWORD_INDEX_FILE.exists():
        print("  ❌ 关键词索引文件不存在")
        return

    index_text = KEYWORD_INDEX_FILE.read_text(encoding="utf-8")

    # 去重
    existing_keywords = set()
    for line in index_text.split("\n"):
        if line.startswith("| ") and not line.startswith("|--") and not line.startswith("| 关键词"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells and cells[0]:
                existing_keywords.add(cells[0])

    # 按部门分组，去重
    dept_entries = defaultdict(list)
    seen_pairs = set()
    for entry in new_index_entries:
        key = (entry["keyword"], entry["module"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        if entry["keyword"] not in existing_keywords:
            dept_entries[entry["dept"]].append(entry)
            existing_keywords.add(entry["keyword"])

    total_new = sum(len(v) for v in dept_entries.values())
    print(f"  新增 {total_new} 条关键词索引")

    if total_new == 0:
        print("  没有新关键词需要添加")
        return

    # 按部门插入
    sections = index_text.split("\n")
    dept_patterns = {
        "数智财务组": ["### 数智财务组 · 浙里报", "### 数智财务组 · 孵化业务",
                       "### 数智财务组 · 徽报账", "### 数智财务组 · 数智财务组-直属"],
        "免疫规划组": ["### 免疫规划组"],
        "数字化支撑组": ["### 数字化支撑组"],
        "电子档案组": ["### 电子档案组"],
    }

    for dept, patterns in sorted(dept_patterns.items()):
        entries = dept_entries.get(dept, [])
        if not entries:
            continue

        new_lines = []
        for entry in entries:
            mod_file_rel = entry["module_file"].replace("ProjectSkill/projects/共享模块中心/", "").replace("projects/knowledge-base/shared-modules/", "")
            kb_path_short = entry["kb_path"].replace("2026产品业务知识库/", "").replace("projects/knowledge-base/knowledge/", "")
            new_lines.append(
                f"| {entry['keyword']} | {entry['module']} | "
                f"[{entry['module']}.md]({mod_file_rel}) | "
                f"{entry['dept']} | {entry['domain']} | "
                f"projects/knowledge-base/knowledge/{kb_path_short} | "
                f"{entry['note']} |"
            )

        inserted = False
        for pattern in patterns:
            # 找到部门区块
            target_idx = None
            for i, line in enumerate(sections):
                if pattern in line:
                    target_idx = i
                    break

            if target_idx is None:
                continue

            # 找到最后一个表格行
            last_row = None
            for i in range(target_idx, len(sections)):
                if sections[i].startswith("### ") and i > target_idx:
                    break
                if sections[i].startswith("| ") and not sections[i].startswith("|--"):
                    last_row = i

            if last_row:
                sections = sections[:last_row + 1] + new_lines + sections[last_row + 1:]
                inserted = True
                break

        if inserted:
            print(f"  ✅ [{dept}] 新增 {len(entries)} 条")
        else:
            print(f"  ⚠️ [{dept}] 无法定位，跳过 {len(entries)} 条")

    # 写入
    KEYWORD_INDEX_FILE.write_text("\n".join(sections), encoding="utf-8")
    print(f"  ✅ 关键词索引已更新")

    # ── 步骤 5: 重建索引 ──
    print("\n步骤 5: 重建搜索索引")
    ret = os.system(f"cd {PROJECT_DIR} && python3 {HERE}/search_engine.py 'test' --rebuild > /dev/null 2>&1")
    if ret == 0:
        print("  ✅ 搜索索引已重建")
    else:
        print("  ⚠️ 搜索索引重建可能失败，请手动运行")


if __name__ == "__main__":
    main()