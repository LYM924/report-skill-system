/**
 * LeftSidebar.jsx - 左侧导航栏
 *
 * 三个视图模式 + 可折叠:
 * - 产品模块: 所属产品线 → 所属产品 → 模块
 * - 业务模块: 所属领域 → 产品线 → 产品 → 模块
 * - 部门知识: 一级部门 → 二级部门 → 三级部门
 * - 快捷入口: 全部知识、FAQ库、工单沉淀、工单知识
 */

import React, { useState } from 'react';
import { Menu, Button, Segmented } from 'antd';
import {
  FolderOpenOutlined, AppstoreOutlined, ApartmentOutlined,
  FileTextOutlined, TeamOutlined, QuestionCircleOutlined,
  BugOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from '@ant-design/icons';
import menuData from '../data/menuData.json';

const { productModules, businessModules, deptKnowledge } = menuData;

/** 构建产品模块树 */
function buildProductItems() {
  return Object.entries(productModules).map(([line, products]) => ({
    key: `prod-${line}`,
    label: line,
    icon: <AppstoreOutlined />,
    children: Object.entries(products).map(([prod, modules]) => ({
      key: `prod-${line}-${prod}`,
      label: `${prod} (${modules.length})`,
      children: modules.map((m) => ({
        key: `prod-${line}-${prod}-${m.name}`,
        label: m.name,
      })),
    })),
  }));
}

/** 构建业务模块树 */
function buildBizItems() {
  return Object.entries(businessModules).map(([domain, lines]) => {
    const totalMods = Object.values(lines).reduce(
      (sum, prods) => sum + Object.values(prods).reduce((s, mods) => s + mods.length, 0), 0
    );
    return {
      key: `biz-${domain}`,
      label: `${domain} (${totalMods})`,
      icon: <ApartmentOutlined />,
      children: Object.entries(lines).map(([line, prods]) => ({
        key: `biz-${domain}-${line}`,
        label: line,
        children: Object.entries(prods).map(([prod, mods]) => ({
          key: `biz-${domain}-${line}-${prod}`,
          label: `${prod} (${mods.length})`,
          children: mods.map((name) => ({
            key: `biz-${domain}-${line}-${prod}-${name}`,
            label: name,
          })),
        })),
      })),
    };
  });
}

/** 构建部门知识树 */
function buildDeptItems() {
  return Object.entries(deptKnowledge).map(([d1, d2s]) => {
    const totalD1 = Object.values(d2s).reduce(
      (sum, d3s) => sum + Object.values(d3s).reduce((s, mods) => s + mods.length, 0), 0
    );
    return {
      key: `dept-${d1}`,
      label: `${d1} (${totalD1})`,
      icon: <TeamOutlined />,
      children: Object.entries(d2s).map(([d2, d3s]) => {
        const totalD2 = Object.values(d3s).reduce((s, mods) => s + mods.length, 0);
        // 如果三级只有一个值且是"未分类"，就不展开三级
        const d3Keys = Object.keys(d3s);
        const skipD3 = d3Keys.length === 1 && d3Keys[0] === '未分类';
        if (skipD3) {
          return {
            key: `dept-${d1}-${d2}`,
            label: `${d2} (${totalD2})`,
            children: d3s['未分类'].map((name) => ({
              key: `dept-${d1}-${d2}-${name}`,
              label: name,
            })),
          };
        }
        return {
          key: `dept-${d1}-${d2}`,
          label: `${d2} (${totalD2})`,
          children: Object.entries(d3s).map(([d3, mods]) => ({
            key: `dept-${d1}-${d2}-${d3}`,
            label: `${d3} (${mods.length})`,
            children: mods.map((name) => ({
              key: `dept-${d1}-${d2}-${d3}-${name}`,
              label: name,
            })),
          })),
        };
      }),
    };
  });
}

const quickItems = [
  { key: 'all', label: '全部知识', icon: <FolderOpenOutlined /> },
  { key: 'faq', label: 'FAQ库', icon: <QuestionCircleOutlined /> },
  { key: 'ticket_deposit', label: '工单沉淀', icon: <BugOutlined /> },
  { key: 'ticket', label: '工单知识', icon: <FileTextOutlined /> },
];

const VIEW_OPTIONS = [
  { label: '产品模块', value: 'product' },
  { label: '业务模块', value: 'business' },
  { label: '部门知识', value: 'dept' },
];

function LeftSidebar({ selectedNav, onNavChange, collapsed, onToggleCollapse }) {
  const [viewMode, setViewMode] = useState('product');

  const handleClick = ({ key }) => {
    onNavChange(key);
  };

  const treeItems = viewMode === 'product'
    ? buildProductItems()
    : viewMode === 'business'
    ? buildBizItems()
    : buildDeptItems();

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 折叠按钮 */}
      <div style={{
        padding: collapsed ? '8px 0' : '8px 8px',
        display: 'flex', justifyContent: collapsed ? 'center' : 'flex-end',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <Button
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={onToggleCollapse}
          style={{ color: '#64748B', fontSize: 16 }}
        />
      </div>

      {/* 快捷入口 */}
      {!collapsed && (
        <div style={{ padding: '8px 8px 0', borderBottom: '1px solid #f0f0f0' }}>
          <Menu
            mode="inline"
            selectedKeys={[selectedNav]}
            onClick={handleClick}
            items={quickItems}
            style={{ background: 'transparent', borderRight: 'none' }}
          />
        </div>
      )}

      {/* 视图切换 */}
      {!collapsed && (
        <div style={{ padding: '8px' }}>
          <Segmented
            block
            size="small"
            options={VIEW_OPTIONS}
            value={viewMode}
            onChange={setViewMode}
            style={{ fontSize: 12 }}
          />
        </div>
      )}

      {/* 树形菜单 */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[selectedNav]}
          onClick={handleClick}
          items={collapsed ? quickItems : treeItems}
          style={{ background: 'transparent', borderRight: 'none', paddingTop: 4 }}
        />
      </div>
    </div>
  );
}

export default LeftSidebar;