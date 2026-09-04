/**
 * TopNav.jsx - 顶部全局导航栏
 *
 * 标题 + 导航 Tab + 深色模式切换 + 用户信息（登录/登出）
 * 支持 Confluence SSO 登录（os_destination 回调 + 窗口焦点检测 + 用户名确认）
 *
 * SSO 流程：
 * 1. 页面加载 → 后端代理检测 Confluence 会话（同域部署时自动登录）
 * 2. 点击 SSO → 新标签页打开 Confluence（带 os_destination 回调）
 * 3a. 同域部署：Confluence 登录后自动跳回回调页 → 自动完成登录
 * 3b. 跨域部署：用户手动回到 KB → 焦点事件触发 → 提示确认用户名 → 快捷登录
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Space, Badge, Avatar, Dropdown, Modal, Form, Input, Divider, message } from 'antd';
import {
  BellOutlined, UserOutlined, BookOutlined,
  RobotOutlined, SearchOutlined, BarChartOutlined, FolderAddOutlined,
  SunOutlined, MoonOutlined, LoginOutlined, LogoutOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import { login, clearToken, isAuthed, getSSOStatus, checkConfluenceSession, ssoConfluenceLogin, notifyAuthChanged, authFetch } from '../api';

const baseMenuItems = [
  { key: 'search', label: '文档搜索', icon: <SearchOutlined /> },
  { key: 'stats', label: '问答统计', icon: <BarChartOutlined /> },
  { key: 'manage', label: '知识管理', icon: <FolderAddOutlined />, role: 'admin' },
  { key: 'learning', label: '学习中心', icon: <BookOutlined />, role: 'admin' },
  { key: 'ai', label: 'AI 问答', icon: <RobotOutlined /> },
];

function TopNav({ onGoHome, isDark, onToggleDark, topTab, onTabChange }) {
  const [authed, setAuthed] = useState(isAuthed());
  const [loginOpen, setLoginOpen] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [ssoAvailable, setSsoAvailable] = useState(false);
  const [confluenceUrl, setConfluenceUrl] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [userRole, setUserRole] = useState('user');
  const ssoCheckedRef = useRef(false);

  // 获取当前用户角色
  useEffect(() => {
    authFetch('/api/auth/me').then(r => r.ok ? r.json() : null).then(d => {
      if (d?.role) setUserRole(d.role);
    }).catch(() => {});
  }, [authed]);

  // 根据角色过滤菜单项
  const menuItems = baseMenuItems.filter(item => !item.role || item.role === 'admin' && userRole === 'admin');

  // SSO 状态：0=初始, 1=已打开新标签页等待用户返回, 2=用户名确认
  const [ssoStep, setSsoStep] = useState(0);
  const [ssoUsername, setSsoUsername] = useState('');
  const [ssoLoading, setSsoLoading] = useState(false);
  const ssoTabOpenedRef = useRef(false);  // 标记是否已打开 Confluence 新标签页

  const [form] = Form.useForm();

  // 401 全局事件 → 弹出登录框
  useEffect(() => {
    const handler = () => {
      setAuthed(false);
      setLoginOpen(true);
      setSsoStep(0);
    };
    window.addEventListener('kb-auth-required', handler);
    return () => window.removeEventListener('kb-auth-required', handler);
  }, []);

  // 监听 BroadcastChannel：回调页（同域部署）登录成功后通知
  useEffect(() => {
    let bc;
    try {
      bc = new BroadcastChannel('kb-auth');
      bc.onmessage = (event) => {
        if (event.data === 'auth-changed' && isAuthed()) {
          setAuthed(true);
          setLoginOpen(false);
          setSsoStep(0);
          ssoTabOpenedRef.current = false;
          fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('kb_token')}` },
          }).then(r => r.ok ? r.json() : null).then(d => {
            if (d?.user) setDisplayName(d.user);
          });
          notifyAuthChanged();
          message.success('SSO 登录成功');
        }
      };
    } catch (e) { /* 浏览器不支持 */ }
    return () => { try { bc?.close(); } catch {} };
  }, []);

  // 监听 localStorage 变化（回调页写入 token 触发，跨 tab 生效）
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'kb_token' && e.newValue && !isAuthed()) {
        // 另一个 tab 写入了新 token（回调页），但当前页还没更新
        // storage 事件只在其他 tab 触发，当前 tab 不触发
      }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  // 监听窗口焦点：用户从 Confluence 回来时触发 SSO 检测
  useEffect(() => {
    const handleFocus = async () => {
      // 只在 SSO 新标签页已打开且用户未登录时触发
      if (!ssoTabOpenedRef.current || isAuthed()) return;

      // 先尝试代理检测（同域部署时自动完成）
      const result = await checkConfluenceSession();
      if (result.ok && result.username) {
        const loginResult = await ssoConfluenceLogin({
          username: result.username,
          display_name: result.display_name,
          email: result.email,
        });
        if (loginResult.ok) {
          setAuthed(true);
          setDisplayName(result.display_name || result.username);
          setLoginOpen(false);
          setSsoStep(0);
          ssoTabOpenedRef.current = false;
          notifyAuthChanged();
          message.success(`SSO 登录成功，欢迎 ${result.display_name || result.username}`);
          return;
        }
      }

      // 代理失败（跨域）→ 弹出用户名确认
      if (loginOpen) {
        setSsoStep(2);
        setSsoUsername('');
      } else {
        setLoginOpen(true);
        setSsoStep(2);
        setSsoUsername('');
      }
      ssoTabOpenedRef.current = false;
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [loginOpen]);

  // 页面加载 → 自动检测 SSO（同域部署时无感登录）
  useEffect(() => {
    if (authed || ssoCheckedRef.current) return;
    ssoCheckedRef.current = true;

    (async () => {
      if (isAuthed()) {
        try {
          const resp = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('kb_token')}` },
          });
          if (resp.ok) {
            const data = await resp.json();
            if (data.user) setDisplayName(data.user);
            setAuthed(true);
            return;
          }
        } catch (e) { /* ignore */ }
      }

      const status = await getSSOStatus();
      if (!status.enabled) {
        setSsoAvailable(false);
        return;
      }
      setConfluenceUrl(status.confluence_url);
      setSsoAvailable(true);

      const result = await checkConfluenceSession();
      if (result.ok && result.username) {
        const loginResult = await ssoConfluenceLogin({
          username: result.username,
          display_name: result.display_name,
          email: result.email,
        });
        if (loginResult.ok) {
          setAuthed(true);
          setDisplayName(result.display_name || result.username);
          message.success(`SSO 自动登录成功，欢迎 ${result.display_name || result.username}`);
          notifyAuthChanged();
        }
      }
    })();
  }, [authed]);

  // ─── 普通登录 ───
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
      setDisplayName(username);
      setLoginOpen(false);
      form.resetFields();
      message.success('登录成功');
      notifyAuthChanged();
    } else {
      message.error(result.error || '登录失败');
    }
  };

  // ─── SSO 登录 ───
  const handleSSOStart = () => {
    if (!confluenceUrl) {
      message.warning('SSO 配置不可用');
      return;
    }
    const callbackUrl = encodeURIComponent(window.location.origin + '/api/auth/sso/confluence-callback');
    const loginUrl = `${confluenceUrl}/login.action?os_destination=${callbackUrl}`;
    window.open(loginUrl, '_blank');
    ssoTabOpenedRef.current = true;
    setSsoStep(1);  // 显示"等待返回"提示
  };

  // SSO 用户名确认登录
  const handleSSOConfirm = async () => {
    if (!ssoUsername.trim()) {
      message.warning('请输入 Confluence 用户名');
      return;
    }
    setSsoLoading(true);
    const result = await ssoConfluenceLogin({
      username: ssoUsername.trim(),
      display_name: ssoUsername.trim(),
    });
    setSsoLoading(false);
    if (result.ok) {
      setAuthed(true);
      setDisplayName(ssoUsername.trim());
      setLoginOpen(false);
      setSsoStep(0);
      setSsoUsername('');
      notifyAuthChanged();
      message.success('SSO 登录成功');
    } else {
      message.error(result.error || 'SSO 登录失败');
    }
  };

  const handleLogout = () => {
    clearToken();
    setAuthed(false);
    setDisplayName('');
    ssoCheckedRef.current = false;
    message.info('已退出登录');
    notifyAuthChanged();
  };

  const userMenu = authed
    ? { items: [{ key: 'logout', label: '退出登录', icon: <LogoutOutlined /> }], onClick: ({ key }) => { if (key === 'logout') handleLogout(); } }
    : { items: [{ key: 'login', label: '登录', icon: <LoginOutlined /> }], onClick: ({ key }) => { if (key === 'login') { setSsoStep(0); setLoginOpen(true); } } };

  // ─── SSO 面板 ───
  const renderSSOPanel = () => {
    if (!ssoAvailable) return null;

    // 步骤 0：初始 — SSO 按钮
    if (ssoStep === 0) {
      return (
        <>
          <Button
            block
            icon={<CloudServerOutlined />}
            onClick={handleSSOStart}
            style={{
              height: 44, borderRadius: 8, fontSize: 15,
              background: 'linear-gradient(135deg, #0D9488 0%, #2DD4BF 100%)',
              color: '#fff', border: 'none',
            }}
          >
            Confluence SSO 登录
          </Button>
          <Divider style={{ margin: '16px 0', color: '#999', fontSize: 12 }}>或使用账号密码</Divider>
        </>
      );
    }

    // 步骤 1：已打开新标签页，等待用户返回
    if (ssoStep === 1) {
      return (
        <div style={{
          background: isDark ? '#252525' : '#f0fdfa', borderRadius: 8,
          padding: '16px 18px', marginBottom: 4, border: `1px solid ${isDark ? '#303030' : '#ccfbf1'}`,
        }}>
          <p style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 500, color: isDark ? '#e5e5e5' : '#1a1a2e' }}>
            请在新标签页中完成 Confluence 登录
          </p>
          <p style={{ margin: 0, fontSize: 12, color: isDark ? '#999' : '#606266' }}>
            登录完成后回到此页面，将自动检测登录状态
          </p>
        </div>
      );
    }

    // 步骤 2：用户已返回，代理未成功 → 确认用户名
    if (ssoStep === 2) {
      return (
        <div style={{ padding: '4px 0' }}>
          <div style={{
            background: isDark ? '#252525' : '#fff7ed', borderRadius: 8,
            padding: '12px 16px', marginBottom: 12, border: `1px solid ${isDark ? '#303030' : '#fed7aa'}`,
          }}>
            <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 500, color: isDark ? '#e5e5e5' : '#9a3412' }}>
              Confluence 已登录，请确认用户名
            </p>
            <p style={{ margin: 0, fontSize: 12, color: isDark ? '#999' : '#78716c' }}>
              输入你的 Confluence 用户名即可完成知识库登录
            </p>
          </div>
          <Input
            placeholder="Confluence 用户名"
            value={ssoUsername}
            onChange={e => setSsoUsername(e.target.value)}
            onPressEnter={handleSSOConfirm}
            prefix={<UserOutlined style={{ color: '#0D9488' }} />}
            autoFocus
            style={{ marginBottom: 8, height: 40, borderRadius: 8 }}
          />
          <Button
            type="primary"
            block
            loading={ssoLoading}
            onClick={handleSSOConfirm}
            style={{ height: 40, borderRadius: 8 }}
          >
            确认登录
          </Button>
          <Button type="link" size="small" onClick={() => setSsoStep(0)} style={{ marginTop: 4, padding: 0 }}>
            返回
          </Button>
        </div>
      );
    }
    return null;
  };

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
            <span style={{ fontSize: 13, color: isDark ? '#999' : '#595959' }}>{authed ? (displayName || '已登录') : '未登录'}</span>
          </div>
        </Dropdown>
      </Space>

      {/* 登录弹窗 */}
      <Modal
        title="登录智能知识库"
        open={loginOpen}
        onCancel={() => { setLoginOpen(false); setSsoStep(0); ssoTabOpenedRef.current = false; }}
        footer={null}
        width={400}
      >
        <div style={{ marginTop: 12 }}>
          {renderSSOPanel()}

          {/* SSO 步骤 0 时显示账号密码表单 */}
          {ssoStep === 0 && (
            <Form form={form} layout="vertical">
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input placeholder="用户名" onPressEnter={handleLogin} />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password placeholder="密码" onPressEnter={handleLogin} />
              </Form.Item>
              <Button
                type="primary"
                block
                loading={loggingIn}
                onClick={handleLogin}
                style={{ height: 40, borderRadius: 8, fontSize: 14 }}
              >
                登录
              </Button>
            </Form>
          )}
        </div>
      </Modal>
    </div>
  );
}

export default TopNav;
