/**
 * UserManager.jsx - 用户管理（仅管理员可见）
 *
 * 创建账号（用户名/密码/角色）、重置密码、修改角色、删除账号。
 */

import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, message, Typography, Tag, Popconfirm, Space } from 'antd';
import { PlusOutlined, KeyOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';

const { Text } = Typography;

function UserManager() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [roleUser, setRoleUser] = useState(null);
  const [roleOpen, setRoleOpen] = useState(false);
  const [form] = Form.useForm();
  const [resetForm] = Form.useForm();
  const [roleForm] = Form.useForm();
  const [currentUser, setCurrentUser] = useState('');

  const loadUsers = async () => {
    setLoading(true);
    try {
      const resp = await authFetch('/api/users');
      const data = await resp.json();
      setUsers(data.users || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    authFetch('/api/auth/me').then(r => r.json()).then(d => setCurrentUser(d.user || ''));
    loadUsers();
  }, []);

  const handleCreate = async () => {
    const values = form.getFieldsValue();
    const resp = await authFetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      message.error(data.error || '创建失败');
      return;
    }
    message.success(`用户 ${values.username} 已创建`);
    setCreateOpen(false);
    form.resetFields();
    loadUsers();
  };

  const handleReset = async () => {
    const values = resetForm.getFieldsValue();
    const resp = await authFetch(`/api/users/${encodeURIComponent(resetUser)}/password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: values.password }),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      message.error(data.error || '重置失败');
      return;
    }
    message.success(`用户 ${resetUser} 密码已重置`);
    setResetOpen(false);
    resetForm.resetFields();
  };

  const handleRoleChange = async () => {
    const values = roleForm.getFieldsValue();
    const resp = await authFetch(`/api/users/${encodeURIComponent(roleUser.username)}/role`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: values.role }),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      message.error(data.error || '修改角色失败');
      return;
    }
    message.success(`用户 ${roleUser.username} 角色已改为 ${values.role === 'admin' ? '管理员' : '普通用户'}`);
    setRoleOpen(false);
    roleForm.resetFields();
    loadUsers();
  };

  const handleDelete = async (username) => {
    const resp = await authFetch(`/api/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      message.error(data.error || '删除失败');
      return;
    }
    message.success(`用户 ${username} 已删除`);
    loadUsers();
  };

  const openRoleModal = (record) => {
    setRoleUser(record);
    roleForm.setFieldsValue({ role: record.role });
    setRoleOpen(true);
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '用户名', dataIndex: 'username' },
    {
      title: '角色', dataIndex: 'role', width: 120,
      render: (role) => (role === 'admin' ? <Tag color="gold">管理员</Tag> : <Tag>普通用户</Tag>),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 200, render: (v) => (v || '').slice(0, 19) },
    {
      title: '操作', width: 280,
      render: (_, record) => (
        <Space size={0}>
          <Button
            type="link" size="small" icon={<EditOutlined />}
            onClick={() => openRoleModal(record)}
            disabled={record.username === currentUser}
          >
            改角色
          </Button>
          <Button
            type="link" size="small" icon={<KeyOutlined />}
            onClick={() => { setResetUser(record.username); setResetOpen(true); }}
          >
            重置密码
          </Button>
          <Popconfirm
            title={`删除用户 ${record.username}？`}
            description="删除后该用户将无法登录（其 AI 配置同时失效）"
            onConfirm={() => handleDelete(record.username)}
            okText="删除" okButtonProps={{ danger: true }}
            disabled={record.username === currentUser}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}
              disabled={record.username === currentUser}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <AdminShell
      title="用户管理"
      description="每个用户登录后可到「配置中心」配置自己的 AI 模型与 AppKey，互不影响"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建用户
        </Button>
      }
    >
      <Card style={{ borderRadius: 12 }}>
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={users}
          pagination={false}
        />
      </Card>

      {/* 新建用户 */}
      <Modal
        title="新建用户"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="登录账号，如 zhangsan" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}>
            <Input.Password placeholder="初始密码" autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="user">
            <Select
              options={[
                { value: 'user', label: '普通用户（可配置自己的 AI）' },
                { value: 'admin', label: '管理员（可管理用户）' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 */}
      <Modal
        title={`重置密码 - ${resetUser || ''}`}
        open={resetOpen}
        onOk={handleReset}
        onCancel={() => { setResetOpen(false); resetForm.resetFields(); }}
        okText="重置"
        cancelText="取消"
      >
        <Form form={resetForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="password" label="新密码" rules={[{ required: true, message: '请输入新密码' }]}>
            <Input.Password placeholder="新密码" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 修改角色 */}
      <Modal
        title={`修改角色 - ${roleUser?.username || ''}`}
        open={roleOpen}
        onOk={handleRoleChange}
        onCancel={() => { setRoleOpen(false); roleForm.resetFields(); }}
        okText="确认"
        cancelText="取消"
      >
        <Form form={roleForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { value: 'user', label: '普通用户' },
                { value: 'admin', label: '管理员' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </AdminShell>
  );
}

export default UserManager;
