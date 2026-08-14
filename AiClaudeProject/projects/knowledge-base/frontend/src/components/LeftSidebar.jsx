/**
 * LeftSidebar.jsx - 左侧导航栏
 *
 * 扁平导航分类：
 * 知识分类、全部知识、产品模块、业务模块、工单知识、部门知识、FAQ库、工单沉淀
 */

import React, { useState } from 'react';
import { Typography } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { navCategories, deptSubCategories } from '../mock/data';

const { Text } = Typography;

// Font Awesome 图标映射（用 unicode/emoji 简单模拟）
const iconMap = {
  FolderOpenOutlined: '🏠',
  AppstoreOutlined: '📋',
  ApartmentOutlined: '🔷',
  FileTextOutlined: '🎫',
  TeamOutlined: '👥',
  QuestionCircleOutlined: '❓',
  BugOutlined: '🗄️',
};

function LeftSidebar({ selectedNav, onNavChange }) {
  const [activeNav, setActiveNav] = useState('dept');
  const [activeSub, setActiveSub] = useState(null);

  const handleNavClick = (key) => {
    setActiveNav(key);
    if (key !== 'dept') setActiveSub(null);
    onNavChange && onNavChange(key);
  };

  const handleSubClick = (key) => {
    setActiveSub(key);
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '12px 8px' }}>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {navCategories.map(cat => {
          const isActive = activeNav === cat.key;
          const isDept = cat.key === 'dept';
          return (
            <li key={cat.key} style={{ marginBottom: 2 }}>
              <div
                onClick={() => handleNavClick(cat.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                  background: isActive ? 'rgba(13,148,136,0.08)' : 'transparent',
                  color: isActive ? '#0D9488' : '#334155',
                  fontWeight: isActive ? 600 : 400,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = '#e2e8f0'; }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ width: 24, textAlign: 'center', fontSize: 14 }}>{iconMap[cat.icon] || '📄'}</span>
                <span style={{ flex: 1, fontSize: 14 }}>{cat.label}</span>
                <span style={{ fontSize: 11, color: '#999' }}>{cat.count}</span>
                <RightOutlined style={{ fontSize: 10, color: '#ccc' }} />
              </div>
              {/* 部门知识展开子分类 */}
              {isDept && isActive && (
                <ul style={{ listStyle: 'none', padding: '4px 0 4px 32px', margin: 0 }}>
                  {deptSubCategories.map(sub => (
                    <li
                      key={sub.key}
                      onClick={() => handleSubClick(sub.key)}
                      style={{
                        padding: '7px 12px', borderRadius: 6, cursor: 'pointer',
                        fontSize: 13,
                        background: activeSub === sub.key ? 'rgba(13,148,136,0.08)' : 'transparent',
                        color: activeSub === sub.key ? '#0D9488' : '#475569',
                        fontWeight: activeSub === sub.key ? 600 : 400,
                        display: 'flex', justifyContent: 'space-between',
                        marginBottom: 1,
                      }}
                      onMouseEnter={e => { if (activeSub !== sub.key) e.currentTarget.style.background = '#e2e8f0'; }}
                      onMouseLeave={e => { if (activeSub !== sub.key) e.currentTarget.style.background = 'transparent'; }}
                    >
                      <span>{sub.label}</span>
                      <span style={{ fontSize: 11, color: '#999' }}>{sub.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default LeftSidebar;