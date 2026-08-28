#!/usr/bin/env python3
"""
query_parser.py - 搜索语法解析器

支持高级搜索语法，将用户查询解析为结构化参数。

支持的语法:
    field:value       字段过滤（dept, module, product, source, domain）
    -word             排除词
    "phrase"          精确短语匹配
    word1 AND word2   布尔与（默认行为）

用法:
    parser = QueryParser()
    parsed = parser.parse("dept:免疫规划组 接种")
    # → {"keywords": ["接种"], "filters": {"dept": ["免疫规划组"]}, "excludes": [], "phrases": []}
"""

import re
import logging

logger = logging.getLogger(__name__)


class QueryParser:
    """搜索语法解析器，将用户查询解析为结构化搜索参数。

    支持的字段过滤:
        dept:      部门（如 数智财务组、免疫规划组）
        module:     模块（如 预防接种、浙里报）
        product:    产品（如 浙里报旗舰版）
        domain:     业务域（如 浙里报）
        source:     来源类型（faq, kb, report）
        owner:      负责人

    支持的语法:
        -word                   排除包含 word 的结果
        "exact phrase"          精确短语匹配
        field:value             字段过滤
    """

    # 支持的过滤字段
    FILTER_FIELDS = {
        "dept", "department", "部门",
        "module", "模块",
        "product", "产品",
        "domain", "domain", "业务域",
        "source", "类型",
        "owner", "负责人",
    }

    # 字段名标准化
    FIELD_ALIASES = {
        "department": "dept",
        "部门": "dept",
        "模块": "module",
        "产品": "product",
        "业务域": "domain",
        "类型": "source",
        "负责人": "owner",
    }

    def __init__(self):
        self._field_pattern = None
        self._build_patterns()

    def _build_patterns(self):
        """构建正则表达式"""
        fields = "|".join(re.escape(f) for f in self.FILTER_FIELDS)
        self._field_pattern = re.compile(rf'\b({fields}):([^\s]+)', re.IGNORECASE)

    def parse(self, query: str) -> dict:
        """解析查询字符串，返回结构化搜索参数。

        返回:
        {
            "keywords": list[str],     # 自由文本关键词
            "filters": dict,           # {field: [values]}
            "excludes": list[str],     # 排除词
            "phrases": list[str],      # 精确短语
            "raw_query": str,          # 去除语法后的纯查询文本
        }
        """
        if not query or not query.strip():
            return {
                "keywords": [],
                "filters": {},
                "excludes": [],
                "phrases": [],
                "raw_query": "",
            }

        result = {
            "keywords": [],
            "filters": {},
            "excludes": [],
            "phrases": [],
            "raw_query": query.strip(),
        }

        working = query.strip()

        # 1. 提取精确短语 "phrase"
        phrase_matches = re.findall(r'"([^"]+)"', working)
        for phrase in phrase_matches:
            result["phrases"].append(phrase.strip())
            working = working.replace(f'"{phrase}"', '', 1)

        # 2. 提取排除词 -word
        exclude_matches = re.findall(r'(?<!\w)-(\S+)', working)
        for word in exclude_matches:
            result["excludes"].append(word.strip())
            working = re.sub(rf'(?<!\w)-{re.escape(word)}', '', working, count=1)

        # 3. 提取字段过滤 field:value
        for match in self._field_pattern.finditer(working):
            field = match.group(1).lower()
            value = match.group(2).strip()

            # 标准化字段名
            field = self.FIELD_ALIASES.get(field, field)

            if field not in result["filters"]:
                result["filters"][field] = []
            if value not in result["filters"][field]:
                result["filters"][field].append(value)

            # 移除已匹配的 field:value
            working = working.replace(match.group(0), '', 1)

        # 4. 处理 AND 关键字
        working = re.sub(r'\bAND\b', ' ', working, flags=re.IGNORECASE)

        # 5. 剩余文本作为关键词
        # 清理多余空格
        remaining = ' '.join(working.split())
        if remaining.strip():
            result["keywords"].append(remaining.strip())

        result["raw_query"] = remaining.strip()

        return result

    def has_advanced_syntax(self, query: str) -> bool:
        """检查查询是否包含高级搜索语法"""
        if not query:
            return False
        indicators = [
            r'\b(dept|department|module|product|domain|source|owner|部门|模块|产品|类型|负责人):\S+',
            r'(?<!\w)-\S+',
            r'"[^"]+"',
            r'\bAND\b',
        ]
        for pattern in indicators:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False

    def apply_filters(self, results: list, filters: dict) -> list:
        """对搜索结果应用字段过滤。

        results: 搜索结果列表
        filters: {field: [values]}
        """
        if not filters:
            return results

        filtered = []
        for r in results:
            match = True
            for field, values in filters.items():
                if not self._match_filter(r, field, values):
                    match = False
                    break
            if match:
                filtered.append(r)

        return filtered

    def _match_filter(self, result: dict, field: str, values: list) -> bool:
        """检查单个结果是否匹配过滤条件"""
        if not values:
            return True

        # 映射 field 到结果中的 key
        field_to_key = {
            "dept": ["dept", "department"],
            "module": ["module", "sub_module"],
            "product": ["product", "domain"],
            "domain": ["domain"],
            "source": ["source"],
            "owner": ["dev_owner", "module_owner"],
        }

        keys = field_to_key.get(field, [field])
        for value in values:
            value_lower = value.lower()
            matched = False
            for key in keys:
                result_value = result.get(key, "")
                if isinstance(result_value, str):
                    if value_lower in result_value.lower():
                        matched = True
                        break
                elif isinstance(result_value, list):
                    for item in result_value:
                        if value_lower in str(item).lower():
                            matched = True
                            break
            if not matched:
                return False

        return True

    def apply_excludes(self, results: list, excludes: list) -> list:
        """过滤掉包含排除词的结果"""
        if not excludes:
            return results

        filtered = []
        for r in results:
            # 检查所有文本字段
            text_fields = [
                r.get("title", ""),
                r.get("snippets", ""),
                r.get("content_sample", ""),
                r.get("module", ""),
                r.get("dept", ""),
                " ".join(r.get("match_terms", [])),
            ]
            combined = " ".join(str(f) for f in text_fields if f).lower()

            excluded = False
            for word in excludes:
                if word.lower() in combined:
                    excluded = True
                    break

            if not excluded:
                filtered.append(r)

        return filtered


if __name__ == "__main__":
    parser = QueryParser()

    tests = [
        'dept:免疫规划组 接种',
        'module:预防接种 新生儿',
        'dept:数智财务组 module:浙里报 报销',
        '"报销单选择" -发票',
        '报销 AND 审批',
        'product:浙里报 支付',
        'source:faq 档案',
        '部门:数智财务组 模块:收费平台',
        '接种证 免疫规划',  # 普通查询
    ]

    for q in tests:
        parsed = parser.parse(q)
        print(f"\n查询: {q}")
        print(f"  关键词: {parsed['keywords']}")
        print(f"  过滤: {parsed['filters']}")
        print(f"  排除: {parsed['excludes']}")
        print(f"  短语: {parsed['phrases']}")
        print(f"  高级语法: {parser.has_advanced_syntax(q)}")