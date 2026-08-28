/**
 * constants.js - 共享常量
 *
 * 部门选项从 /api/departments/options 动态获取，不再硬编码。
 * 为兼容旧代码，保留 DEPT_OPTIONS 作为默认空数组，
 * 组件应使用 fetchDeptOptions() 或直接 fetch API。
 */

// 默认空列表（真实数据从 API 获取）
const DEPT_OPTIONS = [];

/** 从 API 获取部门选项列表，按层级组织标签 */
async function fetchDeptOptions() {
  try {
    const resp = await fetch('/api/departments/options');
    const data = await resp.json();
    return (data?.options || []).map(d => ({
      label: d.label,
      value: d.name,
      id: d.id,
      level: d.level,
      parent_name: d.parent_name,
    }));
  } catch {
    return [];
  }
}

export { DEPT_OPTIONS, fetchDeptOptions };