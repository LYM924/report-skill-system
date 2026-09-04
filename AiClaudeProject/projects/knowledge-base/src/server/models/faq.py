"""FAQ 模型"""
from typing import Optional
from sqlalchemy import String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


class FAQ(Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    faq_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    faq_title: Mapped[str] = mapped_column(String(500), nullable=False)
    faq_question: Mapped[str] = mapped_column(Text, nullable=False)
    faq_answer: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dept: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_module: Mapped[str] = mapped_column(String(100), default="")
    module: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    scene: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[int] = mapped_column(Integer, default=0)
    sort_num: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    source_file_name: Mapped[str] = mapped_column(String(200), default="")
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    version_from: Mapped[str] = mapped_column(String(50), default="")
    related: Mapped[str] = mapped_column(Text, default="[]")
    tickets: Mapped[str] = mapped_column(Text, default="[]")
    create_user: Mapped[str] = mapped_column(String(100), default="")
    update_user: Mapped[str] = mapped_column(String(100), default="")
    create_time: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())
    update_time: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


# 注意：旧 keywords 表已删除（见 config/migrations 与 git 7c5d812），
# 关键词现由 keywords_v2 + keyword_mappings 管理（repository/db_repo.py 直接 SQL）。
# SQLAlchemy 模型仅作结构参考，Schema 演进统一走 config/migrations/。

class Synonym(Base):
    __tablename__ = "synonyms"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(200), nullable=False)
    synonym: Mapped[str] = mapped_column(String(200), nullable=False)


class SearchCounter(Base):
    __tablename__ = "search_counter"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    result_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    result_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())


class LearningCandidate(Base):
    """学习候选池：AI 回答 / 用户反馈中有价值的知识，经审核后沉淀为 FAQ"""
    __tablename__ = "learning_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="ai_answer")  # ai_answer | user_feedback | manual
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    dept: Mapped[str] = mapped_column(String(100), default="")
    module: Mapped[str] = mapped_column(String(200), default="")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[int] = mapped_column(Integer, default=0)  # 0待审核/1已通过/2已拒绝/3已过期
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str] = mapped_column(String(100), default="")
    reviewed_at: Mapped[str] = mapped_column(String(30), default="")
    feedback_id: Mapped[int] = mapped_column(Integer, default=0)
    session_id: Mapped[str] = mapped_column(String(50), default="")
    faq_code: Mapped[str] = mapped_column(String(50), default="")
    created_by: Mapped[str] = mapped_column(String(100), default="")
    create_time: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())
    update_time: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    week: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="周报")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dept_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat())