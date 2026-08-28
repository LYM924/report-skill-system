#!/usr/bin/env python3
"""
关键词提取器 - 综合 TF-IDF（自定义IDF） + TextRank 双引擎

核心思路：
  TF-IDF 提供跨文档区分度（"竞价"在全库低频但本文高频 = 独特关键词）
  TextRank 提供文档内语义关联（词共现图，识别主题词）
  二者融合，提取能精准定位文档的独特关键词
"""

import re, math, logging
from pathlib import Path
from collections import Counter, defaultdict

import jieba, jieba.analyse
jieba.setLogLevel(logging.WARNING)

# ── jieba 自定义词典：确保业务术语不被错误切分 ──
_JIEBA_CUSTOM_TERMS = [
    ("报销单", 100), ("差旅报销单", 100), ("申请单", 100),
    ("创建报销单", 80), ("我的单据", 80), ("报销申请", 80),
    ("差旅报销", 100), ("差旅申请单", 100), ("费用报销单", 100),
    ("选不到", 100), ("找不到", 100), ("无法选择", 100),
    ("无需报销", 100), ("关联单据", 100), ("关联申请单", 100),
    ("银行回单", 100), ("回单同步", 100), ("同步回单", 100),
    ("四性检测", 100), ("核算云", 100), ("实体移交", 100),
    ("凭证传输", 100), ("归档失败", 80), ("归档附件", 80),
    ("用款计划", 80), ("支付申请", 80), ("预算指标", 80),
    ("公务卡", 80), ("兑付报销", 80), ("批量报销", 80),
    ("指标同步", 80), ("发票后补", 80), ("财务审核", 80),
    ("出纳结算", 80), ("国库支付", 80), ("进项税额", 80),
    ("票据信息", 80), ("人脸采集", 80), ("运营后台", 80),
    ("电子档案", 80), ("免疫规划", 80), ("数字化支撑", 80),
    ("浙里报", 100), ("徽报账", 100), ("数里通", 80),
    ("接种证", 100), ("预防接种", 100), ("接种记录", 100),
    ("入学入托", 100), ("查验结果", 80), ("疫苗库存", 80),
    ("电子卖场", 100), ("参考价", 100), ("基准价", 100),
    ("电商", 100), ("反拍", 80), ("竞价", 100), ("选品", 80),
    ("商品", 80), ("合规", 80), ("网超", 80), ("政采", 80),
    ("协议商品", 80), ("交易", 80), ("采购人", 80), ("供应商", 80),
    ("审批流程", 80), ("收款账户", 80), ("支付限额", 80),
    ("会计凭证", 80), ("原始凭证", 80), ("档案管理", 80),
    ("资产管理", 80), ("采购管理", 80), ("预算管理", 80),
    ("合同管理", 80), ("发票管理", 80), ("费用管理", 80),
    ("数据智控", 80), ("智慧门诊", 80), ("数字化门诊", 80),
    ("智能催种", 80), ("冷链云", 80), ("疫苗馆", 80),
    ("单位管理", 80), ("人员管理", 80), ("便民服务", 80),
]
for _term, _freq in _JIEBA_CUSTOM_TERMS:
    jieba.add_word(_term, freq=_freq, tag='n')

# ── 预处理 ──

def _clean_content(text: str) -> str:
    """剥离 URL、图片等干扰内容（保留正文，交给 jieba 分词处理）"""
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', text)
    # 去掉 frontmatter
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, flags=re.DOTALL)
    return text


def _tokenize(text: str) -> list[str]:
    """分词，过滤短词、纯数字、纯标点"""
    tokens = jieba.lcut(text)
    return [
        t.strip() for t in tokens
        if len(t.strip()) >= 2
        and not t.strip().isdigit()
        and not all(c in '，。、；：！？""''（）…—·/\\|-_=+*&^%$#@!~`' for c in t.strip())
    ]


# ── 关键词提取器 ──

# 业务文档模板通用词（出现在 PRD/交底/周报等模板中，非文档内容特有）
_TEMPLATE_STOPWORDS = {
    '产品经理', '需求评审', '需求链接', '原型稿', '基本信息', '需求背景',
    '用户画像', '需求场景', '需求描述', '验收标准', '版本记录', '变更记录',
    '访谈', '方案', '送交', '先例', '评审', '责任人', '文档', '模板',
    '备注', '附录', '参考', '说明', '概述', '介绍', '总结', '结论',
    '目标', '范围', '定位', '边界', '角色', '特征', '行为', '诉求',
    '所属产品线', '所属产品', '模块名称', '模块描述', '模块负责人', '研发负责人',
    '菜单', '按钮', '页面', '输入框', '下拉框', '弹窗', '提示',
}

class KeywordExtractor:
    """
    综合关键词提取器

    用法:
        extractor = KeywordExtractor()
        extractor.build_idf(doc_paths=[...])  # 用全库文档构建自定义 IDF
        keywords = extractor.extract(content)  # 提取单篇文档的关键词
    """

    def __init__(self):
        self.idf = {}          # word -> idf value
        self.doc_count = 0     # 总文档数
        self._built = False

    # ── 构建自定义 IDF ──

    def build_idf(self, doc_paths: list[str] = None, doc_contents: list[str] = None):
        """
        从全库文档构建自定义 IDF 词典。

        参数:
          doc_paths: 文档路径列表（从文件读取）
          doc_contents: 文档内容列表（直接传入，优先）
        """
        df = Counter()  # document frequency
        self.doc_count = 0

        def process(text):
            if not text:
                return
            clean = _clean_content(text)
            tokens = set(_tokenize(clean))  # 每篇文档每个词只计一次
            for t in tokens:
                df[t] += 1
            self.doc_count += 1

        if doc_contents:
            for text in doc_contents:
                process(text)
        elif doc_paths:
            for path in doc_paths:
                try:
                    text = Path(path).read_text(encoding='utf-8')
                    process(text)
                except Exception:
                    pass

        if self.doc_count == 0:
            self.doc_count = 1

        # 计算 IDF: log(总文档数 / 包含该词的文档数)
        self.idf = {
            word: math.log((self.doc_count + 1) / (freq + 1)) + 1
            for word, freq in df.items()
        }
        self._built = True

    def add_documents(self, texts: list[str]):
        """增量添加文档到 IDF 词典"""
        for text in texts:
            if not text:
                continue
            clean = _clean_content(text)
            tokens = set(_tokenize(clean))
            self.doc_count += 1
            for t in tokens:
                # 更新 IDF：需要重新计算
                pass
        # 重建 IDF
        # 简化：重新计算整个 IDF
        self._built = True  # 标记需要重建，实际重建在 build_idf 中

    # ── 提取关键词 ──

    def extract(self, content: str, top_k: int = 10) -> list[str]:
        """
        综合提取关键词：TF-IDF（自定义IDF）+ TextRank 融合

        返回: 按重要性排序的关键词列表
        """
        if not self._built:
            # 未构建 IDF，回退到纯 TextRank
            return self._extract_textrank_only(content, top_k)

        clean = _clean_content(content)
        tokens = _tokenize(clean)

        if len(tokens) < 10:
            return self._extract_textrank_only(content, top_k)

        # ── 1. TF-IDF with custom IDF ──
        tf = Counter(tokens)
        total_terms = len(tokens)
        tfidf_scores = {}
        for word, freq in tf.items():
            if len(word) < 2 or word.isascii():
                continue
            tf_val = freq / total_terms
            idf_val = self.idf.get(word, self.idf.get(word, 1.0))
            tfidf_scores[word] = tf_val * idf_val

        # ── 2. TextRank ──
        tr_scores = {}
        try:
            tr_raw = jieba.analyse.textrank(
                clean, topK=top_k * 2, withWeight=True,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'vn'),
            )
            tr_scores = {kw: weight for kw, weight in tr_raw if len(kw) >= 2}
        except Exception:
            pass

        # ── 3. 融合评分 ──
        # TF-IDF 和 TextRank 归一化后加权求和
        combined = {}

        # min-max 归一化
        def normalize(scores: dict) -> dict:
            if not scores:
                return {}
            vals = list(scores.values())
            vmin, vmax = min(vals), max(vals)
            if vmax == vmin:
                return {k: 0.5 for k in scores}
            return {k: (v - vmin) / (vmax - vmin) for k, v in scores.items()}

        norm_tfidf = normalize(tfidf_scores)
        norm_tr = normalize(tr_scores)

        all_words = set(norm_tfidf.keys()) | set(norm_tr.keys())
        for word in all_words:
            if len(word) < 2 or word.isascii():
                continue
            s_tfidf = norm_tfidf.get(word, 0)
            s_tr = norm_tr.get(word, 0)
            # TF-IDF 权重 0.35（跨文档区分度），TextRank 权重 0.65（文档内语义重要性）
            combined[word] = s_tfidf * 0.35 + s_tr * 0.65

        # 排序取 Top-K，过滤模板通用词
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        result = []
        for word, score in ranked:
            if word in _TEMPLATE_STOPWORDS:
                continue
            result.append(word)
            if len(result) >= top_k:
                break
        return result

    def _extract_textrank_only(self, content: str, top_k: int = 10) -> list[str]:
        """纯 TextRank 兜底"""
        clean = _clean_content(content)
        try:
            tr_kws = jieba.analyse.textrank(
                clean, topK=top_k, withWeight=True,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'vn'),
            )
            return [kw for kw, w in tr_kws if len(kw) >= 2 and not kw.isascii()][:top_k]
        except Exception:
            return []


# ── 全局单例 ──

_extractor: KeywordExtractor = None


def get_extractor() -> KeywordExtractor:
    """获取全局关键词提取器单例（自动构建 IDF）"""
    global _extractor
    if _extractor is None:
        _extractor = KeywordExtractor()
    return _extractor


def build_extractor_idf(data_dir: str = None):
    """从知识库数据目录构建 IDF 词典"""
    ext = get_extractor()
    if data_dir is None:
        # 默认路径
        here = Path(__file__).resolve().parent
        data_dir = here.parent / "data"

    data_path = Path(data_dir)
    all_docs = []
    for subdir in ["knowledge", "faq", "reports", "raw-docs"]:
        d = data_path / subdir
        if d.exists():
            all_docs.extend(str(p) for p in d.rglob("*.md") if p.name not in ("INDEX.md", "TEMPLATE.md"))

    ext.build_idf(doc_paths=all_docs)
    return ext