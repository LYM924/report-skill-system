"""路径安全校验：所有用户提供的相对路径必须解析到数据目录内，防止路径穿越"""
from pathlib import Path
from config import settings


def safe_data_path(rel_path: str) -> Path:
    """将用户提供的相对路径解析到 DATA_DIR 内；越界返回 None

    - 拒绝绝对路径、空路径
    - 路径基于 PROJECT_DIR 解析（兼容 "data/..." 前缀写法），resolve() 展开 .. 后
      校验必须落在 DATA_DIR 内
    """
    if not rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
        return None
    base = settings.PROJECT_DIR.resolve()
    data_dir = settings.DATA_DIR.resolve()
    p = (base / rel_path).resolve()
    if p == data_dir or not str(p).startswith(str(data_dir) + "/"):
        return None
    return p
