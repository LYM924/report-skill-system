/**
 * TopNav.jsx - 顶部全局导航栏
 *
 * 标题 + 导航菜单 + 用户信息
 * 搜索栏已移至中间主区域
 */

import React, { useState } from 'react';
import { Button, Space, Badge, Avatar, Dropdown } from 'antd';
import {
  BellOutlined, UserOutlined, BookOutlined,
  RobotOutlined, SearchOutlined, BarChartOutlined, FolderAddOutlined,
} from '@ant-design/icons';

const menuItems = [
  { key: 'search', label: '文档搜索', icon: <SearchOutlined /> },
  { key: 'stats', label: '问答统计', icon: <BarChartOutlined /> },
  { key: 'manage', label: '知识管理', icon: <FolderAddOutlined /> },
  { key: 'ai', label: 'AI助手', icon: <RobotOutlined /> },
];

function TopNav({ onGoHome }) {
  const [activeMenu, setActiveMenu] = useState('search');

  return (
    <div style={{ display: 'flex', alignItems: 'center', width: '100%', height: 56 }}>
      {/* 左侧标题 Logo */}
      <div style={{
        fontSize: 17, fontWeight: 700, color: '#1a1a2e',
        whiteSpace: 'nowrap', marginRight: 28,
        display: 'flex', alignItems: 'center', gap: 10,
        width: 220, cursor: 'pointer',
      }}
        onClick={onGoHome}
        title="点击回到首页"
      >
        <div style={{
          width: 34, height: 34, borderRadius: 8,
          background: 'linear-gradient(135deg, #0D9488 0%, #2DD4BF 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <BookOutlined style={{ fontSize: 18, color: '#fff' }} />
        </div>
        智能知识库
      </div>

      {/* 导航菜单 */}
      <div style={{ display: 'flex', gap: 2, flex: 1, justifyContent: 'center' }}>
        {menuItems.map(item => (
          <Button
            key={item.key}
            type="text"
            icon={item.icon}
            onClick={() => setActiveMenu(item.key)}
            style={{
              fontSize: 14, height: 36, borderRadius: 6,
              color: activeMenu === item.key ? '#0D9488' : '#595959',
              background: activeMenu === item.key ? 'rgba(13,148,136,0.08)' : 'transparent',
              fontWeight: activeMenu === item.key ? 600 : 'normal',
              padding: '4px 16px',
            }}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {/* 右侧：今日问答 + 通知 + 用户 */}
      <Space size="middle" style={{ flexShrink: 0 }}>
        <span style={{
          background: 'rgba(13,148,136,0.08)', color: '#0D9488',
          padding: '4px 12px', borderRadius: 8, fontSize: 13,
        }}>
          今日问答 128
        </span>
        <Badge count={5} size="small">
          <Button type="text" icon={<BellOutlined style={{ fontSize: 17 }} />} style={{ color: '#595959' }} />
        </Badge>
        <Dropdown menu={{ items: [{ key: 'profile', label: '个人中心' }, { key: 'logout', label: '退出登录' }] }}>
          <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Avatar size={32} icon={<UserOutlined />} style={{ backgroundColor: '#0D9488' }} />
            <span style={{ fontSize: 13, color: '#595959' }}>名称筛选</span>
            <i className="fa fa-caret-down" style={{ fontSize: 12, color: '#999' }} />
          </div>
        </Dropdown>
      </Space>
    </div>
  );
}

export default TopNav;