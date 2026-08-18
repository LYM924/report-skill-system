/**
 * App.jsx - 智能知识库中台主页面
 *
 * 布局：顶部导航 + 左侧导航 + 中间主面板 + 右侧信息看板
 * 核心定位：企业AI赋能的知识沉淀平台
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Layout, ConfigProvider, Modal } from 'antd';
import { SearchOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import TopNav from './components/TopNav';
import LeftSidebar from './components/LeftSidebar';
import CenterContent from './components/CenterContent';
import RightPanel from './components/RightPanel';
import './App.css';

const { Header, Sider, Content } = Layout;

function App() {
  const [selectedNav, setSelectedNav] = useState('all');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // 搜索状态（提升到 App 层，供 CenterContent 和 RightPanel 联动）
  const [searchResults, setSearchResults] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null); // 右侧面板选中的文档
  const [searchScope, setSearchScope] = useState('all'); // 左侧栏联动搜索范围

  // 右侧面板宽度（响应式：占可用宽度 22%，最小 280px，最大 500px）
  const calcRightWidth = useCallback(() => {
    const leftW = sidebarCollapsed ? 60 : 240;
    const available = window.innerWidth - leftW;
    return Math.max(280, Math.min(500, Math.round(available * 0.22)));
  }, [sidebarCollapsed]);

  const [rightWidth, setRightWidth] = useState(calcRightWidth);
  const [userResized, setUserResized] = useState(false); // 用户手动拖拽后不再自动缩放
  const resizing = useRef(false);

  // 窗口缩放时自适应
  useEffect(() => {
    const handleResize = () => {
      if (!userResized) {
        setRightWidth(calcRightWidth());
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [userResized, calcRightWidth]);

  // 左侧栏折叠/展开时调整
  useEffect(() => {
    if (!userResized) {
      setRightWidth(calcRightWidth());
    }
  }, [sidebarCollapsed, userResized, calcRightWidth]);

  // 快捷键面板
  const [shortcutsVisible, setShortcutsVisible] = useState(false);

  // 全局键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ctrl/Cmd + K: 聚焦搜索框
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const input = document.querySelector('input[placeholder*="搜索"]');
        if (input) input.focus();
      }
      // ?: 显示快捷键面板
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        setShortcutsVisible(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleResizeStart = useCallback((e) => {
    e.preventDefault();
    resizing.current = true;
    setUserResized(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!resizing.current) return;
      const newWidth = window.innerWidth - e.clientX;
      setRightWidth(Math.max(280, Math.min(600, newWidth)));
    };
    const handleMouseUp = () => {
      resizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // 左侧栏点击 → 更新筛选范围
  const handleNavChange = (key) => {
    setSelectedNav(key);
    // 映射到搜索范围
    const scopeMap = {
      all: 'all', product: 'doc', business: 'doc',
      ticket: 'doc', faq: 'faq', ticket_deposit: 'doc',
      szcw: 'dept', myp: 'dept', da: 'dept', szh: 'dept',
    };
    setSearchScope(scopeMap[key] || 'all');
  };

  // 点击 logo 回到首页
  const handleGoHome = () => {
    if (searchResults) {
      setSearchResults(null);
      setSelectedDoc(null);
    } else {
      window.location.reload();
    }
  };

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#0D9488',
          borderRadius: 8,
          colorBgContainer: '#ffffff',
          colorBgLayout: '#f8fafc',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <Layout style={{ height: '100vh', overflow: 'hidden' }}>
        {/* ===== 顶部全局导航 ===== */}
        <Header style={{
          height: 60, lineHeight: '60px', padding: '0 16px',
          background: '#fff', borderBottom: '1px solid #e2e8f0',
          display: 'flex', alignItems: 'center', zIndex: 100,
          flexShrink: 0,
        }}>
          <TopNav onGoHome={handleGoHome} />
        </Header>

        <Layout style={{ flex: 1, overflow: 'hidden' }}>
          {/* ===== 左侧导航栏 ===== */}
          <Sider
            width={240}
            collapsedWidth={60}
            collapsible
            collapsed={sidebarCollapsed}
            onCollapse={setSidebarCollapsed}
            trigger={null}
            style={{ background: '#f8fafa', borderRight: '1px solid #e2e8f0', overflow: 'hidden' }}
          >
            <LeftSidebar
              selectedNav={selectedNav}
              onNavChange={handleNavChange}
              collapsed={sidebarCollapsed}
              onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
            />
          </Sider>

          {/* ===== 中间主面板 ===== */}
          <Content style={{ background: '#f8fafc', overflow: 'auto', padding: '16px 20px' }}>
            <CenterContent
              searchResults={searchResults}
              onSearchResultsChange={setSearchResults}
              onSelectDoc={setSelectedDoc}
              searchScope={searchScope}
              onSearchScopeChange={setSearchScope}
            />
          </Content>

          {/* ===== 右侧信息看板 ===== */}
          <div style={{ position: 'relative', flexShrink: 0, width: rightWidth }}>
            {/* 拖拽手柄 */}
            <div
              onMouseDown={handleResizeStart}
              style={{
                width: 6, cursor: 'col-resize',
                background: 'transparent',
                transition: 'background 0.15s',
                position: 'absolute', left: -3, top: 0, bottom: 0, zIndex: 10,
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(13,148,136,0.15)'}
              onMouseLeave={e => { if (!resizing.current) e.currentTarget.style.background = 'transparent'; }}
            />
            <div style={{ width: '100%', height: '100%', background: '#fff', borderLeft: '1px solid #e2e8f0', overflow: 'hidden' }}>
              <RightPanel
                selectedDoc={selectedDoc}
                onClearDoc={() => setSelectedDoc(null)}
              />
            </div>
          </div>
        </Layout>
      </Layout>
      {/* 快捷键面板 */}
      <Modal
        title="键盘快捷键"
        open={shortcutsVisible}
        onCancel={() => setShortcutsVisible(false)}
        footer={null}
        width={360}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#334155' }}>聚焦搜索框</span>
            <kbd style={{ background: '#f1f5f9', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontFamily: 'monospace', border: '1px solid #e2e8f0' }}>Ctrl + K</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#334155' }}>清除搜索结果</span>
            <kbd style={{ background: '#f1f5f9', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontFamily: 'monospace', border: '1px solid #e2e8f0' }}>Esc</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#334155' }}>显示快捷键</span>
            <kbd style={{ background: '#f1f5f9', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontFamily: 'monospace', border: '1px solid #e2e8f0' }}>?</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#334155' }}>搜索</span>
            <kbd style={{ background: '#f1f5f9', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontFamily: 'monospace', border: '1px solid #e2e8f0' }}>Enter</kbd>
          </div>
        </div>
      </Modal>
    </ConfigProvider>
  );
}

export default App;