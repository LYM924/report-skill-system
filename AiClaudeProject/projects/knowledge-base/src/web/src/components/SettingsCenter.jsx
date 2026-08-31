/**
 * SettingsCenter.jsx - 配置中心（AI 大模型配置，多提供商）
 *
 * 每个登录用户配置自己的模型提供商/API地址/AppKey，保存后搜索的 AI 总结与 AI 问答
 * 将使用本人的配置（互不影响）；未配置时回退服务器默认值。
 * 支持：DeepSeek（Anthropic/OpenAI 两种端点）、OpenAI、通义千问、智谱GLM、
 *       Kimi、豆包、Claude、Ollama 本地模型、自定义。
 */

import React, { useState, useEffect } from 'react';
import { Card, Form, Input, InputNumber, Button, message, Alert, Tag, Typography, Space, Select, AutoComplete, Radio, Divider } from 'antd';
import { SaveOutlined, ThunderboltOutlined, ReloadOutlined } from '@ant-design/icons';
import { authFetch } from '../api';

const { Text, Paragraph } = Typography;

function SettingsCenter({ isDark }) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [source, setSource] = useState('none');
  const [testResult, setTestResult] = useState(null);
  const [presets, setPresets] = useState([]);
  const [protocol, setProtocol] = useState('anthropic');
  const [modelOptions, setModelOptions] = useState([]);

  const loadConfig = async () => {
    const resp = await authFetch('/api/config/ai');
    const data = await resp.json();
    form.setFieldsValue({
      provider: data.provider || 'custom',
      model: data.model || 'deepseek-v4-pro',
      base_url: data.base_url || '',
      api_key: data.api_key_masked || '',
      max_tokens: data.max_tokens || 4096,
      protocol: data.protocol || 'anthropic',
    });
    setProtocol(data.protocol || 'anthropic');
    setSource(data.source || 'none');
    const preset = presets.find(p => p.provider === data.provider);
    if (preset) setModelOptions(preset.models || []);
    else if (data.model) setModelOptions([data.model]);
  };

  useEffect(() => {
    authFetch('/api/config/ai/presets').then(r => r.json()).then(d => {
      setPresets(d.presets || []);
    });
  }, []);

  useEffect(() => { loadConfig(); }, [presets]);

  const handleProviderChange = (provider) => {
    if (provider === 'custom') {
      form.setFieldsValue({ base_url: '', model: '' });
      setModelOptions([]);
      return;
    }
    const preset = presets.find(p => p.provider === provider);
    if (!preset) return;
    form.setFieldsValue({
      base_url: preset.base_url || '',
      protocol: preset.protocol || 'anthropic',
      model: preset.models?.[0] || '',
    });
    setProtocol(preset.protocol || 'anthropic');
    setModelOptions(preset.models || []);
    message.info(`已选用 ${preset.name}（${preset.protocol === 'openai' ? 'OpenAI 兼容协议' : 'Anthropic 协议'}），可修改模型名`);
  };

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

  const providerOptions = [
    ...presets.map(p => ({ value: p.provider, label: p.name })),
    { value: 'custom', label: '自定义（手动填写）' },
  ];

  return (
    <div style={{ width: '100%', maxWidth: 760 }}>
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
        message="选择模型提供商后自动带出 API 地址与推荐模型（可修改）。AppKey 加密存储、界面脱敏显示；每个用户独立配置，互不影响。"
      />

      <Card style={{ borderRadius: 12 }}>
        <Form form={form} layout="vertical" initialValues={{ provider: 'custom', protocol: 'anthropic' }}>
          <Form.Item name="provider" label="模型提供商">
            <Select
              options={providerOptions}
              onChange={handleProviderChange}
              style={{ maxWidth: 360 }}
            />
          </Form.Item>

          <Form.Item name="model" label="模型名称">
            <AutoComplete
              options={modelOptions.map(m => ({ value: m }))}
              placeholder="选择推荐模型或直接输入模型名"
              style={{ maxWidth: 360 }}
              filterOption={(input, option) => (option?.value || '').toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>

          <Form.Item name="protocol" label="调用协议">
            <Radio.Group onChange={e => setProtocol(e.target.value)}>
              <Radio value="anthropic">Anthropic 协议</Radio>
              <Radio value="openai">OpenAI 兼容协议</Radio>
            </Radio.Group>
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
              {protocol === 'openai'
                ? '适用于 OpenAI / 通义千问 / 智谱GLM / Kimi / 豆包 / Ollama 等'
                : '适用于 DeepSeek anthropic 端点 / Claude 官方 / 公司AI网关等'}
            </div>
          </Form.Item>

          <Form.Item name="base_url" label="API 地址（Base URL）">
            <Input placeholder="https://...（留空则用服务器默认）" />
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
        未配置个人密钥的用户将回退服务器 .env 中的默认值。Ollama 本地模型需在服务器上运行 Ollama 服务。
      </Paragraph>
    </div>
  );
}

export default SettingsCenter;
