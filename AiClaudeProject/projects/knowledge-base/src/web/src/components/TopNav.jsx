/**
 * TopNav.jsx - 顶部全局导航栏
 *
 * 标题 + 导航 Tab + 深色模式切换 + 用户信息（登录/登出）
 */

import React, { useState, useEffect } from 'react';
import { Button, Space, Badge, Avatar, Dropdown, Modal, Form, Input, message } from 'antd';
import {
  BellOutlined, UserOutlined, BookOutlined,
  RobotOutlined, SearchOutlined, BarChartOutlined, FolderAddOutlined,
  SunOutlined, MoonOutlined, LoginOutlined, LogoutOutlined,
} from '@ant-design/icons';
import { login, clearToken, isAuthed } from '../api';

const menuItems = [
  { key: 'search', label: '文档搜索', icon: <SearchOutlined /> },
  { key: 'stats', label: '问答统计', icon: <BarChartOutlined /> },
  { key: 'manage', label: '知识管理', icon: <FolderAddOutlined /> },
  { key: 'ai', label: 'AI 问答', icon: <RobotOutlined /> },
];

function TopNav({ onGoHome, isDark, onToggleDark, topTab, onTabChange }) {
  const [authed, setAuthed] = useState(isAuthed());
  const [loginOpen, setLoginOpen] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [form] = Form.useForm();

  // 401 全局事件 → 弹出登录框
  useEffect(() => {
    const handler = () => {
      setAuthed(false);
      setLoginOpen(true);
    };
    window.addEventListener('kb-auth-required', handler);
    return () => window.removeEventListener('kb-auth-required', handler);
  }, []);

  const handleLogin = async () => {
    const { username, password } = form.getFieldsValue();
    if (!username || !password) {
      message.warning('请输入用户名和密码');
      return;
    }
    setLoggingIn(true);
    const result = await login(username, password);
    setLoggingIn(false);
    if (result.ok) {
      setAuthed(true);
      setLoginOpen(false);
      form.resetFields();
      message.success('登录成功');
    } else {
      message.error(result.error || '登录失败');
    }
  };

  const handleLogout = () => {
    clearToken();
    setAuthed(false);
    message.info('已退出登录');
  };

  const userMenu = authed
    ? { items: [{ key: 'logout', label: '退出登录', icon: <LogoutOutlined /> }], onClick: ({ key }) => { if (key === 'logout') handleLogout(); } }
    : { items: [{ key: 'login', label: '登录', icon: <LoginOutlined /> }], onClick: ({ key }) => { if (key === 'login') setLoginOpen(true); } };

  return (
    <div style={{ display: 'flex', alignItems: 'center', width: '100%', height: 56 }}>
      {/* 左侧标题 Logo */}
      <div style={{
        fontSize: 17, fontWeight: 700, color: isDark ? '#e5e5e5' : '#1a1a2e',
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

      {/* 导航 Tab */}
      <div style={{ display: 'flex', gap: 2, flex: 1, justifyContent: 'center' }}>
        {menuItems.map(item => (
          <Button
            key={item.key}
            type="text"
            icon={item.icon}
            onClick={() => onTabChange(item.key)}
            style={{
              fontSize: 14, height: 36, borderRadius: 6,
              color: topTab === item.key ? '#0D9488' : (isDark ? '#999' : '#595959'),
              background: topTab === item.key ? 'rgba(13,148,136,0.08)' : 'transparent',
              fontWeight: topTab === item.key ? 600 : 'normal',
              padding: '4px 16px',
            }}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {/* 右侧：深色模式 + 通知 + 用户 */}
      <Space size="middle" style={{ flexShrink: 0 }}>
        <Button
          type="text"
          icon={isDark ? <SunOutlined style={{ fontSize: 17 }} /> : <MoonOutlined style={{ fontSize: 17 }} />}
          onClick={onToggleDark}
          title={isDark ? '切换亮色模式' : '切换深色模式'}
          style={{ color: isDark ? '#999' : '#595959' }}
        />
        <span style={{
          background: 'rgba(13,148,136,0.08)', color: '#0D9488',
          padding: '4px 12px', borderRadius: 8, fontSize: 13,
        }}>
          今日问答 128
        </span>
        <Badge count={5} size="small">
          <Button type="text" icon={<BellOutlined style={{ fontSize: 17 }} />} style={{ color: isDark ? '#999' : '#595959' }} />
        </Badge>
        <Dropdown menu={userMenu}>
          <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Avatar size={32} icon={<UserOutlined />} style={{ backgroundColor: authed ? '#0D9488' : '#8c8c8c' }} />
            <span style={{ fontSize: 13, color: isDark ? '#999' : '#595959' }}>{authed ? '管理员' : '未登录'}</span>
          </div>
        </Dropdown>
      </Space>

      {/* 登录弹窗 */}
      <Modal
        title="登录智能知识库"
        open={loginOpen}
        onOk={handleLogin}
        onCancel={() => setLoginOpen(false)}
        confirmLoading={loggingIn}
        okText="登录"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="用户名" onPressEnter={handleLogin} />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="密码" onPressEnter={handleLogin} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default TopNav;
