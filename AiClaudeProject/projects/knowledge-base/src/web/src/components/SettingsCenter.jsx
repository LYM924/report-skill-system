/**
 * SettingsCenter.jsx - 配置中心（AI 大模型配置）
 *
 * 每个登录用户配置自己的模型/API地址/AppKey，保存后搜索的 AI 总结与 AI 问答
 * 将使用本人的配置（互不影响）；未配置时回退服务器默认值。
 */

import React, { useState, useEffect } from 'react';
import { Card, Form, Input, InputNumber, Button, message, Alert, Tag, Typography, Space, Select } from 'antd';
import { SaveOutlined, ThunderboltOutlined, ReloadOutlined } from '@ant-design/icons';
import { authFetch } from '../api';

const { Text, Paragraph } = Typography;

const MODEL_OPTIONS = [
  { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro（推荐）' },
  { value: 'deepseek-v4-flash', label: 'deepseek-v4-flash（快速）' },
  { value: 'deepseek-v4-flash-vision-exp', label: 'deepseek-v4-flash-vision-exp（视觉）' },
];

function SettingsCenter({ isDark }) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [source, setSource] = useState('none');
  const [testResult, setTestResult] = useState(null);

  const loadConfig = async () => {
    const resp = await authFetch('/api/config/ai');
    const data = await resp.json();
    form.setFieldsValue({
      model: data.model || 'deepseek-v4-pro',
      base_url: data.base_url || '',
      api_key: data.api_key_masked || '',
      max_tokens: data.max_tokens || 4096,
    });
    setSource(data.source || 'none');
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const handleSave = async () => {
    const values = form.getFieldsValue();
    if (!values.model) {
      message.warning('请填写模型名');
      return;
    }
    setSaving(true);
    try {
      const resp = await authFetch('/api/config/ai', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        message.error(data.error || `保存失败 (HTTP ${resp.status})`);
      } else {
        message.success('AI 配置已保存，立即生效');
        loadConfig();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    const values = form.getFieldsValue();
    setTesting(true);
    setTestResult(null);
    try {
      const resp = await authFetch('/api/config/ai/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      const data = await resp.json();
      setTestResult(data);
      if (data.ok) message.success('连接成功');
      else message.error('连接失败');
    } finally {
      setTesting(false);
    }
  };

  const sourceTag = {
    user: <Tag color="green">使用我的配置</Tag>,
    env: <Tag color="orange">未配置个人密钥，回退服务器默认</Tag>,
    none: <Tag color="red">未配置（AI 功能不可用）</Tag>,
  }[source] || <Tag>未知</Tag>;

  return (
    <div style={{ width: '100%', maxWidth: 720 }}>
      <Text strong style={{ fontSize: 20, display: 'block', marginBottom: 4, color: isDark ? '#e5e5e5' : '#1e293b' }}>
        配置中心
      </Text>
      <Space size="middle" style={{ marginBottom: 16 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>AI 大模型配置（本人独立生效）</Text>
        {sourceTag}
      </Space>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16, fontSize: 13 }}
        message="每个登录用户保存自己的模型配置与 AppKey，AI 总结/问答将使用本人配置调用，互不影响。AppKey 加密存储、界面脱敏显示。"
      />

      <Card style={{ borderRadius: 12 }}>
        <Form form={form} layout="vertical">
          <Form.Item name="model" label="模型名称">
            <Select
              options={MODEL_OPTIONS}
              showSearch
              placeholder="选择或输入模型名"
              style={{ maxWidth: 360 }}
            />
          </Form.Item>
          <Form.Item name="base_url" label="API 地址（Base URL）">
            <Input placeholder="https://api.deepseek.com/anthropic（留空则用服务器默认）" />
          </Form.Item>
          <Form.Item name="api_key" label="AppKey / API Key" extra="留空保存 = 保留已保存的密钥">
            <Input.Password placeholder="sk-..." autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="max_tokens" label="单次回复最大 Token">
            <InputNumber min={256} max={32768} step={256} style={{ width: 200 }} />
          </Form.Item>
          <Space>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
              保存配置
            </Button>
            <Button icon={<ThunderboltOutlined />} onClick={handleTest} loading={testing}>
              测试连接
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadConfig}>刷新</Button>
          </Space>
        </Form>

        {testResult && (
          <Alert
            style={{ marginTop: 16, fontSize: 13 }}
            type={testResult.ok ? 'success' : 'error'}
            showIcon
            message={testResult.ok ? testResult.message : `连接失败: ${testResult.error}`}
          />
        )}
      </Card>

      <Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
        说明：配置保存后立即生效（无需重启服务）。AI 智能总结、AI 问答、深度分析均使用本人的配置。
        服务器管理员可在 .env 中配置 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN 作为未配置用户的默认回退。
      </Paragraph>
    </div>
  );
}

export default SettingsCenter;
