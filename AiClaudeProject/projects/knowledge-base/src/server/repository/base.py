"""
Repository 数据访问层 - 抽象接口与数据模型

定义知识库数据访问的统一接口与数据结构。当前唯一实现: DBRepository
（PostgreSQL 优先，SQLite 自动回退；文档内容主体仍为文件系统 data/）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """知识文档"""
    path: str
    title: str
    content: str
    dept: str = ""
    module: str = ""
    product: str = ""
    product_line: str = ""
    date: str = ""
    keywords: list = field(default_factory=list)
    appendix: str = ""


@dataclass
class FAQ:
    """FAQ 文档"""
    faq_code: str = ""          # FAQ-DZ-DZ-002，语义 ID
    faq_title: str = ""         # FAQ 标题
    faq_question: str = ""      # 问题，用于检索/向量化
    faq_answer: str = ""        # 答案完整 Markdown
    content: str = ""           # 完整 MD（兼容旧数据）
    path: str = ""              # 文件路径
    tags: list = field(default_factory=list)       # JSON 数组 ["银行回单","同步"]
    dept: str = ""
    dept_id: int = 0
    sub_module: str = ""
    module: str = ""
    module_id: int = 0
    scene: str = ""
    status: int = 0             # 0草稿 1已发布 2归档 3禁用
    category_id: int = 0
    sort_num: int = 0
    view_count: int = 0
    source_file_name: str = ""
    version_from: str = ""
    related: list = field(default_factory=list)
    tickets: list = field(default_factory=list)
    create_user: str = ""
    update_user: str = ""
    create_time: str = ""
    update_time: str = ""
    is_deleted: int = 0

    # 向后兼容属性
    @property
    def id(self): return self.faq_code
    @property
    def title(self): return self.faq_title
    @property
    def keywords(self): return self.tags


@dataclass
class KeywordEntry:
    """关键词映射条目"""
    keyword: str
    module: str
    dept: str = ""
    domain: str = ""
    kb_path: str = ""
    note: str = ""


@dataclass
class ModuleInfo:
    """模块信息"""
    name: str
    path: str
    dept: str = ""
    domain: str = ""
    product: str = ""
    keywords: list = field(default_factory=list)
    menus: list = field(default_factory=list)


@dataclass
class Report:
    """报表文档"""
    path: str
    title: str
    content: str = ""


class KnowledgeRepository(ABC):
    """知识库数据访问抽象接口"""

    @abstractmethod
    def get_all_documents(self) -> list[Document]:
        """获取所有知识文档"""
        ...

    @abstractmethod
    def get_all_faqs(self) -> list[FAQ]:
        """获取所有 FAQ 文档"""
        ...

    @abstractmethod
    def get_all_keywords_v2(self) -> dict[str, list[dict]]:
        """获取所有关键词映射（ID方案）: {keyword: [{mapping_id, keyword_id, module, module_id, dept, dept_id, ...}]}"""
        ...

    @abstractmethod
    def get_all_modules(self) -> dict[str, ModuleInfo]:
        """获取所有模块信息: {module_name: ModuleInfo}"""
        ...

    @abstractmethod
    def get_all_reports(self) -> list[Report]:
        """获取所有报表文档"""
        ...

    @abstractmethod
    def save_faq(self, faq: FAQ) -> str:
        """保存 FAQ，返回文件路径"""
        ...

    @abstractmethod
    def delete_faq(self, path: str) -> bool:
        """删除 FAQ，返回是否成功"""
        ...

    @abstractmethod
    def save_feedback(self, query: str, result_id: str, result_path: str, feedback_type: str) -> None:
        """记录搜索反馈"""
        ...

    @abstractmethod
    def get_raw_docs(self) -> list[Document]:
        """获取原始产品文档"""
        ...

    @abstractmethod
    def get_synonyms(self) -> dict[str, list[str]]:
        """获取同义词映射"""
        ...