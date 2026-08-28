#!/usr/bin/env python3
"""
FAQ 与工单关联管理工具

用法:
    python3 faq_ticket_link.py                          # 查看关联总览
    python3 faq_ticket_link.py --report                 # 详细关联报告
    python3 faq_ticket_link.py --orphan-faqs            # 查看无工单来源的 FAQ
    python3 faq_ticket_link.py --unresolved             # 查看高频工单中无 FAQ 覆盖的
    python3 faq_ticket_link.py --link FAQ-SZ-ZLB-001 TKT202605061542585571124  # 添加工单关联
    python3 faq_ticket_link.py --scan-tickets           # 扫描工单文档，匹配已有 FAQ
    python3 faq_ticket_link.py --json                   # JSON 格式输出

关联逻辑:
    FAQ → 工单: FAQ frontmatter 中的 tickets 字段
    工单 → FAQ: 工单分析文档中的 FAQ ID 引用，或关键词匹配推断
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import date
from collections import defaultdict, Counter

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
FAQ_DIR = PROJECT_DIR / "FAQ知识库"
KB_DIR = PROJECT_DIR / "knowledge"

# 工单分析文档搜索路径
TICKET_DOC_PATHS = [
    PROJECT_DIR.parent.parent / "其他文档区" / "技术支持工单四大类场景归类分析.md",
    PROJECT_DIR.parent.parent / "其他文档区" / "技术支持工单场景归类分析.md",
    PROJECT_DIR.parent.parent / "2026报表数据知识库" / "周报",
    PROJECT_DIR.parent.parent / "projects" / "report-system" / "output",
]

# 工单号正则（支持 20+ 位数字时间戳或 TKT 前缀）
TICKET_ID_RE = re.compile(r'TKT\d{14,24}|(?<![a-zA-Z\d])\d{20,24}(?![a-zA-Z\d])', re.IGNORECASE)
FAQ_ID_RE = re.compile(r'FAQ-[A-Z]+-[A-Z]+-\d+')


def parse_frontmatter(text):
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}
    data = {}
    for line in fm_match.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in ("keywords", "related", "tickets"):
            value = value.strip("[]")
            data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
        else:
            data[key] = value
    return data


def collect_all_faqs():
    """收集所有 FAQ 及其工单关联"""
    faqs = []
    if not FAQ_DIR.exists():
        return faqs
    for md_file in sorted(FAQ_DIR.rglob("*.md")):
        if md_file.name in ("TEMPLATE.md", "INDEX.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            rel = md_file.relative_to(FAQ_DIR)
            faqs.append({
                "id": fm.get("id", ""),
                "title": fm.get("title", ""),
                "tickets": fm.get("tickets", []),
                "keywords": fm.get("keywords", []),
                "status": fm.get("status", "active"),
                "path": str(rel),
                "dept": fm.get("dept", ""),
            })
        except Exception:
            pass
    return faqs


def scan_ticket_docs():
    """扫描工单分析文档，提取工单号和高频关键词"""
    tickets = {}  # {ticket_id: {title, keywords, faq_refs, file}}
    keywords_counter = Counter()
    ticket_keywords = defaultdict(list)  # ticket_id → [keywords]

    for search_path in TICKET_DOC_PATHS:
        if not search_path.exists():
            continue
        for md_file in search_path.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # 提取工单号
            found_tickets = TICKET_ID_RE.findall(text)
            for tid in found_tickets:
                if tid not in tickets:
                    # 尝试提取工单标题（工单号后面的内容）
                    title_match = re.search(
                        re.escape(tid) + r'\s*[|｜]\s*(.+?)(?:\n|$)', text
                    )
                    title = title_match.group(1).strip() if title_match else ""
                    tickets[tid] = {
                        "title": title[:80],
                        "keywords": [],
                        "faq_refs": [],
                        "file": str(md_file.relative_to(PROJECT_DIR.parent.parent)),
                        "frequency": 1,
                    }
                else:
                    tickets[tid]["frequency"] += 1

            # 提取 FAQ 引用
            faq_refs = FAQ_ID_RE.findall(text)
            for fid in faq_refs:
                for tid in found_tickets:
                    if tid in tickets:
                        if fid not in tickets[tid]["faq_refs"]:
                            tickets[tid]["faq_refs"].append(fid)

            # 提取工单关键词（从表格行中）
            for line in text.split("\n"):
                ticket_match = TICKET_ID_RE.search(line)
                if ticket_match:
                    tid = ticket_match.group()
                    # 提取工单描述中的关键词
                    cells = [c.strip() for c in line.split("|")]
                    for cell in cells:
                        words = [w for w in cell.split() if len(w) >= 2 and not w.startswith("TKT")]
                        for w in words:
                            keywords_counter[w] += 1
                            if tid in tickets:
                                if w not in tickets[tid]["keywords"]:
                                    tickets[tid]["keywords"].append(w)

    return tickets, keywords_counter


def match_faqs_to_tickets(faqs, tickets):
    """尝试将 FAQ 与工单通过关键词匹配"""
    matches = []
    for faq in faqs:
        faq_kw = set(faq.get("keywords", []))
        faq_title_words = set(faq.get("title", ""))
        matched_tickets = []

        for tid, tinfo in tickets.items():
            ticket_kw = set(tinfo.get("keywords", []))
            ticket_title_words = set(tinfo.get("title", ""))
            # 关键词匹配
            overlap = faq_kw & ticket_kw
            title_overlap = faq_title_words & ticket_title_words
            if overlap or title_overlap:
                matched_tickets.append({
                    "id": tid,
                    "title": tinfo.get("title", ""),
                    "matched_keywords": list(overlap)[:5],
                    "score": len(overlap) + len(title_overlap),
                })

        # 按匹配度排序
        matched_tickets.sort(key=lambda x: x["score"], reverse=True)

        if matched_tickets:
            matches.append({
                "faq_id": faq["id"],
                "faq_title": faq["title"],
                "existing_tickets": faq.get("tickets", []),
                "suggested_tickets": matched_tickets[:5],
            })

    return matches


def add_ticket_link(faq_id, ticket_id):
    """为 FAQ 添加工单关联"""
    faq_file = None
    for md_file in sorted(FAQ_DIR.rglob("*.md")):
        if md_file.name in ("TEMPLATE.md", "INDEX.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm.get("id") == faq_id:
                faq_file = md_file
                break
        except Exception:
            pass

    if not faq_file:
        print(f"❌ 未找到 FAQ: {faq_id}")
        return False

    text = faq_file.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)

    existing_tickets = fm.get("tickets", [])
    if ticket_id in existing_tickets:
        print(f"⚠ {faq_id} 已关联工单 {ticket_id}")
        return True

    existing_tickets.append(ticket_id)
    new_tickets_str = "[" + ", ".join(existing_tickets) + "]"

    # 替换 tickets 行
    old_tickets_line = re.search(r'^tickets:\s*\[.*?\]', text, re.MULTILINE)
    if old_tickets_line:
        text = text.replace(old_tickets_line.group(), f"tickets: {new_tickets_str}")
    else:
        # 在 related 行后插入
        text = re.sub(
            r'(related:\s*\[.*?\])',
            f'\\1\ntickets: {new_tickets_str}',
            text
        )

    faq_file.write_text(text, encoding="utf-8")
    print(f"✅ {faq_id} 已关联工单 {ticket_id}")
    return True


def report_unresolved_tickets(tickets, faqs, keywords_counter):
    """报告高频工单中无 FAQ 覆盖的"""
    # 已有 FAQ 覆盖的工单
    covered_tickets = set()
    for faq in faqs:
        for tid in faq.get("tickets", []):
            covered_tickets.add(tid)

    # 高频关键词
    top_keywords = keywords_counter.most_common(50)

    # 已有 FAQ 覆盖的关键词
    covered_keywords = set()
    for faq in faqs:
        for kw in faq.get("keywords", []):
            covered_keywords.add(kw)

    unresolved = []
    for kw, count in top_keywords:
        if kw not in covered_keywords and count >= 3 and len(kw) >= 3:
            # 找到相关工单
            related_tickets = []
            for tid, tinfo in tickets.items():
                if kw in tinfo.get("keywords", []) or kw in tinfo.get("title", ""):
                    related_tickets.append(tid)
            unresolved.append({
                "keyword": kw,
                "frequency": count,
                "related_tickets": related_tickets[:5],
            })

    return unresolved


def print_report(faqs, tickets, matches, unresolved):
    """打印详细报告"""
    # 表头
    print(f"\n{'='*70}")
    print(f"FAQ ↔ 工单 关联报告")
    print(f"日期: {date.today().isoformat()}")
    print(f"{'='*70}")

    # 统计
    total_faqs = len(faqs)
    faqs_with_tickets = sum(1 for f in faqs if f.get("tickets"))
    total_tickets = len(tickets)
    faq_linked_tickets = set()
    for f in faqs:
        for t in f.get("tickets", []):
            faq_linked_tickets.add(t)

    print(f"\n📊 统计概览")
    print(f"  FAQ 总数: {total_faqs}")
    print(f"  已关联工单的 FAQ: {faqs_with_tickets}")
    print(f"  无工单来源的 FAQ: {total_faqs - faqs_with_tickets}")
    print(f"  扫描到的工单数: {total_tickets}")
    print(f"  已关联 FAQ 的工单: {len(faq_linked_tickets)}")

    # 关联详情
    if faqs_with_tickets:
        print(f"\n📋 FAQ → 工单 关联")
        for f in faqs:
            if f.get("tickets"):
                tids = ", ".join(f["tickets"])
                print(f"  [{f['id']}] {f['title']}")
                print(f"    工单: {tids}")

    # 建议匹配
    if matches:
        print(f"\n💡 建议关联（关键词匹配）")
        for m in matches[:10]:
            if not m["existing_tickets"]:
                suggested = m["suggested_tickets"][:3]
                if suggested:
                    print(f"  [{m['faq_id']}] {m['faq_title']}")
                    for st in suggested:
                        print(f"    → {st['id']} ({st['title'][:40]}) [匹配度: {st['score']}]")

    # 未覆盖高频词
    if unresolved:
        print(f"\n🔴 高频关键词无 FAQ 覆盖 (Top {len(unresolved)})")
        for item in unresolved[:15]:
            tids = ", ".join(item["related_tickets"][:3])
            print(f"  '{item['keyword']}' (出现 {item['frequency']} 次)")
            print(f"    相关工单: {tids}")


def main():
    args = sys.argv[1:]

    faqs = collect_all_faqs()
    tickets, keywords_counter = scan_ticket_docs()
    matches = match_faqs_to_tickets(faqs, tickets)
    unresolved = report_unresolved_tickets(tickets, faqs, keywords_counter)

    if "--link" in args:
        idx = args.index("--link")
        if idx + 2 < len(args):
            faq_id = args[idx + 1]
            ticket_id = args[idx + 2]
            add_ticket_link(faq_id, ticket_id)
            return
        else:
            print("用法: python3 faq_ticket_link.py --link <FAQ_ID> <TICKET_ID>")
            return

    if "--json" in args:
        output = {
            "faqs": [{"id": f["id"], "title": f["title"], "tickets": f["tickets"]} for f in faqs],
            "ticket_count": len(tickets),
            "unresolved_keywords": unresolved,
            "suggested_matches": [
                {"faq_id": m["faq_id"], "suggested_tickets": [
                    {"id": s["id"], "title": s["title"], "score": s["score"]}
                    for s in m["suggested_tickets"][:3]
                ]}
                for m in matches if not m["existing_tickets"]
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if "--orphan-faqs" in args:
        print(f"\n🔴 无工单来源的 FAQ:")
        count = 0
        for f in faqs:
            if not f.get("tickets"):
                print(f"  [{f['id']}] {f['title']} ({f['dept']})")
                count += 1
        if count == 0:
            print("  ✅ 所有 FAQ 都有工单来源")
        return

    if "--scan-tickets" in args:
        print(f"\n📋 扫描工单文档匹配 FAQ:")
        for m in matches:
            print(f"\n  [{m['faq_id']}] {m['faq_title']}")
            if m["existing_tickets"]:
                print(f"    已有工单: {', '.join(m['existing_tickets'])}")
            if m["suggested_tickets"]:
                print(f"    建议添加:")
                for st in m["suggested_tickets"][:3]:
                    print(f"      {st['id']} - {st['title'][:50]} (匹配度: {st['score']})")
                    print(f"      执行: python3 faq_ticket_link.py --link {m['faq_id']} {st['id']}")
        return

    # 默认：打印报告
    print_report(faqs, tickets, matches, unresolved)


if __name__ == "__main__":
    main()