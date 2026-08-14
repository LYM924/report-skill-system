#!/usr/bin/env python3
"""
FAQ 自动生成脚本

从知识库文档和工单分析中提取 FAQ 种子，生成草稿待人工审核。

用法:
    python3 faq_generate.py                          # 分析并输出建议
    python3 faq_generate.py --drafts                 # 生成草稿文件到 _drafts/
    python3 faq_generate.py --drafts --apply         # 生成草稿并自动入库
    python3 faq_generate.py --json                   # JSON 格式输出
    python3 faq_generate.py --source tickets         # 仅从工单分析生成
    python3 faq_generate.py --source kb              # 仅从知识库生成

流程:
    1. 从知识库文档提取 Q&A 章节
    2. 从工单分析文档提取高频问题
    3. 从搜索引擎 FAQ 缓存提取常见查询
    4. 去重合并 → 生成草稿 → 人工审核 → 入库
"""

import os
import re
import sys
import json
import hashlib
from pathlib import Path
from datetime import date
from collections import defaultdict, Counter

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
FAQ_DIR = PROJECT_DIR / "FAQ知识库"
KB_DIR = PROJECT_DIR / "knowledge"
DRAFTS_DIR = FAQ_DIR / "_drafts"
INDEX_FILE = FAQ_DIR / "INDEX.md"
TEMPLATE_FILE = FAQ_DIR / "TEMPLATE.md"

# 工单分析文档路径
TICKET_DOC_DIRS = [
    PROJECT_DIR.parent.parent / "其他文档区",
    PROJECT_DIR.parent.parent / "2026报表数据知识库" / "周报",
    PROJECT_DIR.parent.parent / "projects" / "report-system" / "output",
]

# 部门简称映射
DEPT_CODES = {
    "数智财务组": "SZ",
    "免疫规划组": "YM",
    "电子档案组": "DZ",
    "数字化支撑组": "ZH",
}

# 子模块简称映射
MODULE_CODES = {
    "浙里报": "ZLB",
    "孵化业务": "FH",
    "徽报账": "HBZ",
    "数智财务组-直属": "ZS",
}

# 工单号正则（支持 20+ 位数字时间戳或 TKT 前缀）
TICKET_ID_RE = re.compile(r'TKT\d{14,24}|(?<![a-zA-Z\d])\d{20,24}(?![a-zA-Z\d])', re.IGNORECASE)


def load_existing_faqs():
    """加载已有 FAQ 的 ID 和关键词"""
    ids = set()
    keywords = {}
    if not FAQ_DIR.exists():
        return ids, keywords
    for md_file in FAQ_DIR.rglob("*.md"):
        if md_file.name in ("TEMPLATE.md", "INDEX.md") or md_file.parent.name == "_drafts":
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if fm_match:
                fm = {}
                for line in fm_match.group(1).split("\n"):
                    line = line.strip()
                    if ":" not in line:
                        continue
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if key == "id":
                        ids.add(value)
                    elif key == "keywords":
                        value = value.strip("[]")
                        keywords[value] = fm.get("title", "")
        except Exception:
            pass
    return ids, keywords


def extract_kb_faqs(kb_dir):
    """从知识库文档中提取 Q&A 章节"""
    seeds = []
    if not kb_dir.exists():
        return seeds

    for md_file in sorted(kb_dir.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # 查找标准 FAQ 章节
        faq_sections = re.findall(
            r'##\s*(?:FAQ|常见问题|故障库|常见问题&故障库|常见问题排查)\s*\n(.*?)(?=\n##\s|\Z)',
            text, re.DOTALL
        )

        for section in faq_sections:
            qa_pairs = re.findall(
                r'###\s*Q[:：]?\s*(.+?)\n(.*?)(?=\n###\s*Q[:：]|\n##\s|\Z)',
                section, re.DOTALL
            )
            for q, a in qa_pairs:
                q = q.strip()
                a = a.strip()
                if len(q) < 5 or len(a) < 20:
                    continue
                seeds.append({
                    "source": str(md_file.relative_to(PROJECT_DIR.parent.parent)).replace(str(PROJECT_DIR.parent.parent) + "/", ""),
                    "question": q,
                    "answer": a[:500],
                    "type": "kb_qanda",
                })

        # 查找"问题现象 原因 解决方案"等表格类 FAQ
        table_rows = re.findall(
            r'\|(.+?)\|(.+?)\|(.+?)\|',
            text
        )
        for row in table_rows:
            cells = [c.strip() for c in [row[0], row[1], row[2]]]
            if len(cells) == 3 and cells[0] and cells[1] and cells[2]:
                has_issue = any(kw in cells[0] for kw in ["问题", "现象", "报错", "故障", "无法"])
                has_solution = any(kw in cells[2] for kw in ["解决", "方案", "处理", "修复"])
                if has_issue and has_solution:
                    seeds.append({
                        "source": str(md_file.relative_to(PROJECT_DIR.parent.parent)),
                        "question": cells[0][:80],
                        "answer": f"**原因**: {cells[1][:200]}\n**解决**: {cells[2][:200]}",
                        "type": "kb_table",
                    })

    return seeds


def extract_ticket_faqs():
    """从工单分析文档提取高频问题"""
    seeds = []
    keyword_counter = Counter()
    ticket_issues = defaultdict(list)

    for search_dir in TICKET_DOC_DIRS:
        if not search_dir.exists():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            if "周报" in str(md_file):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            for line in text.split("\n"):
                # 提取工单表格行
                if line.startswith("|") and TICKET_ID_RE.search(line):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if len(cells) >= 4:
                        ticket_id = ""
                        issue = ""
                        for cell in cells:
                            tid_match = TICKET_ID_RE.search(cell)
                            if tid_match:
                                ticket_id = tid_match.group()
                            elif len(cell) >= 8 and not ticket_id:
                                # 可能是问题描述
                                issue = cell[:80]

                        if ticket_id and issue:
                            # 提取关键词
                            words = re.findall(r'[\w一-鿿]{2,}', issue)
                            for w in words:
                                if len(w) >= 2:
                                    keyword_counter[w] += 1
                                    ticket_issues[ticket_id].append({
                                        "issue": issue,
                                        "keywords": [w for w in words if len(w) >= 2][:5],
                                        "file": str(md_file.relative_to(PROJECT_DIR.parent.parent)),
                                    })

    # 从高频关键词生成种子
    # 过滤通用词和已有 FAQ 覆盖的词
    stop_words = {"问题", "解决", "支持", "处理", "相关", "操作", "系统", "用户", "数据", "信息", "查询", "设置", "需要", "确认", "无法", "使用", "选择", "申请", "审批", "提交", "创建", "查看", "新增", "编辑", "删除", "修改", "导出", "导入", "下载", "上传", "同步", "配置", "管理", "功能", "列表", "页面", "按钮", "状态", "类型", "日期", "时间", "金额", "名称", "编号", "代码", "方式", "场景", "说明", "结果", "因为", "所以", "但是", "如果", "可以", "没有", "什么", "如何", "怎么", "是否"}
    existing_ids, existing_keywords = load_existing_faqs()

    coverage_keywords = set()
    for kw_str in existing_keywords:
        for kw in kw_str.split(","):
            coverage_keywords.add(kw.strip().strip("'\""))

    # 从高频关键词推问题
    for keyword, count in keyword_counter.most_common(100):
        if keyword in stop_words or keyword in coverage_keywords:
            continue
        if count < 3 or len(keyword) < 3 or len(keyword) > 20:
            continue

        # 找到相关工单
        related_tickets = []
        for tid, issues in ticket_issues.items():
            for item in issues:
                if keyword in item["keywords"]:
                    related_tickets.append({
                        "id": tid,
                        "issue": item["issue"],
                    })
                    if len(related_tickets) >= 3:
                        break
            if len(related_tickets) >= 3:
                break

        if related_tickets:
            # 推测问题类型
            if "报错" in keyword or "失败" in keyword or "异常" in keyword:
                q = f"{keyword}报错"
            elif "怎么" in keyword or "如何" in keyword:
                q = keyword
            else:
                q = f"{keyword}怎么处理"
            seeds.append({
                "source": "ticket_analysis",
                "question": q,
                "answer": f"高频问题（出现 {count} 次），来自工单: {', '.join([t['id'] for t in related_tickets])}",
                "type": "ticket_suggestion",
                "keyword": keyword,
                "frequency": count,
                "tickets": [t["id"] for t in related_tickets],
            })

    return seeds


def deduplicate_seeds(seeds, existing_ids, existing_keywords):
    """去重：过滤掉已有 FAQ 已覆盖的"""
    deduped = []
    seen_questions = set()

    # 构建已有 FAQ 的关键词覆盖
    covered_set = set()
    for kw_str in existing_keywords:
        for kw in kw_str.split(","):
            covered_set.add(kw.strip().strip("'\""))

    for seed in seeds:
        q = seed["question"]
        # 去重
        q_fingerprint = q.replace(" ", "").lower()[:30]
        if q_fingerprint in seen_questions:
            continue
        seen_questions.add(q_fingerprint)

        # 检查是否已经被覆盖
        is_covered = False
        for kw in covered_set:
            if kw in q or q in kw:
                is_covered = True
                break
        if is_covered:
            continue

        deduped.append(seed)

    return deduped


def generate_drafts(seeds, existing_ids):
    """生成草稿 FAQ 文件"""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    # 读取模板
    template_text = ""
    if TEMPLATE_FILE.exists():
        template_text = TEMPLATE_FILE.read_text(encoding="utf-8")

    drafts = []
    for i, seed in enumerate(seeds[:30]):  # 最多 30 个
        q = seed["question"]
        q_slug = q.replace(" ", "_").replace("?", "").replace("？", "").replace("怎么", "howto")[:30]
        q_slug = re.sub(r'[^\w一-鿿_-]', '', q_slug)

        # 推断部门
        dept = "数智财务组"
        sub_module = "浙里报"
        dept_code = "SZ"
        module_code = "ZLB"

        # 生成 ID
        seq = 1
        while f"FAQ-{dept_code}-{module_code}-{seq:03d}" in existing_ids:
            seq += 1
        faq_id = f"FAQ-{dept_code}-{module_code}-{seq:03d}"
        existing_ids.add(faq_id)

        # 提取关键词
        q_words = [w for w in re.findall(r'[一-鿿]{2,5}', q) if len(w) >= 2]
        keywords = q_words[:5] + [seed.get("keyword", "")] if seed.get("keyword") else q_words[:5]
        keywords = list(set(kw for kw in keywords if kw))

        # 构建 frontmatter
        tickets_str = json.dumps(seed.get("tickets", []), ensure_ascii=False)
        frontmatter = f"""---
id: {faq_id}
title: {q}
keywords: {json.dumps(keywords, ensure_ascii=False)}
module: {sub_module}
dept: {dept}
sub_module: {sub_module}
scene: ""
status: active
version_from: ""
created: {date.today().isoformat()}
reviewed: {date.today().isoformat()}
related: []
tickets: {tickets_str}
---

# {q}

## 问题描述

*（待补充）*

## 原因分析

*（待补充）*

## 解决方法

*（待补充）*

## 排查要点

*（待补充）*

---
> 🏷️ **自动生成草稿** | 来源: {seed.get("source", "unknown")} | 类型: {seed.get("type", "unknown")}
> 请人工审核补充内容后，移入正式目录并更新 INDEX.md
"""

        draft_file = DRAFTS_DIR / f"{faq_id}_{q_slug}.md"
        draft_file.write_text(frontmatter, encoding="utf-8")

        drafts.append({
            "id": faq_id,
            "title": q,
            "file": str(draft_file.relative_to(PROJECT_DIR)),
            "source": seed.get("source", ""),
            "type": seed.get("type", ""),
            "keywords": keywords,
            "tickets": seed.get("tickets", []),
        })

    return drafts


def print_report(seeds, drafts, already_covered):
    """打印分析报告"""
    print(f"\n{'='*70}")
    print(f"FAQ 自动生成报告")
    print(f"日期: {date.today().isoformat()}")
    print(f"{'='*70}")

    # 分类统计
    kb_count = sum(1 for s in seeds if s.get("type", "").startswith("kb_"))
    ticket_count = sum(1 for s in seeds if s.get("type") == "ticket_suggestion")
    draft_count = len(drafts)

    print(f"\n📊 分析统计")
    print(f"  知识库来源: {kb_count} 个候选")
    print(f"  工单分析来源: {ticket_count} 个候选")
    print(f"  去重后: {len(seeds)} 个候选")
    print(f"  已有 FAQ 覆盖: {already_covered} 个")
    print(f"  生成草稿: {draft_count} 个")

    # 按类型分布
    if drafts:
        print(f"\n📝 草稿生成")
        for d in drafts:
            print(f"  [{d['id']}] {d['title']}")
            print(f"    来源: {d['source']} | 类型: {d['type']}")
            if d.get("tickets"):
                print(f"    工单: {', '.join(d['tickets'][:3])}")
            print(f"    文件: {d['file']}")

        print(f"\n💡 下一步")
        print(f"  1. 审核: 编辑 {DRAFTS_DIR}/ 下的草稿文件")
        print(f"  2. 入库: 将审核后的文件移到 {FAQ_DIR}/<业务组>/<子模块>/")
        print(f"  3. 索引: 运行 python3 scripts/faq_audit.py --fix")
        print(f"")
        print(f"  或直接运行 python3 scripts/faq_generate.py --drafts --apply 自动入库")


def main():
    args = sys.argv[1:]

    use_json = "--json" in args
    do_drafts = "--drafts" in args
    do_apply = "--apply" in args
    source_filter = None
    for i, arg in enumerate(args):
        if arg == "--source" and i + 1 < len(args):
            source_filter = args[i + 1]

    existing_ids, existing_keywords = load_existing_faqs()

    seeds = []

    # 来源1: 知识库
    if source_filter in (None, "kb"):
        if KB_DIR.exists():
            kb_seeds = extract_kb_faqs(KB_DIR)
            seeds.extend(kb_seeds)

    # 来源2: 工单分析
    if source_filter in (None, "tickets"):
        ticket_seeds = extract_ticket_faqs()
        seeds.extend(ticket_seeds)

    # 去重
    before_dedup = len(seeds)
    seeds = deduplicate_seeds(seeds, existing_ids, existing_keywords)
    already_covered = before_dedup - len(seeds)

    if use_json:
        output = {
            "total_candidates": before_dedup,
            "already_covered": already_covered,
            "new_candidates": len(seeds),
            "seeds": seeds[:30],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 生成草稿
    drafts = []
    if do_drafts:
        drafts = generate_drafts(seeds, existing_ids)

    if do_apply and drafts:
        # 自动入库：将草稿移到正式目录
        for d in drafts:
            dept = "数智财务组"
            sub = "浙里报"
            target_dir = FAQ_DIR / dept / sub
            target_dir.mkdir(parents=True, exist_ok=True)
            src = PROJECT_DIR / d["file"]
            dst = target_dir / src.name
            if src.exists():
                src.rename(dst)
                d["file"] = str(dst.relative_to(PROJECT_DIR))
                print(f"  ✅ 已入库: {dst}")
        # 更新 INDEX
        print(f"  🔄 更新 INDEX.md...")
        os.system(f"python3 {HERE}/faq_audit.py --fix > /dev/null 2>&1")
        print(f"  ✅ 完成，新增 {len(drafts)} 条 FAQ")

    print_report(seeds, drafts, already_covered)


if __name__ == "__main__":
    main()