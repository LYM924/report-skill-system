/**
 * admin/index.js - 管理模块注册表
 *
 * 所有管理模块在此声明：key, 标题, 图标, 组件, 所需角色。
 * LeftSidebar 和 CenterContent 从此注册表动态生成菜单和路由，
 * 新增管理页面只需：1) 创建组件 2) 在此文件加一行注册。
 */

import React, { lazy, Suspense } from 'react';
import {
  ApiOutlined, UserOutlined, HeartOutlined,
  AuditOutlined, SettingOutlined, DatabaseOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';

// 懒加载管理组件
const SettingsCenter = lazy(() => import('./SettingsCenter'));
const UserManager = lazy(() => import('./UserManager'));
const SystemHealth = lazy(() => import('./SystemHealth'));
const AuditLog = lazy(() => import('./AuditLog'));
const SystemConfig = lazy(() => import('./SystemConfig'));
const DataManagement = lazy(() => import('./DataManagement'));
const ModuleMapping = lazy(() => import('./ModuleMapping'));

/**
 * 管理模块注册表
 *
 * @property {string} key - 路由 key（与 LeftSidebar selectedNav 匹配）
 * @property {string} title - 菜单显示标题
 * @property {ReactElement} icon - 菜单图标
 * @property {React.LazyExoticComponent} component - 懒加载组件
 * @property {'user'|'admin'} role - 最低访问角色（'user' = 所有登录用户可见）
 * @property {number} order - 菜单排序权重（小的在前）
 */
export const ADMIN_MODULES = [
  { key: 'settings-ai', title: '配置中心', icon: <ApiOutlined />, component: SettingsCenter, role: 'user', order: 10 },
  { key: 'settings-users', title: '用户管理', icon: <UserOutlined />, component: UserManager, role: 'admin', order: 20 },
  { key: 'system-health', title: '系统健康', icon: <HeartOutlined />, component: SystemHealth, role: 'admin', order: 30 },
  { key: 'audit-log', title: '审计日志', icon: <AuditOutlined />, component: AuditLog, role: 'admin', order: 40 },
  { key: 'system-config', title: '系统配置', icon: <SettingOutlined />, component: SystemConfig, role: 'admin', order: 50 },
  { key: 'data-management', title: '数据管理', icon: <DatabaseOutlined />, component: DataManagement, role: 'admin', order: 60 },
  { key: 'module-mapping', title: '模块映射', icon: <ApartmentOutlined />, component: ModuleMapping, role: 'admin', order: 70 },
];

/**
 * 根据用户角色过滤可见模块
 * @param {'admin'|'user'} userRole
 * @returns {Array} 当前用户可见的管理模块列表
 */
export function getVisibleModules(userRole) {
  return ADMIN_MODULES
    .filter(m => m.role === 'user' || userRole === 'admin')
    .sort((a, b) => a.order - b.order);
}

/**
 * 根据 key 查找模块
 * @param {string} key
 * @param {'admin'|'user'} userRole
 * @returns {object|undefined} 匹配的模块（角色不足则返回 undefined）
 */
export function findModule(key, userRole) {
  return ADMIN_MODULES.find(m => m.key === key && (m.role === 'user' || userRole === 'admin'));
}
