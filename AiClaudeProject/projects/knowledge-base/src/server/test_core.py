#!/usr/bin/env python3
"""
核心功能测试 — 覆盖搜索、关键词提取、路径映射、API 端点
"""

import sys, os, json, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_DIR = HERE.parent.parent

# ============================================================
# 1. 搜索引擎测试
# ============================================================
class TestSearchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from search_engine import SearchEngine
        cls.engine = SearchEngine()
        cls.engine.load_all()

    def test_bm25_index_loaded(self):
        """BM25 索引已加载"""
        self.assertIsNotNone(self.engine.bm25)
        self.assertGreater(self.engine.bm25.N, 0, "BM25 索引为空")

    def test_search_returns_results(self):
        """搜索返回结果"""
        r = self.engine.search("参考价合规", top=5)
        results = r.get("results", [])
        self.assertGreater(len(results), 0, "搜索无结果")

    def test_search_document_top1(self):
        """文档搜索 Top1 命中"""
        r = self.engine.search("安徽网超参考价管控", top=5)
        results = r.get("results", [])
        self.assertGreater(len(results), 0)
        # 检查 Top1 是否与竞价/参考价相关
        title = results[0].get("title", "")
        path = results[0].get("path", "")
        self.assertTrue(
            "竞价" in title or "参考价" in title or "参考价" in path or "竞价" in path,
            f"Top1 不相关: {title}"
        )

    def test_search_source_diversity(self):
        """搜索结果来源多样性"""
        r = self.engine.search("报销单", top=10)
        sources = set(rr.get("source", "?") for rr in r.get("results", []))
        self.assertGreaterEqual(len(sources), 2, f"来源种类不足: {sources}")

    def test_search_faq_match(self):
        """FAQ 搜索匹配"""
        r = self.engine.search("报销单选不到申请单", top=5)
        results = r.get("results", [])
        titles = " ".join(rr.get("title", "") for rr in results)
        self.assertIn("申请单", titles)

    def test_rrf_fusion(self):
        """RRF 融合正常工作"""
        r = self.engine.search("参考价", top=5)
        results = r.get("results", [])
        self.assertGreater(len(results), 0)
        # 至少有一个结果有 rrf_score
        self.assertTrue(any(rr.get("rrf_score") is not None for rr in results))

    def test_search_no_crash_on_empty(self):
        """空查询不崩溃"""
        r = self.engine.search("", top=5)
        self.assertIsNotNone(r)

    def test_search_no_crash_on_special_chars(self):
        """特殊字符查询不崩溃"""
        r = self.engine.search("!!!???###", top=5)
        self.assertIsNotNone(r)


# ============================================================
# 2. 关键词提取测试
# ============================================================
class TestKeywordExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from keyword_extractor import KeywordExtractor, build_extractor_idf
        cls.extractor = build_extractor_idf(str(PROJECT_DIR / "data"))

    def test_idf_built(self):
        """IDF 词典已构建"""
        self.assertGreater(len(self.extractor.idf), 1000, "IDF 词典太小")
        self.assertGreater(self.extractor.doc_count, 100, "语料库文档太少")

    def test_extract_keywords(self):
        """提取关键词"""
        content = "参考价合规是电子卖场竞价交易的核心要求，电商参考价作为基准价"
        kws = self.extractor.extract(content, top_k=5)
        self.assertGreater(len(kws), 0, "未提取到关键词")

    def test_extract_no_url_pollution(self):
        """无 URL 片段污染"""
        content = "参考价合规 ![image](https://example.com/img.png) 竞价交易"
        kws = self.extractor.extract(content, top_k=10)
        self.assertNotIn("png", kws, "URL 片段污染")
        self.assertNotIn("https", kws, "URL 片段污染")

    def test_extract_no_ascii_words(self):
        """无纯英文词"""
        content = "参考价合规是电子卖场竞价交易的核心要求"
        kws = self.extractor.extract(content, top_k=10)
        for kw in kws:
            self.assertFalse(kw.isascii(), f"纯英文词: {kw}")

    def test_extract_business_terms(self):
        """业务术语被提取"""
        content = "参考价合规是竞价交易的核心，电商参考价作为基准价，反拍商品必须合规"
        kws = self.extractor.extract(content, top_k=10)
        business = {"参考价", "合规", "竞价", "电商", "反拍", "基准价"}
        found = [kw for kw in kws if kw in business]
        self.assertGreaterEqual(len(found), 3, f"业务术语不足: {kws}")


# ============================================================
# 3. 路径映射测试
# ============================================================
class TestDeptMapping(unittest.TestCase):
    def setUp(self):
        from repository.dept_mapping import get_dept_path, get_submodule_path
        self.get_dept_path = get_dept_path
        self.get_submodule_path = get_submodule_path

    def test_known_dept(self):
        """已知部门映射"""
        self.assertEqual(self.get_dept_path("业务研发部"), "business-dev")
        self.assertEqual(self.get_dept_path("数智财务组"), "fin-tech")
        self.assertEqual(self.get_dept_path("免疫规划组"), "immunization")

    def test_unknown_dept_pinyin_fallback(self):
        """未知部门拼音兜底"""
        result = self.get_dept_path("新测试部门")
        self.assertNotIn("测试", result.split("-")[0] if "-" in result else result)
        self.assertTrue(result.isascii(), f"非英文路径: {result}")

    def test_known_submodule(self):
        """已知子模块映射"""
        self.assertEqual(self.get_submodule_path("竞价"), "jing-jia")
        self.assertEqual(self.get_submodule_path("浙里报"), "zhelibao")

    def test_submodule_pinyin_fallback(self):
        """未知子模块拼音兜底"""
        result = self.get_submodule_path("新模块测试")
        self.assertTrue(result.isascii(), f"非英文路径: {result}")


# ============================================================
# 4. 数据库测试
# ============================================================
class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.db = sqlite3.connect(str(PROJECT_DIR / "runtime" / "knowledge.db"))

    def test_faqs_table_has_data(self):
        """FAQs 表有数据"""
        cnt = self.db.execute("SELECT COUNT(*) FROM faqs WHERE is_deleted=0").fetchone()[0]
        self.assertGreater(cnt, 100, f"FAQs 数据太少: {cnt}")

    def test_modules_table_has_data(self):
        """Modules 表有数据"""
        cnt = self.db.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        self.assertGreater(cnt, 100, f"Modules 数据太少: {cnt}")

    def test_keywords_table_has_data(self):
        """Keywords 表有数据"""
        cnt = self.db.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        self.assertGreater(cnt, 500, f"Keywords 数据太少: {cnt}")

    def test_departments_have_dir_name(self):
        """部门表有 dir_name"""
        cnt = self.db.execute(
            "SELECT COUNT(*) FROM departments WHERE dir_name IS NOT NULL AND dir_name != ''"
        ).fetchone()[0]
        self.assertGreaterEqual(cnt, 20, f"部门 dir_name 不足: {cnt}")

    def test_module_menus_has_data(self):
        """module_menus 表有数据"""
        cnt = self.db.execute("SELECT COUNT(*) FROM module_menus").fetchone()[0]
        self.assertGreater(cnt, 0, "module_menus 为空")

    def test_faq_dir_names_are_english(self):
        """FAQ 目录路径为英文（文件名可以为中文标题）"""
        rows = self.db.execute(
            "SELECT file_path FROM faqs WHERE is_deleted=0"
        ).fetchall()
        for (path,) in rows:
            # 只检查目录部分（去掉文件名）
            dir_part = "/".join(path.split("/")[:-1]) if "/" in path else path
            # 目录不应含中文
            self.assertFalse(
                any('一' <= c <= '鿿' for c in dir_part),
                f"FAQ 目录含中文: {dir_part}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)