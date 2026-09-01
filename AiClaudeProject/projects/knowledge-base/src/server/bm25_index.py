#!/usr/bin/env python3
"""BM25 文档检索引擎 - 倒排索引 + BM25 排序算法"""
import pickle
import math
import logging
from collections import defaultdict

import jieba
jieba.setLogLevel(logging.WARNING)


class BM25Index:
    """BM25 文档检索引擎。

    用法:
        bm25 = BM25Index()
        bm25.build([{'path': '...', 'content': '...', 'dept': '...', 'domain': '...'}, ...])
        results = bm25.search(['关键词1', '关键词2'], k=10)
        bm25.save('bm25_index.pkl')
        bm25.load('bm25_index.pkl')
    """

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.documents = []       # [(doc_id, path, dept, domain)]
        self.inverted_index = defaultdict(dict)  # term -> {doc_id: term_frequency}
        self.doc_lengths = {}     # doc_id -> total_terms
        self.avg_dl = 0
        self.N = 0

    def build(self, kb_docs):
        """从 KB 文档列表构建倒排索引。

        kb_docs: list of dict, each with keys: path, content, dept, domain
        """
        self.documents = []
        self.inverted_index = defaultdict(dict)
        self.doc_lengths = {}

        for i, doc in enumerate(kb_docs):
            doc_id = i
            self.documents.append((
                doc_id,
                doc.get('path', ''),
                doc.get('dept', ''),
                doc.get('domain', ''),
            ))

            text = doc.get('content', '')
            tokens = [t.strip() for t in jieba.cut(text) if len(t.strip()) >= 1]
            self.doc_lengths[doc_id] = len(tokens)

            term_freq = defaultdict(int)
            for token in tokens:
                term_freq[token] += 1

            for term, freq in term_freq.items():
                self.inverted_index[term][doc_id] = freq

        self.N = len(self.documents)
        total_len = sum(self.doc_lengths.values())
        self.avg_dl = total_len / self.N if self.N > 0 else 1

    def add_document(self, doc):
        """增量添加单个文档到索引（不重建整个索引）

        doc: dict with keys: path, content, dept, domain
        """
        doc_id = self.N  # 新文档 ID
        self.documents.append((
            doc_id,
            doc.get('path', ''),
            doc.get('dept', ''),
            doc.get('domain', ''),
        ))

        text = doc.get('content', '')
        tokens = [t.strip() for t in jieba.cut(text) if len(t.strip()) >= 1]
        self.doc_lengths[doc_id] = len(tokens)

        term_freq = defaultdict(int)
        for token in tokens:
            term_freq[token] += 1

        for term, freq in term_freq.items():
            self.inverted_index[term][doc_id] = freq

        self.N = len(self.documents)
        total_len = sum(self.doc_lengths.values())
        self.avg_dl = total_len / self.N if self.N > 0 else 1

    def remove_by_path_prefix(self, prefix: str):
        """删除路径前缀匹配的所有文档索引条目（增量更新用）

        删除后自动重算 N/avg_dl，IDF 在下次搜索时按新 N 重算。
        """
        to_remove = [i for i, (_, path, _, _) in enumerate(self.documents) if path.startswith(prefix)]
        if not to_remove:
            return
        remove_ids = set(to_remove)
        # 清理 inverted_index 中的引用
        for term in list(self.inverted_index.keys()):
            for doc_id in remove_ids:
                self.inverted_index[term].pop(doc_id, None)
            if not self.inverted_index[term]:
                del self.inverted_index[term]
        # 清理 doc_lengths
        for doc_id in remove_ids:
            self.doc_lengths.pop(doc_id, None)
        # 重建 documents 列表（ID 重新映射）
        old_docs = self.documents
        self.documents = []
        id_map = {}  # 旧 ID → 新 ID
        new_id = 0
        for old_id, (_, path, dept, domain) in enumerate(old_docs):
            if old_id not in remove_ids:
                id_map[old_id] = new_id
                self.documents.append((new_id, path, dept, domain))
                new_id += 1
        # 重映射 inverted_index 和 doc_lengths
        new_inverted = defaultdict(dict)
        for term, postings in self.inverted_index.items():
            for old_id, freq in postings.items():
                if old_id in id_map:
                    new_inverted[term][id_map[old_id]] = freq
        self.inverted_index = new_inverted
        new_lengths = {}
        for old_id, length in self.doc_lengths.items():
            if old_id in id_map:
                new_lengths[id_map[old_id]] = length
        self.doc_lengths = new_lengths
        # 重算统计量
        self.N = len(self.documents)
        total_len = sum(self.doc_lengths.values())
        self.avg_dl = total_len / self.N if self.N > 0 else 1

    def _idf(self, term):
        """计算 IDF（逆文档频率），使用 BM25 标准公式"""
        df = len(self.inverted_index.get(term, {}))
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1)

    def search(self, query_terms, k=10):
        """BM25 搜索，返回 Top-K 文档的 (path, score) 列表。

        query_terms: list of str, 已经过分词和扩展的查询词列表
        """
        scores = defaultdict(float)

        for term in query_terms:
            if term not in self.inverted_index:
                continue
            idf = self._idf(term)
            for doc_id, tf in self.inverted_index[term].items():
                doc_len = self.doc_lengths.get(doc_id, 1)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_dl)
                scores[doc_id] += idf * numerator / denominator

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(self.documents[doc_id][1], score) for doc_id, score in ranked]

    def save(self, path):
        """序列化到磁盘（pickle 格式）"""
        data = {
            'k1': self.k1, 'b': self.b,
            'documents': self.documents,
            'inverted_index': dict(self.inverted_index),
            'doc_lengths': self.doc_lengths,
            'avg_dl': self.avg_dl, 'N': self.N,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)

    def load(self, path):
        """从磁盘加载"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.k1 = data['k1']
        self.b = data['b']
        self.documents = data['documents']
        self.inverted_index = defaultdict(dict, data['inverted_index'])
        self.doc_lengths = data['doc_lengths']
        self.avg_dl = data['avg_dl']
        self.N = data['N']
        return True