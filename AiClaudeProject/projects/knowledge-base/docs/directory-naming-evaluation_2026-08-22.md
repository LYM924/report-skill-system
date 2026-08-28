# 知识库项目结构评估：文件夹命名与业界对比

> 评估日期：2026-08-22
> 对标参考：Docusaurus、Outline、Wiki.js、BookStack、Google Style Guide、2025 项目结构最佳实践

---

## 一、当前目录结构总览

```
knowledge-base/
├── config/                          ✅ 英文
│   ├── 关键词索引.md                 ❌ 中文文件名
│   ├── synonyms.json                ✅
│   └── schema.sql                   ✅
├── data/                            ✅ 英文
│   ├── faq/                         ✅ 英文
│   │   ├── FAQ知识库/               ❌ 中文 + 冗余（与 faq/ 重复）
│   │   ├── 数智财务组/              ❌ 中文目录
│   │   │   ├── 浙里报/              ❌ 中文目录
│   │   │   │   └── 预算指标同步失败.md  ❌ 中文文件名
│   │   │   └── 徽报账/              ❌ 中文目录
│   │   ├── 免疫规划组/              ❌ 中文目录
│   │   ├── 电子档案组/              ❌ 中文目录
│   │   └── 数字化支撑组/            ❌ 中文目录
│   ├── knowledge/                   ✅ 英文
│   │   ├── 数智财务组/              ❌ 中文目录
│   │   │   ├── 浙里报/              ❌ 中文目录
│   │   │   │   └── 浙里报_20260101_影响_需求实现.md  ❌ 中文文件名
│   │   │   ├── 百搭/                ❌ 中文目录
│   │   │   ├── 其他资金/            ❌ 中文目录
│   │   │   └── ...
│   │   ├── 免疫规划组/              ❌ 中文目录
│   │   ├── 电子档案组/              ❌ 中文目录
│   │   └── 数字化支撑组/            ❌ 中文目录
│   ├── modules/                     ✅ 英文
│   │   ├── 数智财务组/              ❌ 中文目录
│   │   ├── 免疫规划组/              ❌ 中文目录
│   │   └── ...
│   ├── raw-docs/                    ✅ 英文
│   │   ├── 数智财务组/              ❌ 中文目录
│   │   │   └── 2026年05月发布说明.md  ❌ 中文文件名
│   │   └── ...
│   └── reports/                     ✅ 英文
│       ├── 周报/                    ❌ 中文目录
│       └── 月报/                    ❌ 中文目录
├── src/                             ✅ 英文
│   ├── scripts/                     ✅ 英文
│   ├── server/                      ✅ 英文
│   │   └── repository/              ✅ 英文
│   └── web/                         ✅ 英文
│       └── src/components/          ✅ 英文
├── runtime/                         ✅ 英文
├── docs/                            ✅ 英文
│   └── 优化记录_2026-08-21.md       ❌ 中文文件名
└── README.md                        ✅ 英文
```

**统计**：46 个中文目录 + 199 个中文文件，占项目总目录/文件的 50%+

---

## 二、业界标准对比

### 2.1 命名规范对比

| 规范 | 业界标准 | 当前项目 | 评分 |
|------|---------|---------|:---:|
| **大小写** | 统一小写（kebab-case 或 snake_case） | 中英文混用，中文无大小写概念 | ❌ |
| **分隔符** | 连字符 `-` 或下划线 `_` | 中文无分隔符，英文用下划线 | ⚠️ |
| **特殊字符** | 禁止空格、`()`、`@`、中文 | 大量中文、部分文件名含 `+`、`&`、`【】` | ❌ |
| **可读性** | 英文单词，语义明确 | 中文对国人可读，但非ASCII在终端/git/CI中易乱码 | ⚠️ |
| **排序性** | 字母排序可预测 | 中文按 Unicode 排序，不可预测 | ❌ |
| **跨平台** | 纯 ASCII，Windows/Mac/Linux 通用 | 中文在 Windows 终端/git bash 可能乱码 | ❌ |
| **URL 友好** | 直接作为 URL 路径 | 中文需 URL 编码（`%E6%B5%99%E9%87%8C%E6%8A%A5`） | ❌ |

### 2.2 目录组织对比

| 维度 | Docusaurus | Outline | Wiki.js | 当前项目 | 评分 |
|------|-----------|---------|---------|---------|:---:|
| **代码/数据分离** | src/ + docs/ | app/ + server/ | client/ + server/ | src/ + data/ + config/ | ✅ |
| **内容按域组织** | docs/guides/, docs/api/ | — | — | data/faq/{部门}/, data/knowledge/{部门}/ | ✅ |
| **命名语言** | 全英文 | 全英文 | 全英文 | 中英文混用 | ❌ |
| **嵌套深度** | ≤3 层 | ≤3 层 | ≤3 层 | 4-5 层（data/faq/{部门}/{子模块}/FAQ-xxx.md） | ⚠️ |
| **版本化** | docs/v1/, docs/v2/ | — | — | 文件名含日期（20260101），无版本目录 | ⚠️ |
| **静态资源** | static/ | public/ | public/ | 无独立 static 目录 | ⚠️ |

### 2.3 业界项目命名示例

| 项目 | 目录命名风格 | 示例 |
|------|------------|------|
| **Docusaurus** | 全英文 kebab-case | `docs/`, `getting-started/`, `advanced-guides/` |
| **Outline** | 全英文 PascalCase 目录 | `app/`, `server/`, `shared/`, `plugins/` |
| **Wiki.js** | 全英文小写 | `client/`, `server/`, `modules/`, `dev/` |
| **Kubernetes** | 全英文小写 | `pkg/`, `staging/`, `api/`, `cmd/` |
| **VS Code** | 全英文小写 | `src/vs/`, `extensions/`, `build/` |
| **React** | 全英文小写 | `packages/react/`, `packages/react-dom/` |

**无一例外：所有主流开源项目均使用全英文 ASCII 命名。**

---

## 三、中文命名的问题清单

### 3.1 当前已知的具体问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|:---:|
| 1 | `data/faq/FAQ知识库/` 与父目录 `data/faq/` 语义重复 | 目录层级冗余 | 🟡 |
| 2 | `关键词索引.md` 作为配置文件名 | 搜索/排序不可预测，URL 不友好 | 🟡 |
| 3 | `data/reports/周报/` 和 `月报/` | CI/CD 脚本引用路径需 URL 编码 | 🟡 |
| 4 | 模块文件名如 `数智财务AI+.md` 含 `+` 特殊字符 | 部分文件系统/git 工具处理异常 | 🟡 |
| 5 | `data/raw-docs/` 下中英文文件名混用 | 排序混乱，git diff 难读 | 🟡 |
| 6 | 18 个代码文件中硬编码中文路径 | 国际化困难，代码可移植性差 | 🔴 |
| 7 | 数据库 `dept`/`sub_module` 字段存储中文 | 如果目录改名，代码中路径提取逻辑需全部重写 | 🔴 |

### 3.2 代码中硬编码中文示例

```python
# search_engine.py - 大量中文路径引用
FAQ_DIR = DATA_DIR / "faq"
KB_DIR = DATA_DIR / "knowledge"

# db_repo.py - 部门名硬编码
dept_dir = faq.dept or "数智财务组"  # 默认值中文

# search_server.py - 保存路径
faq_dir = DATA_DIR / "faq" / dept / sub_module  # dept/sub_module 是中文

# constants.js - 前端选项
{ label: '数智财务组', value: '数智财务组' }

# faq_generate.py - 部门代码映射
DEPT_CODES = {"数智财务组": "SZ", "免疫规划组": "YM", ...}
```

---

## 四、推荐改造方案

### 4.1 命名映射表

| 中文名 | 推荐英文名 | 理由 |
|--------|----------|------|
| **一级目录（部门）** | | |
| 数智财务组 | `fin-tech` | 简洁、语义明确 |
| 免疫规划组 | `immunization` | 英文标准翻译 |
| 电子档案组 | `e-archive` | 简洁、业界通用 |
| 数字化支撑组 | `digital-support` | 语义明确 |
| **二级目录（子模块）** | | |
| 浙里报 | `zhelibao` | 产品名，保留拼音 |
| 孵化业务 | `incubation` | 英文翻译 |
| 徽报账 | `huibaozhang` | 产品名，保留拼音 |
| 百搭 | `baida` | 产品名，保留拼音 |
| 疫苗馆 | `vaccine-hall` | 英文翻译 |
| 便民服务 | `public-service` | 英文翻译 |
| 数据智控 | `data-control` | 英文翻译 |
| 智慧门诊 | `smart-clinic` | 英文翻译 |
| 智能催种 | `smart-reminder` | 英文翻译 |
| 预防接种 | `vaccination` | 英文翻译 |
| 数字化门诊 | `digital-clinic` | 英文翻译 |
| 入学入托查验 | `enrollment-check` | 英文翻译 |
| 单位与人员管理 | `org-personnel` | 英文翻译 |
| 电子档案 | `e-archive` | 与部门名一致 |
| 发票平台 | `invoice-platform` | 英文翻译 |
| 收费平台 | `payment-platform` | 英文翻译 |
| 结算平台 | `settlement-platform` | 英文翻译 |
| 营收平台 | `revenue-platform` | 英文翻译 |
| 成本平台 | `cost-platform` | 英文翻译 |
| 消息平台 | `message-platform` | 英文翻译 |
| 产研大屏 | `rd-dashboard` | 英文翻译 |
| 数智一体化平台 | `integration-platform` | 英文翻译 |
| 直属 | `direct` | 英文翻译 |
| 其他资金 | `other-funds` | 英文翻译 |
| 小额托收 | `micro-collection` | 英文翻译 |
| 资产管理 | `asset-management` | 英文翻译 |
| 采购管理 | `procurement` | 英文翻译 |
| 票据管理 | `invoice-management` | 英文翻译 |
| 结算中心 | `settlement-center` | 英文翻译 |
| 预算中心 | `budget-center` | 英文翻译 |
| 合同中心 | `contract-center` | 英文翻译 |
| 凭证中心 | `voucher-center` | 英文翻译 |
| 用户体系 | `user-system` | 英文翻译 |
| 费控管理 | `cost-control` | 英文翻译 |
| 数据监管 | `data-supervision` | 英文翻译 |
| 核算归档 | `accounting-archive` | 英文翻译 |
| 流程管理 | `workflow` | 英文翻译 |
| 模版中心 | `template-center` | 英文翻译 |
| 消息中心 | `message-center` | 英文翻译 |
| 辅助功能 | `auxiliary` | 英文翻译 |
| 工作台/官网 | `workbench` | 英文翻译 |
| 冷链云 | `cold-chain` | 英文翻译 |
| 疫苗数仓 | `vaccine-dataware` | 英文翻译 |
| 疫苗通用 | `vaccine-common` | 英文翻译 |
| 浙里接种管理端 | `zheli-vaccine-admin` | 英文翻译 |
| 免疫规划学习云 | `immunization-learning` | 英文翻译 |
| 人工智能应用 | `ai-app` | 英文翻译 |
| 夜餐管理 | `meal-management` | 英文翻译 |
| 工资管理 | `salary-management` | 英文翻译 |
| 收入管理 | `revenue-management` | 英文翻译 |
| 政府投资 | `gov-investment` | 英文翻译 |
| 惠企利民 | `enterprise-benefit` | 英文翻译 |
| 生态对接 | `eco-integration` | 英文翻译 |
| 绩效管理 | `performance` | 英文翻译 |
| 考勤管理 | `attendance` | 英文翻译 |
| 考核总结 | `assessment` | 英文翻译 |
| 车辆管理 | `vehicle-management` | 英文翻译 |
| 项目管理 | `project-management` | 英文翻译 |
| 会议室管理 | `meeting-room` | 英文翻译 |
| 财政指标管理 | `fiscal-indicator` | 英文翻译 |
| 工程管理 | `engineering` | 英文翻译 |
| 公务用车 | `official-vehicle` | 英文翻译 |
| 内容中心 | `content-center` | 英文翻译 |
| 加班管理 | `overtime` | 英文翻译 |
| 工作计划 | `work-plan` | 英文翻译 |
| 应用市场 | `app-market` | 英文翻译 |
| 开放平台 | `open-platform` | 英文翻译 |
| 资产管理平台 | `asset-platform` | 英文翻译 |
| 运营后台 | `ops-console` | 英文翻译 |
| 巡检管理 | `inspection` | 英文翻译 |
| 管物SaaS | `asset-saas` | 英文翻译 |
| 数智财务AI+ | `fin-ai` | 英文翻译 |
| 免疫规划 | `immunization` | 与部门一致 |
| 数字化支撑 | `digital-support` | 与部门一致 |
| 徽报账 | `huibaozhang` | 产品名拼音 |
| 直属 | `direct` | 英文翻译 |
| 孵化业务 | `incubation` | 英文翻译 |
| **其他目录** | | |
| 周报 | `weekly` | 英文翻译 |
| 月报 | `monthly` | 英文翻译 |
| 关键词索引 | `keyword-index` | 英文翻译 |
| FAQ知识库 | *(删除，与 faq/ 重复)* | 冗余目录 |

### 4.2 改造后的目标结构

```
knowledge-base/
├── config/
│   ├── keyword-index.md              # ← 原 关键词索引.md
│   ├── synonyms.json
│   └── schema.sql
├── data/
│   ├── faq/
│   │   ├── INDEX.md
│   │   ├── TEMPLATE.md
│   │   ├── fin-tech/                 # ← 原 数智财务组
│   │   │   ├── zhelibao/             # ← 原 浙里报
│   │   │   │   ├── FAQ-SZ-ZLB-001.md
│   │   │   │   └── ...
│   │   │   └── huibaozhang/          # ← 原 徽报账
│   │   ├── immunization/             # ← 原 免疫规划组
│   │   ├── e-archive/                # ← 原 电子档案组
│   │   └── digital-support/          # ← 原 数字化支撑组
│   ├── knowledge/                    # 同上结构
│   │   ├── fin-tech/
│   │   ├── immunization/
│   │   ├── e-archive/
│   │   └── digital-support/
│   ├── modules/                      # 同上结构
│   ├── raw-docs/                     # 同上结构
│   └── reports/
│       ├── weekly/                   # ← 原 周报
│       └── monthly/                  # ← 原 月报
├── src/
│   ├── scripts/
│   ├── server/
│   │   └── repository/
│   └── web/
│       └── src/components/
├── runtime/
├── docs/
└── README.md
```

### 4.3 代码改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/web/src/components/constants.js` | 修改 | DEPT_OPTIONS 增加 `enValue` 字段，label 保留中文 |
| `src/server/repository/db_repo.py` | 修改 | 新增 `DEPT_PATH_MAP` 映射表，`get_all_faqs()` 等使用英文路径 |
| `src/server/repository/file_repo.py` | 修改 | 同上 |
| `src/server/search_engine.py` | 修改 | FAQ_DIR/KB_DIR 路径提取使用映射表 |
| `src/server/search_server.py` | 修改 | FAQ 保存/读取路径使用映射表 |
| `src/scripts/faq_audit.py` | 修改 | 路径引用使用映射表 |
| `src/scripts/faq_generate.py` | 修改 | DEPT_CODES 路径映射 |
| `src/scripts/faq_export.py` | 修改 | 路径引用 |
| `src/scripts/faq_ticket_link.py` | 修改 | 路径引用 |
| `src/server/migrate_to_db.py` | 修改 | 路径引用 |
| `src/server/extract_kb_keywords.py` | 修改 | 路径引用 |
| `src/server/sync_confluence_reports.py` | 修改 | 路径引用 |
| `src/web/src/components/*.jsx` | 修改 | 7 个前端组件路径引用 |
| `config/schema.sql` | 修改 | 默认部门数据增加英文 code |
| `data/faq/INDEX.md` | 自动更新 | 运行 `faq_audit.py --fix` |
| 46 个目录 | 重命名 | mv 操作 |
| 199 个文件 | 重命名 | mv 操作 |

### 4.4 数据库兼容策略

目录改名后，数据库 `faqs` 表的 `dept`/`sub_module` 字段**保持中文不变**（作为显示名），新增 `dept_path`/`sub_module_path` 字段存储英文路径名，代码中通过映射表双向转换：

```python
# 新增映射表（src/server/repository/dept_mapping.py）
DEPT_TO_PATH = {
    "数智财务组": "fin-tech",
    "免疫规划组": "immunization",
    "电子档案组": "e-archive",
    "数字化支撑组": "digital-support",
}
PATH_TO_DEPT = {v: k for k, v in DEPT_TO_PATH.items()}

def get_dept_path(dept_name: str) -> str:
    return DEPT_TO_PATH.get(dept_name, dept_name)

def get_dept_name(dept_path: str) -> str:
    return PATH_TO_DEPT.get(dept_path, dept_path)
```

---

## 五、业界评分对比

| 维度 | 业界最佳 | 当前项目 | 差距 |
|------|:---:|:---:|------|
| 命名规范 | kebab-case 全英文 | 中英文混用 | 🔴 需全面改造 |
| 跨平台兼容 | 纯 ASCII | 中文路径 | 🔴 终端/CI 易乱码 |
| URL 友好 | 直接作为 URL 路径 | 需 URL 编码 | 🟡 影响 API 设计 |
| 代码可移植性 | 路径与语言无关 | 硬编码中文 | 🔴 国际化困难 |
| 目录层次 | ≤3 层 | 4-5 层 | 🟡 可接受 |
| 代码/数据分离 | src/ + data/ + config/ | 已实现 | ✅ 良好 |
| 版本化 | 语义化版本目录 | 文件名日期 | 🟡 可改进 |
| Git 友好 | 纯文本 diff | 中文文件名 diff 可读性差 | 🟡 影响 Code Review |

---

## 六、总结

**当前项目最大的结构问题是中英文混用**。虽然中文命名对中国开发者直观，但在以下场景会出问题：
- CI/CD 脚本中路径需 URL 编码
- Windows 终端 git bash 可能乱码
- 前端 API 路径中中文需 `encodeURIComponent`
- 代码硬编码中文导致国际化困难
- Git diff 中文文件名可读性差

**建议**：目录名改为英文 kebab-case，数据库和前端的显示名保留中文，代码中新增一个中英文映射表做桥接。