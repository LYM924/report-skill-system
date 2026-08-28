#!/usr/bin/env python3
"""
spell_corrector.py - 拼写纠错模块

基于编辑距离 + 词频的拼写纠错，用于搜索查询纠错。
支持中文和英文，与 BM25 倒排索引集成。

用法:
    corrector = SpellCorrector()
    corrector.build_from_inverted_index(bm25.inverted_index)
    correction = corrector.correct("这里报")  # → "浙里报"
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)


class SpellCorrector:
    """中文拼写纠错器。

    核心算法：
    1. 从 BM25 倒排索引构建词频字典（高频词优先）
    2. 对查询中的每个词，生成编辑距离 1-2 的候选词
    3. 按词频 × 编辑距离加权评分，返回最佳纠正
    """

    # 中文常见形近字/音近字混淆对（扩展纠错覆盖）
    PHONETIC_CONFUSIONS = {
        # 拼音混淆
        'z': 'zh', 'c': 'ch', 's': 'sh',
        'zh': 'z', 'ch': 'c', 'sh': 's',
        'n': 'l', 'l': 'n',
        'r': 'l',
        'f': 'h', 'h': 'f',
        'an': 'ang', 'ang': 'an',
        'en': 'eng', 'eng': 'en',
        'in': 'ing', 'ing': 'in',
    }

    # 常见中文输入法错误（拼音相同但选字不同）
    COMMON_TYPOS = {
        '这里': '浙里',
        '报到': '报销',
        '免役': '免疫',
        '一只': '一致',
        '附件': '附近',
        '定单': '订单',
        '记划': '计划',
        '接钟': '接种',
        '工单': '工单',
        '查寻': '查询',
        '收索': '搜索',
        '添交': '提交',
        '保纯': '保存',
        '更该': '更改',
        '会被': '回报',
        '规化': '规划',
        '业物': '业务',
        '款向': '款项',
        '年都': '年度',
        '当案': '档案',
        '借月': '借阅',
        '标指': '指标',
        '只表': '指标',
        '子算': '预算',
        '玉算': '预算',
        '付钱': '支付',
        '收钱': '收费',
        '开票': '开票',
        '绍里报': '浙里报',
        '这里报': '浙里报',
        '这理报': '浙里报',
        '哲里报': '浙里报',
        '辉报账': '徽报账',
        '回报账': '徽报账',
        '数理通': '数里通',
        '捞里报': '浙里报',
    }

    def __init__(self):
        self.word_freq = Counter()  # 词 → 频率
        self.all_words = set()      # 所有已知词
        self.max_word_len = 0

    def build_from_inverted_index(self, inverted_index: dict):
        """从 BM25 倒排索引构建词频字典。

        inverted_index: term -> {doc_id: term_frequency}
        """
        self.word_freq = Counter()
        for term, postings in inverted_index.items():
            if len(term) >= 2:  # 至少 2 个字符
                total_freq = sum(postings.values())
                self.word_freq[term] = total_freq

        self.all_words = set(self.word_freq.keys())
        self.max_word_len = max((len(w) for w in self.all_words), default=0)
        logger.info(f"SpellCorrector: loaded {len(self.all_words)} words from inverted index")

    def build_from_word_list(self, words: list):
        """从词列表构建词频字典（兼容非 BM25 场景）"""
        self.word_freq = Counter()
        for word in words:
            if len(word) >= 2:
                self.word_freq[word] += 1
        self.all_words = set(self.word_freq.keys())
        self.max_word_len = max((len(w) for w in self.all_words), default=0)

    def add_words(self, words: list):
        """追加词到词典（用于从 keyword_map、module_map 补充）"""
        for word in words:
            if len(word) >= 2:
                if word not in self.word_freq:
                    self.word_freq[word] = 1
                else:
                    self.word_freq[word] += 1
        self.all_words = set(self.word_freq.keys())
        self.max_word_len = max((len(w) for w in self.all_words), default=0)

    def correct(self, query: str) -> dict:
        """对查询进行拼写纠错。

        返回: {
            "original": "这里报",
            "corrected": "浙里报",
            "corrections": [{"original": "这里报", "correction": "浙里报", "confidence": 0.85}],
            "has_correction": True
        }
        """
        if not query or not self.all_words:
            return {
                "original": query,
                "corrected": query,
                "corrections": [],
                "has_correction": False,
            }

        # 1. 先检查常见混淆表
        corrected = self._check_common_typos(query)
        if corrected != query:
            return {
                "original": query,
                "corrected": corrected,
                "corrections": [{"original": query, "correction": corrected, "confidence": 0.95}],
                "has_correction": True,
            }

        # 2. 对每个 token 做编辑距离纠错
        corrections = []
        tokens = self._tokenize_query(query)
        corrected_tokens = []

        for token in tokens:
            if len(token) < 2:
                corrected_tokens.append(token)
                continue

            # 如果 token 本身在词典中，不需要纠错
            if token in self.all_words:
                corrected_tokens.append(token)
                continue

            # 生成候选词
            candidates = self._generate_candidates(token)
            if not candidates:
                corrected_tokens.append(token)
                continue

            # 评分并选最佳
            best = self._rank_candidates(token, candidates)
            if best and best["confidence"] > 0.3:
                corrections.append({
                    "original": token,
                    "correction": best["word"],
                    "confidence": round(best["confidence"], 2),
                })
                corrected_tokens.append(best["word"])
            else:
                corrected_tokens.append(token)

        corrected_query = "".join(corrected_tokens) if all(
            len(t) == 1 for t in tokens
        ) else " ".join(corrected_tokens)

        return {
            "original": query,
            "corrected": corrected_query if corrections else query,
            "corrections": corrections,
            "has_correction": len(corrections) > 0,
        }

    def _tokenize_query(self, query: str) -> list:
        """将查询切分为候选纠错单元（中文按 2-4 字切分，英文按词切分）"""
        tokens = []
        i = 0
        while i < len(query):
            char = query[i]
            if '一' <= char <= '鿿' or '㐀' <= char <= '䶿':
                # 中文字符：尝试匹配 2-4 字词组
                found = False
                for length in range(min(4, len(query) - i), 1, -1):
                    chunk = query[i:i + length]
                    if chunk in self.all_words:
                        tokens.append(chunk)
                        i += length
                        found = True
                        break
                    # 也检查常见混淆的 key
                    if chunk in self.COMMON_TYPOS:
                        tokens.append(chunk)
                        i += length
                        found = True
                        break
                if not found:
                    tokens.append(char)
                    i += 1
            elif char.isalpha():
                # 英文字符
                j = i
                while j < len(query) and query[j].isalpha():
                    j += 1
                tokens.append(query[i:j])
                i = j
            else:
                tokens.append(char)
                i += 1
        return tokens

    def _check_common_typos(self, query: str) -> str:
        """检查常见输入法错误混淆表"""
        result = query
        for wrong, correct in sorted(self.COMMON_TYPOS.items(), key=lambda x: -len(x[0])):
            if wrong in result:
                result = result.replace(wrong, correct)
        return result

    def _generate_candidates(self, token: str) -> list:
        """生成编辑距离 1-2 的候选词"""
        candidates = set()

        # 从常见混淆表生成
        for wrong, correct in self.COMMON_TYPOS.items():
            if token in wrong or wrong in token:
                if correct in self.all_words:
                    candidates.add(correct)

        # 编辑距离 1：在词典中找长度相近的词
        token_len = len(token)
        for word in self.all_words:
            word_len = len(word)
            if abs(word_len - token_len) > 2:
                continue

            dist = self._edit_distance(token, word)
            if dist <= 2:
                candidates.add(word)

        # 限制候选数量
        return list(candidates)[:50]

    def _edit_distance(self, s1: str, s2: str) -> int:
        """计算 Levenshtein 编辑距离（支持中文）"""
        if len(s1) < len(s2):
            return self._edit_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                # 插入、删除、替换
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (0 if c1 == c2 else 1)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]

    def _rank_candidates(self, token: str, candidates: list) -> dict:
        """对候选词按词频和编辑距离加权评分"""
        if not candidates:
            return None

        scored = []
        for word in candidates:
            dist = self._edit_distance(token, word)
            freq = self.word_freq.get(word, 1)

            # 评分：词频越高越好，编辑距离越小越好
            # 编辑距离 1: 权重 0.8, 编辑距离 2: 权重 0.5
            dist_weight = {1: 0.8, 2: 0.5, 0: 1.0}.get(dist, 0.2)

            # 长度相似度（长度越接近越好）
            len_ratio = min(len(token), len(word)) / max(len(token), len(word), 1)

            # 首字相同加分（中文搜索中首字很重要）
            first_char_bonus = 1.5 if token[0] == word[0] else 1.0

            score = dist_weight * len_ratio * first_char_bonus
            # 词频取对数平滑
            freq_boost = 1.0 + min(0.3, 0.1 * (freq ** 0.3))
            score *= freq_boost

            scored.append({
                "word": word,
                "distance": dist,
                "frequency": freq,
                "confidence": round(score, 2),
            })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored[0] if scored else None


# ---------- 便捷函数 ----------

def create_corrector(engine) -> SpellCorrector:
    """从 SearchEngine 实例创建纠错器"""
    corrector = SpellCorrector()

    # 从 BM25 倒排索引构建
    if engine.bm25 and engine.bm25.inverted_index:
        corrector.build_from_inverted_index(engine.bm25.inverted_index)

    # 补充关键词索引中的词
    if engine.keyword_map:
        corrector.add_words(list(engine.keyword_map.keys()))

    # 补充模块名
    if engine.module_map:
        corrector.add_words(list(engine.module_map.keys()))

    # 补充菜单名
    if engine.menu_map:
        corrector.add_words(list(engine.menu_map.keys()))

    # 补充 FAQ 标题中的词
    for doc in engine.faq_docs:
        title = doc.get("title", "")
        if title:
            import jieba
            tokens = [t.strip() for t in jieba.cut(title) if len(t.strip()) >= 2]
            corrector.add_words(tokens)

    return corrector


if __name__ == "__main__":
    # 独立测试
    c = SpellCorrector()
    c.add_words(["浙里报", "报销", "免疫规划", "预防接种", "电子档案", "发票平台",
                  "收费平台", "徽报账", "数里通", "银行回单", "差旅报销单", "申请单",
                  "预算中心", "合同管理", "支付", "审批", "用款计划", "公务卡"])
    c.add_words(["这里报", "这里"])  # 模拟错误词在索引中

    tests = ["这里报", "免役", "子算", "绍里报", "辉报账", "报销", "接钟"]
    for q in tests:
        r = c.correct(q)
        if r["has_correction"]:
            for corr in r["corrections"]:
                print(f"  {corr['original']} → {corr['correction']} (confidence: {corr['confidence']})")
        else:
            print(f"  {q} → (no correction needed)")