/**
 * LeftSidebar.jsx - 左侧导航栏
 *
 * 垂直菜单结构：
 * - 快捷入口: 全部知识、FAQ库（可展开，按部门分组）、工单知识
 * - 部门知识（可展开）: 一级部门 → 二级部门 → 三级部门
 * - 业务模块（可展开）: 领域 → 产品线 → 产品 → 模块
 * - 产品模块（可展开）: 产品线 → 产品 → 模块
 */

import React, { useState, useEffect } from 'react';
import { authFetch } from '../api';
import { Menu, Button, Spin } from 'antd';
import {
  FolderOpenOutlined, AppstoreOutlined, ApartmentOutlined,
  FileTextOutlined, TeamOutlined, QuestionCircleOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, BarChartOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { getVisibleModules } from './admin';

/** 构建产品模块子菜单 */
function buildProductChildren(menuData) {
  if (!menuData?.productModules) return [];
  return Object.entries(menuData.productModules).map(([line, products]) => ({
    key: `prod-${line}`,
    label: line,
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

/** 构建业务模块子菜单（只到产品级，不展示最子级模块） */
function buildBizChildren(menuData) {
  if (!menuData?.businessModules) return [];
  return Object.entries(menuData.businessModules).map(([domain, lines]) => {
    const totalMods = Object.values(lines).reduce(
      (sum, prods) => sum + Object.values(prods).reduce((s, mods) => s + mods.length, 0), 0
    );
    return {
      key: `biz-${domain}`,
      label: `${domain} (${totalMods})`,
      children: Object.entries(lines).map(([line, prods]) => {
        const lineTotal = Object.values(prods).reduce((s, mods) => s + mods.length, 0);
        return {
          key: `biz-${domain}-${line}`,
          label: `${line} (${lineTotal})`,
          children: Object.entries(prods).map(([prod, mods]) => ({
            key: `biz-${domain}-${line}-${prod}`,
            label: `${prod} (${mods.length})`,
            // 不再展示模块子级，点击产品级直接浏览该产品下所有文档
          })),
        };
      }),
    };
  });
}

/** 构建部门知识子菜单（从数据库部门树，含文档计数，key含部门ID用于精确过滤） */
function buildDeptChildren(deptTree) {
  if (!deptTree || deptTree.length === 0) return [];
  return deptTree.map((l1) => {
    const l1Total = l1.doc_count || 0;
    let totalUnderL1 = l1Total;
    l1.children?.forEach(l2 => {
      totalUnderL1 += l2.doc_count || 0;
      l2.children?.forEach(l3 => { totalUnderL1 += l3.doc_count || 0; });
    });

    return {
      key: `dept-${l1.id}-${l1.name}`,
      label: `${l1.name} (${totalUnderL1})`,
      icon: <TeamOutlined />,
      children: (l1.children || []).map((l2) => {
        const l2Total = l2.doc_count || 0;
        let totalUnderL2 = l2Total;
        l2.children?.forEach(l3 => { totalUnderL2 += l3.doc_count || 0; });

        const l3Children = (l2.children || []).filter(l3 => l3.name && l3.name !== '未分类');
        if (l3Children.length > 0) {
          return {
            key: `dept-${l1.id}-${l2.name}`,
            label: `${l2.name} (${totalUnderL2})`,
            children: [
              {
                key: `dept-browse-${l2.id}-${l2.name}`,
                label: `📋 全部文档 (${totalUnderL2})`,
                icon: <FolderOpenOutlined />,
              },
              ...l3Children.map((l3) => ({
                key: `dept-browse-${l3.id}-${l3.name}`,
                label: `${l3.name} (${l3.doc_count || 0})`,
              })),
            ],
          };
        }
        return {
          key: `dept-browse-${l2.id}-${l2.name}`,
          label: `${l2.name} (${totalUnderL2})`,
        };
      }),
    };
  });
}

/** 构建 FAQ 子菜单（按部门分组，点击部门在中间面板展示列表） */
function buildFaqChildren(faqs) {
  if (!faqs || faqs.length === 0) return [];
  const grouped = {};
  faqs.forEach(faq => {
    const dept = faq.dept || '其他';
    if (!grouped[dept]) grouped[dept] = [];
    grouped[dept].push(faq);
  });
  return Object.entries(grouped).map(([dept, items]) => ({
    key: `faq-dept-${dept}`,
    label: `${dept} (${items.length})`,
    icon: <QuestionCircleOutlined />,
  }));
}

function LeftSidebar({ selectedNav, onNavChange, collapsed, onToggleCollapse, userRole }) {
  const [menuData, setMenuData] = useState(null);
  const [deptTree, setDeptTree] = useState([]);
  const [faqs, setFaqs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      authFetch('/api/menu').then(r => r.json()),
      authFetch('/api/faq').then(r => r.json()),
      authFetch('/api/departments/tree').then(r => r.json()).catch(() => ({ tree: [] })),
    ]).then(([menu, faqData, deptData]) => {
      setMenuData(menu);
      setFaqs(faqData?.faqs || []);
      setDeptTree(deptData?.tree || []);
      setLoading(false);
    }).catch(() => {
      setMenuData({ productModules: {}, businessModules: {}, deptKnowledge: {} });
      setDeptTree([]);
      setLoading(false);
    });
  }, []);

  const allMenuItems = React.useMemo(() => {
    if (!menuData) return [];
    return [
      { key: 'all', label: '全部知识', icon: <FolderOpenOutlined /> },
      {
        key: 'dept-knowledge',
        label: '部门知识',
        icon: <TeamOutlined />,
        children: buildDeptChildren(deptTree),
      },
      {
        key: 'business-modules',
        label: '业务模块',
        icon: <ApartmentOutlined />,
        children: buildBizChildren(menuData),
      },
      {
        key: 'product-modules',
        label: '产品模块',
        icon: <AppstoreOutlined />,
        children: buildProductChildren(menuData),
      },
      { key: 'reports', label: '报表数据', icon: <BarChartOutlined /> },
      { key: 'ticket', label: '工单知识', icon: <FileTextOutlined /> },
      {
        key: 'faq',
        label: `FAQ库 (${faqs.length})`,
        icon: <QuestionCircleOutlined />,
        children: buildFaqChildren(faqs),
      },
      { type: 'divider' },
      {
        key: 'system-admin',
        label: '系统管理',
        icon: <SettingOutlined />,
        children: getVisibleModules(userRole).map(m => ({
          key: m.key,
          label: m.title,
          icon: m.icon,
        })),
      },
    ];
  }, [menuData, faqs, deptTree, userRole]);

  const handleClick = ({ key }) => {
    onNavChange(key);
  };

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

      {/* 菜单 */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin />
          </div>
        ) : (
          <Menu
            mode="inline"
            inlineCollapsed={collapsed}
            selectedKeys={[selectedNav]}
            onClick={handleClick}
            items={allMenuItems}
            style={{ background: 'transparent', borderRight: 'none', paddingTop: 4 }}
          />
        )}
      </div>
    </div>
  );
}

export default LeftSidebar;