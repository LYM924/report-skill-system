/**
 * App.jsx - 智能知识库中台主页面
 *
 * 布局：顶部导航 + 左侧导航 + 中间主面板 + 右侧信息看板
 * 核心定位：企业AI赋能的知识沉淀平台
 */

import React, { useState } from 'react';
import { Layout, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import TopNav from './components/TopNav';
import LeftSidebar from './components/LeftSidebar';
import CenterContent from './components/CenterContent';
import RightPanel from './components/RightPanel';
import './App.css';

const { Header, Sider, Content } = Layout;

function App() {
  const [selectedNav, setSelectedNav] = useState('dept');

  // 搜索状态（提升到 App 层，供 CenterContent 和 RightPanel 联动）
  const [searchResults, setSearchResults] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null); // 右侧面板选中的文档

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
          <Sider width={240} style={{ background: '#f8fafa', borderRight: '1px solid #e2e8f0', overflow: 'hidden' }}>
            <LeftSidebar selectedNav={selectedNav} onNavChange={setSelectedNav} />
          </Sider>

          {/* ===== 中间主面板 ===== */}
          <Content style={{ background: '#f8fafc', overflow: 'auto', padding: '16px 20px' }}>
            <CenterContent
              searchResults={searchResults}
              onSearchResultsChange={setSearchResults}
              onSelectDoc={setSelectedDoc}
            />
          </Content>

          {/* ===== 右侧信息看板 ===== */}
          <Sider width={320} style={{ background: '#fff', borderLeft: '1px solid #e2e8f0', overflow: 'hidden' }}>
            <RightPanel
              selectedDoc={selectedDoc}
              onClearDoc={() => setSelectedDoc(null)}
            />
          </Sider>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

export default App;