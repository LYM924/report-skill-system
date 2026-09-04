/**
 * AuditLog.jsx - 操作审计日志
 *
 * 展示 audit_logs 表记录，支持按用户/操作类型/时间筛选。
 * 仅管理员可见。
 */

import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Input, Select, Button, Space, Spin, Typography } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';

const { Text } = Typography;

// 操作类型选项
const ACTION_OPTIONS = [
  { value: '', label: '全部操作' },
  { value: 'auth', label: '认证登录' },
  { value: 'user', label: '用户管理' },
  { value: 'doc', label: '文档操作' },
  { value: 'faq', label: 'FAQ 操作' },
  { value: 'keyword', label: '关键词操作' },
  { value: 'system', label: '系统操作' },
  { value: 'config', label: '配置变更' },
];

// 操作类型颜色映射
const ACTION_COLORS = {
  'auth.login': 'green', 'auth.sso_login': 'cyan',
  'user.create': 'blue', 'user.delete': 'red', 'user.reset_password': 'orange', 'user.update_role': 'purple',
  'doc.upload': 'blue', 'doc.delete': 'red', 'doc.update': 'geekblue',
  'faq.save': 'blue', 'faq.delete': 'red', 'faq.import': 'purple',
  'keyword.add': 'blue', 'keyword.update': 'geekblue', 'keyword.delete': 'red',
  'system.rebuild': 'gold',
  'config.ai_save': 'cyan',
};

function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterUsername, setFilterUsername] = useState('');
  const [filterAction, setFilterAction] = useState('');

  const loadLogs = async (p = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: '50' });
      if (filterUsername) params.set('username', filterUsername);
      if (filterAction) params.set('action_prefix', filterAction);
      const resp = await authFetch(`/api/audit/logs?${params.toString()}`);
      const data = await resp.json();
      setLogs(data.logs || []);
      setTotal(data.total || 0);
      setPage(p);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadLogs(); }, []);

  const columns = [
    {
      title: '时间', dataIndex: 'created_at', width: 180,
      render: (v) => (v || '').slice(0, 19),
    },
    {
      title: '用户', dataIndex: 'username', width: 120,
      render: (v) => <Text strong style={{ fontSize: 13 }}>{v}</Text>,
    },
    {
      title: '操作', dataIndex: 'action', width: 160,
      render: (v) => <Tag color={ACTION_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '对象', dataIndex: 'target', width: 180,
      render: (v) => <Text style={{ fontSize: 12 }}>{v || '-'}</Text>,
    },
    {
      title: '详情', dataIndex: 'detail',
      render: (v) => {
        if (!v) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        try {
          const obj = JSON.parse(v);
          return <Text style={{ fontSize: 12 }}>{JSON.stringify(obj).slice(0, 100)}</Text>;
        } catch {
          return <Text style={{ fontSize: 12 }}>{v.slice(0, 100)}</Text>;
        }
      },
    },
    {
      title: 'IP', dataIndex: 'ip', width: 130,
      render: (v) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '-'}</Text>,
    },
  ];

  return (
    <AdminShell
      title="审计日志"
      description="记录系统中所有管理操作的审计轨迹"
      extra={<Button icon={<ReloadOutlined />} onClick={() => loadLogs(page)} loading={loading}>刷新</Button>}
    >
      {/* 筛选栏 */}
      <Card style={{ borderRadius: 12, marginBottom: 16 }}>
        <Space style={{ width: '100%' }} size="middle">
          <Input
            placeholder="按用户名筛选"
            prefix={<SearchOutlined />}
            value={filterUsername}
            onChange={e => setFilterUsername(e.target.value)}
            onPressEnter={() => loadLogs(1)}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            options={ACTION_OPTIONS}
            value={filterAction}
            onChange={setFilterAction}
            style={{ width: 150 }}
          />
          <Button type="primary" onClick={() => loadLogs(1)}>查询</Button>
        </Space>
      </Card>

      {/* 日志表格 */}
      <Card style={{ borderRadius: 12 }}>
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={logs}
          pagination={{
            current: page,
            total,
            pageSize: 50,
            size: 'small',
            showTotal: t => `共 ${t} 条`,
            onChange: (p) => loadLogs(p),
          }}
        />
      </Card>
    </AdminShell>
  );
}

export default AuditLog;
