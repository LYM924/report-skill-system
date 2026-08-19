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
import { Menu, Button, Spin } from 'antd';
import {
  FolderOpenOutlined, AppstoreOutlined, ApartmentOutlined,
  FileTextOutlined, TeamOutlined, QuestionCircleOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, BarChartOutlined,
} from '@ant-design/icons';

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

/** 构建业务模块子菜单 */
function buildBizChildren(menuData) {
  if (!menuData?.businessModules) return [];
  return Object.entries(menuData.businessModules).map(([domain, lines]) => {
    const totalMods = Object.values(lines).reduce(
      (sum, prods) => sum + Object.values(prods).reduce((s, mods) => s + mods.length, 0), 0
    );
    return {
      key: `biz-${domain}`,
      label: `${domain} (${totalMods})`,
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

/** 构建部门知识子菜单 */
function buildDeptChildren(menuData) {
  if (!menuData?.deptKnowledge) return [];
  return Object.entries(menuData.deptKnowledge).map(([d1, d2s]) => {
    const totalD1 = Object.values(d2s).reduce(
      (sum, d3s) => sum + Object.values(d3s).reduce((s, mods) => s + mods.length, 0), 0
    );
    return {
      key: `dept-${d1}`,
      label: `${d1} (${totalD1})`,
      children: Object.entries(d2s).map(([d2, d3s]) => {
        const totalD2 = Object.values(d3s).reduce((s, mods) => s + mods.length, 0);
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

function LeftSidebar({ selectedNav, onNavChange, collapsed, onToggleCollapse }) {
  const [menuData, setMenuData] = useState(null);
  const [faqs, setFaqs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/menu').then(r => r.json()),
      fetch('/api/faq').then(r => r.json()),
    ]).then(([menu, faqData]) => {
      setMenuData(menu);
      setFaqs(faqData?.faqs || []);
      setLoading(false);
    }).catch(() => {
      setMenuData({ productModules: {}, businessModules: {}, deptKnowledge: {} });
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
        children: buildDeptChildren(menuData),
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
    ];
  }, [menuData, faqs]);

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