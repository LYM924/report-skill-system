# 搜索系统健壮性分析

> 日期：2026-08-23

## 一、FAQ 数据变动 → 搜索生效链路

```
FAQ 增删改 → 缓存失效 → 引擎重建 → 搜索生效
```

| 操作 | 触发缓存失效 | 是否自动 | 生效延迟 |
|------|:----------:|:---:|:---:|
| Web 页面新增 FAQ | ✅ `/api/faq/save` → `rebuild_engine()` | 自动 | 即时 |
| Web 页面删除 FAQ | ✅ `/api/faq/delete` → `rebuild_engine()` | 自动 | 即时 |
| 手动 `/api/rebuild` | ✅ 强制清除全部缓存 | 手动 | 即时 |
| 服务重启 | ✅ `load_cache()` 检测文件数/路径哈希/cache_version | 自动 | 启动时 |
| 迁移脚本导入 | ⚠️ 更新 cache_version 但不触发 rebuild | 半自动 | 需重启或手动 rebuild |
| 直接编辑 FAQ 文件 | ⚠️ `_dir_hash()` 检测内容摘要 | 自动 | 下次请求时 |

## 二、当前仍存在的风险点

### 风险 1：迁移脚本导入后不自动重建 ⚠️

`migrate_faqs_to_db.py` 更新了 `cache_version`，但运行中的服务不会自动感知。

**影响**：批量导入新 FAQ 后，搜索仍返回旧结果，直到手动重启或 rebuild。

**修复**：迁移脚本末尾增加 `curl /api/rebuild` 调用。

### 风险 2：同分 FAQ 排序依赖 faq_docs 顺序 ⚠️

当多个 FAQ 都命中 cap（50 分），排名取决于 `faq_docs` 列表中的顺序（按 dept 字母序：digital-support → e-archive → fin-tech → immunization）。

**影响**：同样相关度下，数字化支撑组 FAQ 排在数智财务组前面。

**修复**：`rank()` 已增加 match_count 同分排序，但 cap 50 仍可能导致同分。可考虑移除 cap 或进一步提升。

### 风险 3：jieba 词典未覆盖新业务术语 ⚠️

新 FAQ 引入的新业务术语（如新模块名、新功能名）不在 jieba 自定义词典中，会被错误切分。

**影响**：新 FAQ 的关键词无法被正确匹配。

**修复**：在 `faq_generate.py` 或迁移脚本中，自动从 FAQ 的 keywords 字段提取新术语加入 jieba 词典。

### 风险 4：直接编辑文件不触发 DB 更新 ⚠️

直接编辑 FAQ markdown 文件不会更新 DB，`get_all_faqs()` 从 DB 读取时看不到变更。

**影响**：文件编辑后搜索不生效，直到迁移脚本重新导入。

**修复**：建议统一通过 Web 页面编辑 FAQ；或增加文件监控自动触发迁移。

### 风险 5：旧缓存文件残留 🔴

`rebuild_engine()` 清除 `runtime/cache/*`，但如果缓存目录不存在或权限问题，清除失败不会报错。

**影响**：看似重建了但实际用的是旧缓存。

**已修复**：`rebuild_engine()` 在清除后调用 `load_all()` 构建新数据，不依赖缓存文件。

## 三、已修复的问题（不会复发）

| 问题 | 修复方式 | 是否根治 |
|------|---------|:---:|
| FAQ keywords 为空 | `_parse_faq` 手动解析非 JSON 格式 | ✅ |
| DB 查询失败回退文件 | 修复 `get_all_faqs` SQL | ✅ |
| diversity 误杀 FAQ | module 字段 + dept 兜底 | ✅ |
| keyword_index 占位 | 无路径结果降权 | ✅ |
| AI 总结引用错误文档 | 改用 RAG prompt | ✅ |
| 同分 FAQ 排序随机 | rank 增加 match_count 排序 | ✅ |
| jieba 分词错误 | 扩充自定义词典 | ✅ 但新术语需持续维护 |

## 四、建议

### 立即执行（防止后续问题）

1. **迁移脚本自动 rebuild**：`migrate_faqs_to_db.py` 末尾增加 `curl http://localhost:8765/api/rebuild`
2. **jieba 词典自动维护**：`faq_generate.py` 从 FAQ keywords 提取新术语加入词典

### 短期优化

3. **移除 score cap**：当前 cap 50 导致高相关度 FAQ 无法区分，建议改为权重衰减
4. **增加 FAQ 编辑后自动重建**：`/api/faq/save` 已调用 rebuild，确认正常运行

### 长期规划

5. **文件监控**：watchdog 监控 `data/faq/` 目录变更，自动触发迁移+重建
6. **缓存预热**：服务启动时预加载，避免首次请求慢