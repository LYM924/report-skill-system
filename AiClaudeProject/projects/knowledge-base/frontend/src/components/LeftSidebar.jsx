/**
 * LeftSidebar.jsx - 左侧导航栏
 *
 * 可折叠侧栏 + 筛选联动：
 * - 点击分类 → 更新搜索范围 + 高亮
 * - 部门知识展开子分类（数智财务、免疫规划等）
 * - 折叠按钮切换图标/文字模式
 */

import React from 'react';
import { Menu, Button } from 'antd';
import {
  FolderOpenOutlined, AppstoreOutlined, ApartmentOutlined,
  FileTextOutlined, TeamOutlined, QuestionCircleOutlined,
  BugOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from '@ant-design/icons';

const menuItems = [
  { key: 'all', label: '全部知识', icon: <FolderOpenOutlined /> },
  { key: 'product', label: '产品模块', icon: <AppstoreOutlined /> },
  { key: 'business', label: '业务模块', icon: <ApartmentOutlined /> },
  { key: 'ticket', label: '工单知识', icon: <FileTextOutlined /> },
  {
    key: 'dept', label: '部门知识', icon: <TeamOutlined />,
    children: [
      { key: 'szcw', label: '数智财务' },
      { key: 'myp', label: '免疫规划' },
      { key: 'da', label: '电子档案' },
      { key: 'szh', label: '数字化支撑' },
    ],
  },
  { key: 'faq', label: 'FAQ库', icon: <QuestionCircleOutlined /> },
  { key: 'ticket_deposit', label: '工单沉淀', icon: <BugOutlined /> },
];

function LeftSidebar({ selectedNav, onNavChange, collapsed, onToggleCollapse }) {
  const handleClick = ({ key }) => {
    onNavChange(key);
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 折叠按钮 */}
      <div style={{
        padding: collapsed ? '12px 0' : '12px 12px',
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

      {/* 导航菜单 */}
      <Menu
        mode="inline"
        inlineCollapsed={collapsed}
        selectedKeys={[selectedNav]}
        onClick={handleClick}
        items={menuItems}
        style={{
          background: 'transparent',
          borderRight: 'none',
          flex: 1,
          paddingTop: 4,
        }}
      />
    </div>
  );
}

export default LeftSidebar;