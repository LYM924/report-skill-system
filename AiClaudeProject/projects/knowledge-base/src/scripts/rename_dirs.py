#!/usr/bin/env python3
"""批量重命名中文目录为英文"""
import os, sys, shutil
from pathlib import Path

BASE = Path("/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/projects/knowledge-base")
sys.path.insert(0, str(BASE / "src" / "server" / "repository"))
from dept_mapping import DEPT_TO_PATH, SUBMODULE_TO_PATH, OTHER_DIR_MAP, DEPRECATED_DIRS

renames = []
for root, dirs, files in os.walk(str(BASE / "data")):
    root_path = Path(root)
    for d in dirs:
        if d in DEPRECATED_DIRS:
            continue
        if d in DEPT_TO_PATH:
            old = root_path / d
            new = root_path / DEPT_TO_PATH[d]
            renames.append((old, new))
        elif d in SUBMODULE_TO_PATH:
            old = root_path / d
            new = root_path / SUBMODULE_TO_PATH[d]
            renames.append((old, new))
        elif d in OTHER_DIR_MAP and OTHER_DIR_MAP[d]:
            old = root_path / d
            new = root_path / OTHER_DIR_MAP[d]
            renames.append((old, new))

renames.sort(key=lambda x: -len(str(x[0]).split("/")))

for old, new in renames:
    if old.exists() and not new.exists():
        old.rename(new)
        print(f"  {old.name} -> {new.name}")

for d in DEPRECATED_DIRS:
    for p in BASE.rglob(d):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            print(f"  removed: {p}")

print(f"\nDone: {len(renames)} dirs renamed")