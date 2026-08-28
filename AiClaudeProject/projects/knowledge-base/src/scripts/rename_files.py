#!/usr/bin/env python3
"""批量重命名中文文件名为英文"""
import os, sys, re
from pathlib import Path

BASE = Path("/Users/zcy1/Desktop/ClaudeProject/AiClaudeProject/projects/knowledge-base")
sys.path.insert(0, str(BASE / "src" / "server" / "repository"))
from dept_mapping import SUBMODULE_TO_PATH

# ---- 中文词 → 英文词 映射（用于文件名中的中文片段） ----
WORD_MAP = {
    "预算指标同步失败": "budget-indicator-sync-failed",
    "发票上传后无法识别": "invoice-upload-not-recognized",
    "报销单提交后审批流程卡住": "approval-flow-stuck",
    "公务出行报销单选不到申请单": "travel-reimbursement-application-not-selectable",
    "合同审批流程如何配置": "contract-approval-config",
    "接种记录同步延迟": "vaccination-record-sync-delay",
    "接种记录无法保存": "vaccination-record-save-failed",
    "疫苗库存与实际不符": "vaccine-inventory-mismatch",
    "未满月的小孩支持接种那些疫苗": "newborn-vaccination-support",
    "电子档案归档后无法检索": "archive-search-failed",
    "发票平台开票失败": "invoice-platform-issue",
    "收费平台支付失败": "payment-platform-failed",
    "收费平台保证金退款失败": "payment-platform-deposit-refund-failed",
    "收费平台历史账单未出账": "payment-platform-historical-billing",
    "银行回单同步后电子档案不显示": "bank-receipt-sync-not-showing",
    "核算云归档后电子档案无数据": "accounting-cloud-archive-no-data",
    "银行回单无法自动关联报销单": "bank-receipt-auto-link-failed",
    "四性检测不通过但详情显示已通过": "four-property-check-inconsistent",
    "实体移交接收操作异常": "physical-transfer-error",
    "记账凭证传输后核算云查不到": "voucher-transfer-not-found",
    "银行回单关联凭证后取消再关联失败": "bank-receipt-relink-failed",
    "归档后附件缺失或显示空白": "archive-attachment-missing",
    "支付限额指标未同步到浙里报": "payment-limit-not-synced",
    "报销单收款账户选不到": "reimbursement-payee-not-selectable",
    "接种记录查验失败": "vaccination-check-failed",
    "预防接种档案迁出失败": "vaccination-record-transfer-failed",
    "发布说明": "release-notes",
    "发版说明": "release-notes",
    "月发布说明": "release-notes",
    "交底文档": "handover-doc",
    "项目交底": "project-handover",
    "操作手册": "user-manual",
    "操作文档": "user-manual",
    "功能说明": "feature-doc",
    "版本迭代": "version-iteration",
    "技术支持周报": "tech-support-weekly",
    "步骤": "steps",
    "影响": "impact",
    "需求实现": "requirement",
    "需求单号": "requirement-id",
    "必填": "required",
    "收入": "revenue",
    "金额": "amount",
    "项目明细": "project-detail",
    "采购管理": "procurement",
    "关注人员": "followers",
    "民生项目": "livelihood-project",
    "菜单路径": "menu-path",
    "疫苗身份": "vaccine-identity",
    "问题": "issue",
    "月龄": "month-age",
    "注意事项": "notes",
    "死亡": "death",
    "上传": "upload",
    "接种记录": "vaccination-record",
    "人证核验": "identity-verification",
    "点击": "click",
    "注意": "note",
    "包含": "includes",
    "管理端": "admin",
    "次数": "count",
    "出生队列": "birth-cohort",
    "疫苗专报": "vaccine-report",
    "未全程接": "incomplete-vaccination",
    "情况": "status",
    "疫苗采购": "vaccine-procurement",
    "监测": "monitoring",
    "学校名称": "school-name",
    "今日接种": "today-vaccination",
    "附加信息": "additional-info",
    "资金来源": "funding-source",
    "流感疫苗": "flu-vaccine",
    "入学入托": "enrollment",
    "健康询问": "health-inquiry",
    "浙江省疫": "zhejiang-vaccine",
    "疫苗": "vaccine",
    "模块": "module",
    "浙里接种": "zheli-vaccination",
    "免疫规划": "immunization",
    "数智财务": "fin-tech",
    "智慧门诊": "smart-clinic",
    "数字化门诊": "digital-clinic",
    "单位与人": "org-personnel",
    "智能催种": "smart-reminder",
    "数据智控": "data-control",
    "便民服务": "public-service",
    "预防接种": "vaccination",
    "疫苗馆": "vaccine-hall",
    "其他资金": "other-funds",
    "小额托收": "micro-collection",
    "资产管理": "asset-management",
    "浙里报": "zhelibao",
    "百搭": "baida",
    "内容中心": "content-center",
    "加班管理": "overtime",
    "工作计划": "work-plan",
    "应用市场": "app-market",
    "开放平台": "open-platform",
    "资产管理平台": "asset-platform",
    "运营后台": "ops-console",
    "凭证中心": "voucher-center",
    "巡检管理": "inspection",
    "数据监管": "data-supervision",
    "核算归档": "accounting-archive",
    "模版中心": "template-center",
    "流程管理": "workflow",
    "消息中心": "message-center",
    "用户体系": "user-system",
    "票据管理": "invoice-management",
    "结算中心": "settlement-center",
    "费控管理": "cost-control",
    "辅助功能": "auxiliary",
    "管物SaaS": "asset-saas",
    "工作台_官网": "workbench",
    "冷链云": "cold-chain",
    "疫苗数仓": "vaccine-dataware",
    "疫苗通用": "vaccine-common",
    "浙里接种管理端": "zheli-vaccine-admin",
    "免疫规划学习云": "immunization-learning",
    "人工智能应用": "ai-app",
    "电子档案": "e-archive",
    "发票平台": "invoice-platform",
    "收费平台": "payment-platform",
    "结算平台": "settlement-platform",
    "营收平台": "revenue-platform",
    "成本平台": "cost-platform",
    "消息平台": "message-platform",
    "产研大屏": "rd-dashboard",
    "数智一体化平台": "integration-platform",
    "徽报账": "huibaozhang",
    "合同中心": "contract-center",
    "合同管理": "contract-management",
    "直属": "direct",
    "孵化业务": "incubation",
    "数字化支撑": "digital-support",
    "数字化": "digital",
    "衢州医疗": "quzhou-medical",
    "浙师大项目": "zheshida-project",
    "嵊州医疗交底": "shengzhou-medical-handover",
    "文旅厅预算管理项目交底": "culture-tourism-budget-project",
    "农村流感项目": "rural-flu-project",
    "疫苗流通相关改造": "vaccine-distribution-upgrade",
    "与省疾控汇报内容": "provincial-cdc-report",
    "删除与SaaS产科数据重档的个案": "dedup-saas-obstetrics",
    "刷脸读档": "face-recognition",
    "运营平台": "ops-platform",
    "用户中心": "user-center",
    "内部同步": "internal-sync",
    "常见问题FAQ": "faq",
    "合同管理V": "contract-management-v",
    "合同管理": "contract-management",
}

def translate_filename(name):
    """将中文文件名翻译为英文"""
    # 先处理特殊字符
    name = name.replace("【", "").replace("】", "").replace("&", "-").replace("＋", "+")
    name = name.replace("：", "-").replace("（", "-").replace("）", "").replace(" ", "-")
    name = name.replace("_", "-")

    # 替换中文词
    for cn, en in sorted(WORD_MAP.items(), key=lambda x: -len(x[0])):
        name = name.replace(cn, en)

    # 清理多余连字符
    name = re.sub(r'-{2,}', '-', name)
    name = name.strip('-')
    # 确保小写
    name = name.lower()
    # 移除非法字符
    name = re.sub(r'[^\w\-\.\+]', '', name)
    return name or "unnamed"


# 收集所有需要重命名的文件
renames = []
for root, dirs, files in os.walk(str(BASE / "data")):
    for f in files:
        if re.search(r'[一-龥]', f):
            old_path = Path(root) / f
            new_name = translate_filename(f)
            new_path = Path(root) / new_name
            if old_path != new_path:
                renames.append((old_path, new_path))

print(f"Files to rename: {len(renames)}")
for old, new in renames:
    if not new.exists():
        old.rename(new)
        print(f"  {old.name} → {new.name}")
    else:
        print(f"  ⚠ SKIP (exists): {old.name} → {new.name}")

# Verify
remaining = 0
for root, dirs, files in os.walk(str(BASE / "data")):
    for f in files:
        if re.search(r'[一-龥]', f):
            remaining += 1
            print(f"  ❌ STILL CN: {f}")

print(f"\nDone: {len(renames)} renamed, {remaining} remaining")