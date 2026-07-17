#!/usr/bin/env python3
"""向量检索引擎 - sentence-transformers + FAISS 语义检索"""
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss


class VectorIndex:
    """向量语义检索引擎。

    用法:
        vi = VectorIndex()
        vi.build([{'path': '...', 'heading': '...', 'content': '...'}, ...])
        results = vi.search('查询文本', k=10)
        vi.save('vector_index.faiss', 'vector_meta.pkl')
        vi.load('vector_index.faiss', 'vector_meta.pkl')
    """

    def __init__(self, model_name='paraphrase-multilingual-MiniLM-L12-v2'):
        self.model = SentenceTransformer(model_name)
        self.index = None       # FAISS IndexFlatIP
        self.sections = []      # [{path, heading, content}]
        self.dim = 384          # MiniLM 输出维度

    def build(self, kb_segments):
        """对 KB 段落列表生成 embedding 并建 FAISS 索引。

        kb_segments: list of dict, each with keys: path, heading, content
        """
        embeddings = []
        self.sections = []

        for seg in kb_segments:
            text = seg.get('content', '')
            if len(text) < 50:
                continue
            # 取前 512 字符做 embedding（平衡速度和语义覆盖）
            emb = self.model.encode(text[:512], convert_to_numpy=True)
            embeddings.append(emb)
            self.sections.append({
                'path': seg.get('path', ''),
                'heading': seg.get('heading', ''),
                'content': text[:1500],
            })

        if not embeddings:
            return

        emb_matrix = np.array(embeddings).astype('float32')
        # L2 归一化，使内积等价于余弦相似度
        faiss.normalize_L2(emb_matrix)
        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(emb_matrix)

    def encode(self, text):
        """编码单条文本为归一化向量"""
        emb = self.model.encode(text[:512], convert_to_numpy=True)
        emb = emb.astype('float32').reshape(1, -1)
        faiss.normalize_L2(emb)
        return emb

    def search(self, query, k=10):
        """向量检索 Top-K 段落。返回 [{path, heading, content, score}, ...]"""
        if self.index is None:
            return []

        query_emb = self.encode(query)
        scores, indices = self.index.search(query_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.sections):
                continue
            sec = self.sections[idx].copy()
            sec['score'] = float(score)
            results.append(sec)

        return results

    def save(self, index_path, meta_path):
        """保存 FAISS 索引和元数据到磁盘"""
        if self.index is not None:
            faiss.write_index(self.index, str(index_path))
        with open(meta_path, 'wb') as f:
            pickle.dump({'sections': self.sections, 'dim': self.dim}, f)

    def load(self, index_path, meta_path):
        """从磁盘加载 FAISS 索引和元数据"""
        import os
        if os.path.exists(str(index_path)):
            self.index = faiss.read_index(str(index_path))
        if os.path.exists(str(meta_path)):
            with open(meta_path, 'rb') as f:
                data = pickle.load(f)
            self.sections = data['sections']
            self.dim = data.get('dim', 384)
        return True