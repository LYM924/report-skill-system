/**
 * 模拟数据 - 知识库前端原型
 * 后续对接后端 API 后替换为真实数据
 */

// ===== 左侧导航扁平分类 =====
export const navCategories = [
  { key: 'all', label: '全部知识', icon: 'FolderOpenOutlined', count: 3256 },
  { key: 'product', label: '产品模块', icon: 'AppstoreOutlined', count: 856 },
  { key: 'business', label: '业务模块', icon: 'ApartmentOutlined', count: 423 },
  { key: 'ticket', label: '工单知识', icon: 'FileTextOutlined', count: 1128 },
  { key: 'dept', label: '部门知识', icon: 'TeamOutlined', count: 586, active: true },
  { key: 'faq', label: 'FAQ库', icon: 'QuestionCircleOutlined', count: 842 },
  { key: 'ticket_deposit', label: '工单沉淀', icon: 'BugOutlined', count: 376 },
];

// 部门知识下的子分类
export const deptSubCategories = [
  { key: 'szcw', label: '数智财务', count: 186 },
  { key: 'myp', label: '免疫规划', count: 142 },
  { key: 'da', label: '电子档案', count: 98 },
  { key: 'szh', label: '数字化支撑', count: 76 },
  { key: 'faq_sub', label: 'FAQ库', count: 84 },
];

// 二级：业务模块（用于筛选）
export const businessModules = [
  { key: 'szcw', label: '数智财务', count: 124 },
  { key: 'myp', label: '免疫规划', count: 78 },
  { key: 'da', label: '电子档案', count: 32 },
  { key: 'szh', label: '数字化支撑', count: 45 },
];

// 三级：部门筛选
export const departments = [
  { key: 'zlb', label: '浙里报', business: 'szcw' },
  { key: 'hbz', label: '徽报账', business: 'szcw' },
  { key: 'fh', label: '孵化业务', business: 'szcw' },
  { key: 'zs', label: '数智财务组-直属', business: 'szcw' },
  { key: 'ym', label: '免疫规划组', business: 'myp' },
  { key: 'dz', label: '电子档案组', business: 'da' },
  { key: 'szhzc', label: '数字化支撑组', business: 'szh' },
];

// 四级：产品模块（核心树节点）
export const productModules = [
  // 浙里报
  { key: 'zlb-zcgl', label: '支出管理', dept: 'zlb', business: 'szcw', desc: '浙里报核心支出管理模块，覆盖报销、申请、审批全流程', owner: '张三', devOwner: '李四' },
  { key: 'zlb-ysgl', label: '预算中心', dept: 'zlb', business: 'szcw', desc: '预算申报、预算执行、预算配置管理', owner: '王五', devOwner: '赵六' },
  { key: 'zlb-jszx', label: '结算中心', dept: 'zlb', business: 'szcw', desc: '出纳结算、公务卡管理、支付管理', owner: '张三', devOwner: '钱七' },
  { key: 'zlb-gwcl', label: '公务用车', dept: 'zlb', business: 'szcw', desc: '车辆管理、用车申请、公车结算', owner: '孙八', devOwner: '周九' },
  { key: 'zlb-htzx', label: '合同中心', dept: 'zlb', business: 'szcw', desc: '合同审批、合同履约、合同归档', owner: '吴十', devOwner: '郑十一' },
  { key: 'zlb-pjgl', label: '票据管理', dept: 'zlb', business: 'szcw', desc: '发票管理、票据补充、银行回单', owner: '冯十二', devOwner: '陈十三' },
  { key: 'zlb-cgnc', label: '采/非采场景', dept: 'zlb', business: 'szcw', desc: '采购场景、非采购场景配置管理', owner: '褚十四', devOwner: '卫十五' },
  // 孵化业务
  { key: 'fh-bd', label: '百搭', dept: 'fh', business: 'szcw', desc: '百搭单据配置、组件管理', owner: '蒋十六', devOwner: '沈十七' },
  { key: 'fh-gw', label: '管物SaaS', dept: 'fh', business: 'szcw', desc: '物资管理、标准物资、库存管理', owner: '韩十八', devOwner: '杨十九' },
  // 免疫规划
  { key: 'ym-yfjz', label: '预防接种', dept: 'ym', business: 'myp', desc: '接种管理、接种记录、接种提醒', owner: '朱二十', devOwner: '秦二一' },
  { key: 'ym-ymg', label: '疫苗馆', dept: 'ym', business: 'myp', desc: '疫苗流通、疫苗追溯、疫苗库存', owner: '许二二', devOwner: '何二三' },
  // 电子档案
  { key: 'dz-dzda', label: '电子档案', dept: 'dz', business: 'da', desc: '电子归档、档案管理、无纸化', owner: '吕二四', devOwner: '张二五' },
  // 数字化支撑
  { key: 'szh-sfpt', label: '收费平台', dept: 'szhzc', business: 'szh', desc: '收费管理、收入管理', owner: '孔二六', devOwner: '曹二七' },
  { key: 'szh-fppt', label: '发票平台', dept: 'szhzc', business: 'szh', desc: '发票开具、发票管理', owner: '严二八', devOwner: '华二九' },
];

// ===== 中间文档列表数据 =====

export const mockDocuments = [
  {
    id: 1, title: '2026-05 版本迭代说明', type: '版本迭代', module: 'zlb-zcgl', date: '2026-05-15',
    summary: '支出管理模块5月版本更新，包含报销单关联申请单优化、审批流程改造等功能',
    tags: ['版本迭代', '支出管理', '报销单'],
  },
  {
    id: 2, title: '2026-04 版本迭代说明', type: '版本迭代', module: 'zlb-zcgl', date: '2026-04-20',
    summary: '支出管理模块4月版本更新，新增批量报销功能',
    tags: ['版本迭代', '支出管理', '批量报销'],
  },
  {
    id: 3, title: '支出管理功能操作手册', type: '操作手册', module: 'zlb-zcgl', date: '2026-03-10',
    summary: '支出管理模块完整操作指南，涵盖我的单据、单据列表、审批流程等',
    tags: ['操作手册', '支出管理', '用户指南'],
  },
  {
    id: 4, title: '衢州医疗项目交底文档', type: '项目文档', module: 'zlb-zcgl', date: '2026-06-01',
    summary: '衢州医疗项目交底，包含公务出行、一般事项、公务接待等场景',
    tags: ['项目文档', '交底', '衢州医疗'],
  },
  {
    id: 5, title: '预算中心产品功能说明书', type: '功能说明', module: 'zlb-ysgl', date: '2026-02-15',
    summary: '预算中心完整功能说明，覆盖预算申报、执行、配置、指标管理',
    tags: ['功能说明', '预算中心', '产品文档'],
  },
  {
    id: 6, title: '2026-03 版本迭代说明', type: '版本迭代', module: 'zlb-ysgl', date: '2026-03-22',
    summary: '预算中心3月版本迭代，新增预算绩效管理功能',
    tags: ['版本迭代', '预算中心', '绩效管理'],
  },
  {
    id: 7, title: '结算中心操作指南', type: '操作手册', module: 'zlb-jszx', date: '2026-01-18',
    summary: '结算中心操作指南，涵盖出纳结算、公务卡管理、支付流程',
    tags: ['操作手册', '结算中心', '用户指南'],
  },
  {
    id: 8, title: '合同管理产品功能说明书', type: '功能说明', module: 'zlb-htzx', date: '2026-06-11',
    summary: '合同管理全生命周期功能说明，支持新建、审批、履约、归档',
    tags: ['功能说明', '合同中心', '合同管理'],
  },
  {
    id: 9, title: '2026-01 版本迭代说明', type: '版本迭代', module: 'fh-bd', date: '2026-01-25',
    summary: '百搭单据组件配置更新，新增关联单据组件',
    tags: ['版本迭代', '百搭', '组件配置'],
  },
  {
    id: 10, title: '预防接种操作手册', type: '操作手册', module: 'ym-yfjz', date: '2026-04-05',
    summary: '预防接种模块操作手册，涵盖接种记录、提醒、统计',
    tags: ['操作手册', '预防接种', '免疫规划'],
  },
  {
    id: 11, title: '疫苗馆流通管理操作文档', type: '操作手册', module: 'ym-ymg', date: '2026-03-15',
    summary: '疫苗流通管理操作文档，含疫苗追溯、库存管理',
    tags: ['操作手册', '疫苗馆', '疫苗流通'],
  },
  {
    id: 12, title: '电子档案归档流程说明', type: '功能说明', module: 'dz-dzda', date: '2026-05-20',
    summary: '电子档案归档流程说明，涵盖归档、检索、管理',
    tags: ['功能说明', '电子档案', '归档'],
  },
];

// ===== 右侧 FAQ 数据 =====

export const mockFAQs = [
  {
    id: 'FAQ-SZ-ZLB-001', title: '公务出行报销单选不到申请单',
    question: '为什么在创建公务出行报销单的时候选择不到申请单？',
    answer: '共7种原因：1. 申请单未审批通过；2. 申请单已被关联使用；3. 场景类型不匹配；4. 申请单金额已用完；5. 经办人不一致；6. 关账期间限制；7. 申请单被标记"无需报销"。',
    module: 'zlb-zcgl', keywords: ['报销单', '申请单', '公务出行', '无需报销'],
  },
  {
    id: 'FAQ-SZ-ZLB-002', title: '报销单提交后审批流程卡住',
    question: '报销单提交后审批流程一直不动怎么办？',
    answer: '检查审批人是否在职、是否有代理审批人设置、审批流程配置是否正确。如确认无误，联系运营在后台查看审批流程日志。',
    module: 'zlb-zcgl', keywords: ['报销单', '审批', '流程', '卡住'],
  },
  {
    id: 'FAQ-SZ-ZLB-003', title: '预算指标同步失败',
    question: '财政指标同步失败怎么处理？',
    answer: '先确认指标来源系统是否正常，再检查浙里报指标配置是否正确。常见原因为指标编码不匹配或同步接口超时。',
    module: 'zlb-ysgl', keywords: ['预算', '指标', '同步', '失败'],
  },
  {
    id: 'FAQ-SZ-ZLB-004', title: '发票上传后无法识别',
    question: '上传发票后系统识别不了怎么办？',
    answer: '检查发票图片清晰度，确保发票号码、金额清晰可辨。如OCR识别失败，可手动录入发票信息。',
    module: 'zlb-pjgl', keywords: ['发票', '上传', '识别', 'OCR'],
  },
  {
    id: 'FAQ-SZ-ZLB-005', title: '合同审批流程如何配置',
    question: '合同审批流程在哪里配置？',
    answer: '在运营后台→流程管理→合同审批流程中配置。支持按合同金额、类型设置不同审批层级。',
    module: 'zlb-htzx', keywords: ['合同', '审批', '流程', '配置'],
  },
  {
    id: 'FAQ-YM-YM-001', title: '接种记录无法保存',
    question: '预防接种记录提交后保存失败？',
    answer: '检查接种人信息是否完整、疫苗批号是否正确、接种日期是否在有效期内。',
    module: 'ym-yfjz', keywords: ['接种', '记录', '保存', '失败'],
  },
];

// ===== 右侧工单数据 =====

export const mockTickets = [
  {
    id: '202606241619265746626', title: '公务出行报销申请单找不到',
    type: '咨询', status: '已解决', module: 'zlb-zcgl',
    description: '用户在创建公务出行报销单时，关联申请单列表找不到目标申请单',
    resolution: '确认申请单已被标记为"无需报销"，撤销后恢复正常',
    frequency: 15,
  },
  {
    id: '202606010934125662261', title: '报销审批流程超时',
    type: '故障', status: '已解决', module: 'zlb-zcgl',
    description: '报销单提交后，审批流程超过24小时未处理',
    resolution: '审批人休假未设置代理，后台手动转交处理',
    frequency: 8,
  },
  {
    id: '202606101053135698418', title: '预算指标数据不一致',
    type: '咨询', status: '已解决', module: 'zlb-ysgl',
    description: '浙里报预算指标与财政系统指标数据不一致',
    resolution: '手动触发指标同步，数据恢复一致',
    frequency: 5,
  },
  {
    id: '202606231116315739768', title: '采购申请单金额计算错误',
    type: '故障', status: '处理中', module: 'zlb-cgnc',
    description: '采购申请单自动计算金额与实际金额不符',
    resolution: '开发排查中，临时方案为手动修改金额',
    frequency: 3,
  },
  {
    id: '202606121538465710229', title: '发票上传后无法查看',
    type: '咨询', status: '已解决', module: 'zlb-pjgl',
    description: '用户上传发票后，在票据列表中无法查看',
    resolution: '浏览器缓存问题，清除缓存后正常',
    frequency: 6,
  },
  {
    id: '202606261425055755323', title: '接种记录同步延迟',
    type: '故障', status: '已解决', module: 'ym-yfjz',
    description: '接种记录提交后，数据同步到省平台延迟超过30分钟',
    resolution: '同步队列积压，扩容后恢复',
    frequency: 4,
  },
];

// ===== 搜索建议 =====
export const searchSuggestions = [
  '报销单审批流程',
  '预算指标同步',
  '发票上传识别',
  '合同审批配置',
  '接种记录保存',
  '采购申请单',
  '公务出行报销',
  '电子档案归档',
];

// ===== 知识概览数据卡片 =====
export const dashboardStats = {
  totalDocs: 3256,
  faqCount: 842,
  weekQuestions: 618,
  weekNew: 966,
  weekNewGrowth: 12.5,
  aiMatchConfidence: 92,
  activeUsers: 186,
};

// ===== 文档列表数据 =====
export const docListData = [
  { id: 1, name: '产品模块说明v2.3', product: '数智财务', dept: '浙里报', updated: '2026-08-10', tags: ['产品说明', '系统文档'], confidence: 92 },
  { id: 2, name: '权限配置指南', product: '免疫规划', dept: '免疫规划组', updated: '2026-08-09', tags: ['配置指南', '权限管理'], confidence: 88 },
  { id: 3, name: '客服知识模板', product: '电子档案', dept: '电子档案组', updated: '2026-08-08', tags: ['模板', '客服'], confidence: 95 },
  { id: 4, name: '工单处理规范', product: '数字化支撑', dept: '数字化支撑组', updated: '2026-08-07', tags: ['规范', '工单'], confidence: 90 },
  { id: 5, name: '浙里报操作手册', product: '数智财务', dept: '浙里报', updated: '2026-08-06', tags: ['操作手册', '浙里报'], confidence: 91 },
  { id: 6, name: 'FAQ 维护流程', product: '通用', dept: '运营', updated: '2026-08-05', tags: ['FAQ', '维护'], confidence: 87 },
  { id: 7, name: '疫苗馆用户指南', product: '免疫规划', dept: '免疫规划组', updated: '2026-08-04', tags: ['用户指南', '疫苗'], confidence: 93 },
  { id: 8, name: '电子档案归档细则', product: '电子档案', dept: '电子档案组', updated: '2026-08-03', tags: ['归档', '细则'], confidence: 89 },
];

// ===== 最近更新数据 =====
export const recentUpdates = [
  { id: 1, title: '产品模块说明v2.3', author: '张三', updated: '10分钟前', type: 'edit' },
  { id: 2, title: '权限配置指南', author: '李四', updated: '30分钟前', type: 'edit' },
  { id: 3, title: 'FAQ 新增条目', author: '王五', updated: '1小时前', type: 'add' },
  { id: 4, title: '工单处理规范', author: '赵六', updated: '2小时前', type: 'edit' },
  { id: 5, title: '浙里报操作手册', author: '张三', updated: '3小时前', type: 'add' },
  { id: 6, title: '客服知识模板', author: '李四', updated: '5小时前', type: 'edit' },
];

// ===== 趋势数据（模拟折线图） =====
export const trendData = [
  { month: '3月', value: 120 },
  { month: '4月', value: 200 },
  { month: '5月', value: 150 },
  { month: '6月', value: 310 },
  { month: '7月', value: 280 },
  { month: '8月', value: 410 },
];