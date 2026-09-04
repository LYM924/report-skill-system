/**
 * SystemConfig.jsx - 系统配置管理
 *
 * 管理全局配置项：SSO 开关、Confluence 地址、维护模式、搜索参数、安全策略等。
 * 配置存储在 system_settings 表，优先级：DB > 环境变量 > 默认值。
 * 仅管理员可见。
 */

import React, { useState, useEffect } from 'react';
import { Card, Form, Input, InputNumber, Switch, Button, message, Alert, Spin, Divider, Typography, Space } from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';

const { Text } = Typography;

// 配置分组定义
const CONFIG_GROUPS = [
  {
    key: 'sso',
    title: 'SSO 认证',
    items: [
      { key: 'sso_enabled', label: 'SSO 开关', type: 'bool', description: '启用/禁用 Confluence SSO 登录' },
      { key: 'confluence_base_url', label: 'Confluence 地址', type: 'string', description: 'Confluence 服务地址，修改后需重启生效' },
    ],
  },
  {
    key: 'general',
    title: '通用设置',
    items: [
      { key: 'maintenance_mode', label: '维护模式', type: 'bool', description: '开启后前端显示维护提示，用户无法使用' },
      { key: 'default_dept', label: '默认部门', type: 'string', description: 'FAQ/文档上传时预填的默认部门' },
      { key: 'default_module', label: '默认模块', type: 'string', description: 'FAQ/文档上传时预填的默认模块' },
    ],
  },
  {
    key: 'search',
    title: '搜索配置',
    items: [
      { key: 'search_result_limit', label: '搜索结果条数', type: 'int', description: '每次搜索返回的最大结果数' },
      { key: 'ai_env_fallback', label: 'AI 共享密钥回退', type: 'bool', description: '开启后，未配置 AI 密钥的用户可使用服务器共享密钥调用 AI 总结；关闭则用户必须自行在配置中心配密钥' },
    ],
  },
  {
    key: 'security',
    title: '安全策略',
    items: [
      { key: 'password_min_length', label: '密码最小长度', type: 'int', description: '创建用户/重置密码时的密码长度要求' },
    ],
  },
];

function SystemConfig() {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changedKeys, setChangedKeys] = useState(new Set());

  const loadSettings = async () => {
    setLoading(true);
    try {
      const resp = await authFetch('/api/settings');
      const data = await resp.json();
      const map = {};
      (data.settings || []).forEach(s => { map[s.key] = s.value; });
      setSettings(map);
      setChangedKeys(new Set());
    } catch (e) {
      message.error('加载配置失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSettings(); }, []);

  const handleChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: String(value) }));
    setChangedKeys(prev => new Set(prev).add(key));
  };

  const handleSave = async () => {
    if (changedKeys.size === 0) {
      message.info('没有变更');
      return;
    }
    setSaving(true);
    try {
      const updates = {};
      changedKeys.forEach(key => { updates[key] = settings[key]; });
      const resp = await authFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: updates }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        message.error(data.error || '保存失败');
      } else {
        message.success(`已保存 ${changedKeys.size} 项配置`);
        setChangedKeys(new Set());
      }
    } catch (e) {
      message.error('保存失败: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;

  const renderField = (item) => {
    const value = settings[item.key];
    switch (item.type) {
      case 'bool':
        return (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0' }}>
            <div>
              <Text strong>{item.label}</Text>
              <div><Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text></div>
            </div>
            <Switch
              checked={value === '1' || value === 'true'}
              onChange={(checked) => handleChange(item.key, checked ? '1' : '0')}
            />
          </div>
        );
      case 'int':
        return (
          <div style={{ marginBottom: 16 }}>
            <Text strong>{item.label}</Text>
            <div><Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text></div>
            <InputNumber
              value={value ? parseInt(value) : 0}
              onChange={(v) => handleChange(item.key, v)}
              style={{ width: 200, marginTop: 4 }}
              min={1}
            />
          </div>
        );
      default: // string
        return (
          <div style={{ marginBottom: 16 }}>
            <Text strong>{item.label}</Text>
            <div><Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text></div>
            <Input
              value={value || ''}
              onChange={(e) => handleChange(item.key, e.target.value)}
              style={{ marginTop: 4, maxWidth: 400 }}
            />
          </div>
        );
    }
  };

  return (
    <AdminShell
      title="系统配置"
      description="管理全局配置项，修改后即时生效（部分需重启）"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSettings}>刷新</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving} disabled={changedKeys.size === 0}>
            保存变更{changedKeys.size > 0 ? ` (${changedKeys.size})` : ''}
          </Button>
        </Space>
      }
    >
      <Alert type="info" showIcon style={{ marginBottom: 16, fontSize: 13 }}
        message="配置优先级：数据库设置 > 环境变量 > 默认值。修改后即时生效，SSO 和 Confluence 地址变更可能需重启服务。"
      />

      {CONFIG_GROUPS.map(group => (
        <Card key={group.key} title={group.title} style={{ borderRadius: 12, marginBottom: 16 }}>
          {group.items.map(item => (
            <React.Fragment key={item.key}>
              {renderField(item)}
            </React.Fragment>
          ))}
        </Card>
      ))}
    </AdminShell>
  );
}

export default SystemConfig;
