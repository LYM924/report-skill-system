/**
 * useAdminModule.js - 管理模块权限检查 hook
 *
 * 检查当前用户是否有权访问指定管理模块，
 * 角色不足时返回 allowed=false，前端显示"无权限"提示。
 */

import { useAppContext } from '../../AppContext';

/**
 * @param {'user'|'admin'} requiredRole - 模块所需的最低角色
 * @returns {{ allowed: boolean, userRole: string }}
 */
export function useAdminModule(requiredRole) {
  const { userRole } = useAppContext();
  const allowed = requiredRole === 'user' || userRole === 'admin';
  return { allowed, userRole };
}

export default useAdminModule;
