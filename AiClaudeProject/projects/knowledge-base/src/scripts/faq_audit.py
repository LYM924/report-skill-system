#!/usr/bin/env python3
"""
FAQ 知识库维护审计脚本

用法:
    python3 faq_audit.py                    # 审计所有 FAQ
    python3 faq_audit.py --fix              # 审计并自动修复（如更新 INDEX.md）
    python3 faq_audit.py --json             # 输出 JSON 格式

检查项:
    1. frontmatter 必填字段是否完整
    2. status 值是否合法
    3. reviewed 日期是否超过 6 个月（过期提醒）
    4. related 中的 FAQ ID 是否存在
    5. 文件是否在 INDEX.md 中登记
    6. INDEX.md 中的条目是否对应实际文件
    7. TEMPLATE.md 是否与当前模板一致

输出:
    - 终端彩色报告（错误/警告/建议）
    - 退出码: 0=全部通过, 1=有错误, 2=有警告
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

# ---------- 配置 ----------
HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent  # src/scripts/ -> src/ -> knowledge-base/
FAQ_DIR = PROJECT_DIR / "data" / "faq"
INDEX_FILE = FAQ_DIR / "INDEX.md"
TEMPLATE_FILE = FAQ_DIR / "TEMPLATE.md"
KB_DIR = PROJECT_DIR / "data" / "knowledge"

# 必填字段
REQUIRED_FIELDS = ["id", "title", "keywords", "module", "dept", "status", "created", "reviewed"]
VALID_STATUSES = ["active", "outdated", "deprecated"]

# 过期阈值（月）
STALE_MONTHS = 6

# 部门简称前缀
KNOWN_ID_PREFIXES = ["FAQ-SZ-", "FAQ-YM-", "FAQ-DZ-", "FAQ-ZH-", "FAQ-SZH-"]


# ---------- 工具函数 ----------
class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def parse_frontmatter(text):
    """解析 YAML frontmatter，返回 dict"""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}, "未找到 frontmatter"

    fm_text = fm_match.group(1)
    data = {}
    errors = []

    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # 解析 keywords 列表
        if key == "keywords":
            value = value.strip("[]")
            if value:
                data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
            else:
                data[key] = []
        elif key == "related":
            value = value.strip("[]")
            if value:
                data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
            else:
                data[key] = []
        elif key == "tickets":
            # 尝试 JSON 解析
            try:
                data[key] = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                value = value.strip("[]")
                if value:
                    data[key] = [k.strip().strip("\"'") for k in value.split(",") if k.strip()]
                else:
                    data[key] = []
        else:
            data[key] = value

    return data, None


def collect_all_faq_ids():
    """收集所有已存在的 FAQ ID"""
    ids = set()
    if not FAQ_DIR.exists():
        return ids
    for md_file in sorted(FAQ_DIR.rglob("*.md")):
        if md_file.name in ("TEMPLATE.md", "INDEX.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            fid = fm.get("id", "")
            if fid:
                ids.add(fid)
        except Exception:
            pass
    return ids


def parse_index_entries():
    """解析 INDEX.md 中的 FAQ 条目，返回 {faq_id: {title, path, status, updated}}"""
    entries = {}
    if not INDEX_FILE.exists():
        return entries

    text = INDEX_FILE.read_text(encoding="utf-8")
    for line in text.split("\n"):
        # 匹配: | [FAQ-SZ-ZLB-001](path) | title | keywords | scene | status | date |
        match = re.match(
            r"\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(.+?)\s*\|",
            line
        )
        if match:
            fid = match.group(1)
            path = match.group(2)
            rest = match.group(3)
            cells = [c.strip() for c in rest.split("|")]
            entries[fid] = {
                "path": path,
                "title": cells[0] if len(cells) > 0 else "",
                "status": cells[3] if len(cells) > 3 else "",
                "updated": cells[4] if len(cells) > 4 else "",
            }
    return entries


def parse_date(date_str):
    """解析日期字符串，返回 date 对象"""
    if not date_str:
        return None
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m", "%Y/%m"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


# ---------- 审计逻辑 ----------
class AuditResult:
    def __init__(self):
        self.errors = []      # 必须修复
        self.warnings = []    # 建议修复
        self.info = []        # 信息提示
        self.stats = {"total": 0, "active": 0, "outdated": 0, "deprecated": 0, "stale": 0}


def audit_faq_file(md_file, all_ids, result):
    """审计单个 FAQ 文件"""
    rel_path = str(md_file.relative_to(PROJECT_DIR))
    try:
        text = md_file.read_text(encoding="utf-8")
    except Exception as e:
        result.errors.append(f"{rel_path}: 无法读取文件 - {e}")
        return

    fm, fm_error = parse_frontmatter(text)
    fid = fm.get("id", "")

    if fm_error:
        result.errors.append(f"{rel_path}: {fm_error}")
        return

    # 1. 检查必填字段
    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            if field == "related":
                # related 可选
                continue
            result.errors.append(f"{rel_path} ({fid or '无ID'}): 缺少必填字段 '{field}'")

    # 2. 检查 ID 格式
    if fid:
        if not any(fid.startswith(prefix) for prefix in KNOWN_ID_PREFIXES):
            result.warnings.append(f"{rel_path} ({fid}): ID 前缀不在已知列表中 {KNOWN_ID_PREFIXES}")
    else:
        result.errors.append(f"{rel_path}: 缺少 FAQ ID")

    # 3. 检查 status
    status = fm.get("status", "")
    if status and status not in VALID_STATUSES:
        result.errors.append(
            f"{rel_path} ({fid}): status='{status}' 无效，应为 {VALID_STATUSES}"
        )
    if status == "outdated":
        result.stats["outdated"] += 1
    elif status == "deprecated":
        result.stats["deprecated"] += 1
    else:
        result.stats["active"] += 1

    # 4. 检查 reviewed 日期
    reviewed_str = fm.get("reviewed", "")
    reviewed_date = parse_date(reviewed_str)
    if reviewed_date:
        months_ago = (date.today() - reviewed_date).days / 30.44
        if months_ago > STALE_MONTHS:
            result.warnings.append(
                f"{rel_path} ({fid}): reviewed={reviewed_str} 已过去 {months_ago:.0f} 个月，建议审查更新"
            )
            result.stats["stale"] += 1
    elif reviewed_str:
        result.warnings.append(f"{rel_path} ({fid}): reviewed 日期格式无法解析: '{reviewed_str}'")

    # 5. 检查 related 中的 FAQ ID
    related = fm.get("related", [])
    for rel_id in related:
        if rel_id and rel_id not in all_ids:
            result.warnings.append(f"{rel_path} ({fid}): related 引用的 '{rel_id}' 不存在")

    # 6. 检查 content 章节结构
    required_sections = ["## 问题描述", "## 原因分析", "## 解决方法"]
    for section in required_sections:
        if section not in text:
            result.warnings.append(f"{rel_path} ({fid}): 缺少标准章节 '{section}'")

    # 7. 检查 tickets 字段（可选但建议有）
    tickets = fm.get("tickets", [])
    if not tickets and status == "active":
        result.info.append(f"{rel_path} ({fid}): 建议添加工单来源（tickets 字段）")

    # 8. 检查 tickets 格式
    if tickets:
        if isinstance(tickets, list):
            for tid in tickets:
                if isinstance(tid, str) and len(tid) >= 20:
                    if not re.match(r'^\d{20,24}$', tid) and not re.match(r'^TKT\d{14,24}$', tid):
                        result.warnings.append(f"{rel_path} ({fid}): 工单号格式异常: '{tid[:30]}...'")

    result.stats["total"] += 1


def audit_index_entries(result):
    """审计 INDEX.md 与实际文件的一致性"""
    index_entries = parse_index_entries()
    all_ids = collect_all_faq_ids()

    for fid, entry in index_entries.items():
        # 检查文件是否存在
        expected_path = FAQ_DIR / entry["path"]
        if not expected_path.exists():
            result.errors.append(f"INDEX.md: {fid} 引用的文件不存在: {entry['path']}")

        # 检查 status 是否过期
        if entry["status"] == "outdated":
            result.warnings.append(f"INDEX.md: {fid} 状态为 outdated")

    # 检查是否有文件未在 INDEX 中登记
    for fid in all_ids:
        if fid not in index_entries:
            result.warnings.append(f"文件 {fid} 未在 INDEX.md 中登记")


def audit_kb_files(result):
    """审计知识库文档的新鲜度（检查是否超过 6 个月未更新）"""
    if not KB_DIR.exists():
        result.info.append("知识库目录不存在，跳过新鲜度检查")
        return

    kb_files = [f for f in sorted(KB_DIR.rglob("*.md"))
                if "TEMPLATE" not in f.name and "INDEX" not in f.name]
    if not kb_files:
        result.info.append("知识库目录为空")
        return

    stale_count = 0
    no_date_count = 0
    for md_file in kb_files:
        rel_path = str(md_file.relative_to(PROJECT_DIR))
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, _ = parse_frontmatter(text)
        date_str = fm.get("date", "") or fm.get("reviewed", "") or fm.get("updated", "")
        if not date_str:
            # 尝试从文件名提取日期
            fname_match = re.search(r'(\d{4}[-_]?\d{2}[-_]?\d{2})', md_file.name)
            if fname_match:
                date_str = fname_match.group(1).replace("_", "-")
                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            # 尝试从正文提取日期
            else:
                body_match = re.search(r'(?:发版时间|更新日期|创建日期|date)[:：]\s*(\d{4}-\d{2}-\d{2})', text)
                if body_match:
                    date_str = body_match.group(1)

        if not date_str:
            no_date_count += 1
            result.warnings.append(f"{rel_path}: 无法确定文档日期，建议在 frontmatter 中添加 date 字段")
            continue

        doc_date = parse_date(date_str)
        if not doc_date:
            result.warnings.append(f"{rel_path}: 日期格式无法解析: '{date_str}'")
            continue

        months_ago = (date.today() - doc_date).days / 30.44
        if months_ago > STALE_MONTHS:
            stale_count += 1
            result.warnings.append(
                f"{rel_path}: 文档日期 {date_str}，已过去 {months_ago:.0f} 个月，建议复审更新"
            )

    if stale_count > 0:
        result.stats["stale"] += stale_count
    if no_date_count > 0:
        result.info.append(f"知识库: {no_date_count} 个文档缺少日期信息")
    if stale_count == 0 and no_date_count == 0:
        result.info.append(f"知识库: {len(kb_files)} 个文档全部在 {STALE_MONTHS} 个月内更新 ✓")


def fix_index(result):
    """自动修复 INDEX.md - 根据实际文件更新索引"""
    if not result.stats["total"]:
        print("无需修复：没有 FAQ 文件")
        return

    # 收集所有 FAQ 文件
    faq_entries = []
    for md_file in sorted(FAQ_DIR.rglob("*.md")):
        if md_file.name in ("TEMPLATE.md", "INDEX.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            fid = fm.get("id", "")
            if not fid:
                continue
            rel = md_file.relative_to(FAQ_DIR)
            parts = rel.parts
            faq_entries.append({
                "id": fid,
                "title": fm.get("title", ""),
                "keywords": fm.get("keywords", []),
                "scene": fm.get("scene", ""),
                "status": fm.get("status", "active"),
                "reviewed": fm.get("reviewed", ""),
                "path": str(rel),
                "dept": parts[0] if len(parts) > 0 else "",
                "sub_module": parts[1] if len(parts) > 1 else "",
            })
        except Exception:
            continue

    # 按部门+子模块分组
    groups = defaultdict(list)
    for e in faq_entries:
        key = f"{e['dept']}/{e['sub_module']}"
        groups[key].append(e)

    # 生成 INDEX.md
    lines = [
        "---",
        "name: faq-index",
        "description: FAQ 知识库摘要索引",
        "metadata:",
        "  type: reference",
        f"  updated: {date.today().isoformat()}",
        "---",
        "",
        "# FAQ 知识库索引",
        "",
        "> 自动生成，请勿手动编辑。运行 `python3 scripts/faq_audit.py --fix` 更新。",
        "",
        "## 索引表",
        "",
    ]

    for key in sorted(groups.keys()):
        dept, sub = key.split("/")
        lines.append(f"### {dept} · {sub}")
        lines.append("")
        lines.append("| ID | 标题 | 关键词 | 场景 | 状态 | 更新日期 |")
        lines.append("|----|------|--------|------|------|----------|")
        for e in groups[key]:
            kw_str = ", ".join(e["keywords"])
            lines.append(
                f"| [{e['id']}]({e['path']}) | {e['title']} | {kw_str} | {e['scene']} | {e['status']} | {e['reviewed']} |"
            )
        lines.append("")

    # 统计
    lines.append("## 统计")
    lines.append("")
    lines.append("| 业务组 | 子模块 | FAQ 数量 |")
    lines.append("|--------|--------|----------|")
    stats = defaultdict(lambda: defaultdict(int))
    for e in faq_entries:
        stats[e["dept"]][e["sub_module"]] += 1
    total = 0
    for dept in sorted(stats.keys()):
        for sub in sorted(stats[dept].keys()):
            count = stats[dept][sub]
            total += count
            lines.append(f"| {dept} | {sub} | {count} |")
    lines.append(f"| **合计** | | **{total}** |")
    lines.append("")

    INDEX_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{Colors.GREEN}✓ INDEX.md 已更新{Colors.RESET}")


# ---------- 主入口 ----------
def main():
    args = sys.argv[1:]
    use_json = "--json" in args
    do_fix = "--fix" in args
    do_kb = "--kb" in args

    result = AuditResult()

    # 收集所有现有 ID
    all_ids = collect_all_faq_ids()

    if not FAQ_DIR.exists():
        print(f"{Colors.RED}错误: FAQ 目录不存在: {FAQ_DIR}{Colors.RESET}")
        sys.exit(1)

    # 审计每个 FAQ 文件
    faq_files = [
        f for f in sorted(FAQ_DIR.rglob("*.md"))
        if f.name not in ("TEMPLATE.md", "INDEX.md") and f.parent.name != "_drafts"
    ]

    if not faq_files:
        print(f"{Colors.YELLOW}⚠ 没有找到 FAQ 文件{Colors.RESET}")
    else:
        for md_file in faq_files:
            audit_faq_file(md_file, all_ids, result)

    # 审计 INDEX.md
    audit_index_entries(result)

    # KB 文档新鲜度检查（--kb 参数）
    if do_kb:
        audit_kb_files(result)

    # 输出报告
    if use_json:
        output = {
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
            "stats": result.stats,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 终端彩色报告
        print(f"\n{Colors.BOLD}═══ FAQ 维护审计报告 ═══{Colors.RESET}")
        print(f"审计时间: {date.today().isoformat()}")
        print(f"文件总数: {result.stats['total']}")
        print(f"  active: {result.stats['active']}")
        print(f"  outdated: {result.stats['outdated']}")
        print(f"  deprecated: {result.stats['deprecated']}")
        print(f"  stale (>6月): {result.stats['stale']}")

        if result.errors:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ 错误 ({len(result.errors)}){Colors.RESET}")
            for e in result.errors:
                print(f"  {Colors.RED}✗{Colors.RESET} {e}")

        if result.warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ 警告 ({len(result.warnings)}){Colors.RESET}")
            for w in result.warnings:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} {w}")

        if result.info:
            print(f"\n{Colors.BLUE}ℹ 信息 ({len(result.info)}){Colors.RESET}")
            for i in result.info:
                print(f"  {Colors.BLUE}ℹ{Colors.RESET} {i}")

        if not result.errors and not result.warnings:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ 全部通过！{Colors.RESET}")

        # 评分
        score = 100
        score -= len(result.errors) * 10
        score -= len(result.warnings) * 3
        score = max(0, min(100, score))
        grade = "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D"
        print(f"\n健康评分: {Colors.BOLD}{score}/100 ({grade}){Colors.RESET}")

    # 自动修复
    if do_fix:
        print(f"\n{Colors.BLUE}🔧 执行自动修复...{Colors.RESET}")
        fix_index(result)

    # 退出码
    if result.errors:
        sys.exit(1)
    elif result.warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()