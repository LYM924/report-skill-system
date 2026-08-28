"""部门模型"""
from typing import Optional
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    dir_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)

    modules: Mapped[list["Module"]] = relationship(back_populates="department")


class ProductLine(Base):
    __tablename__ = "product_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="product_line")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    product_line: Mapped[Optional[ProductLine]] = relationship(back_populates="products")
    modules: Mapped[list["Module"]] = relationship(back_populates="product")


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dev_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    module_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    appendix: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    business_domain: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dir_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    department: Mapped[Optional[Department]] = relationship(back_populates="modules")
    product: Mapped[Optional[Product]] = relationship(back_populates="modules")


class ModuleMenu(Base):
    __tablename__ = "module_menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    level1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    level2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    level3: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)