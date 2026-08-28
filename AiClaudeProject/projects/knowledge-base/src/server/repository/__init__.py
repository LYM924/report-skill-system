"""Repository 数据访问层"""
from .base import KnowledgeRepository, Document, FAQ, KeywordEntry, ModuleInfo, Report
from .file_repo import FileRepository
from .db_repo import DBRepository

__all__ = [
    "KnowledgeRepository", "Document", "FAQ", "KeywordEntry", "ModuleInfo", "Report",
    "FileRepository", "DBRepository",
]