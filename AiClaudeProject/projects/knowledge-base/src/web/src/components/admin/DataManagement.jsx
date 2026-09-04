/**
 * DataManagement.jsx - 数据管理面板
 *
 * 整合：索引管理（状态+重建）、文档统计、同义词管理。
 * 仅管理员可见。
 */

import React, { useState, useEffect } from 'react';
import { Card, Tabs, Table, Tag, Button, Input, Space, Empty, Spin, Typography, message, Modal, Form, Row, Col } from 'antd';
import { SyncOutlined, PlusOutlined, DeleteOutlined, DatabaseOutlined } from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';

const { Text } = Typography;

function DataManagement() {
  const [activeTab, setActiveTab] = useState('index');
  const [indexStatus, setIndexStatus] = useState(null);
  const [synonyms, setSynonyms] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addSynonymOpen, setAddSynonymOpen] = useState(false);
  const [synonymForm] = Form.useForm();

  const loadData = async () => {
    setLoading(true);
    try {
      const [healthResp, synonymsResp, statsResp] = await Promise.all([
        authFetch('/api/health').then(r => r.json()).catch(() => null),
        authFetch('/api/synonyms').then(r => r.json()).catch(() => ({ synonyms: [] })),
        authFetch('/api/data/stats').then(r => r.json()).catch(() => null),
      ]);
      setIndexStatus(healthResp);
      setSynonyms(synonymsResp?.synonyms || []);
      setStats(statsResp);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleRebuild = async () => {
    try {
      const resp = await authFetch('/api/rebuild');
      if (resp.ok) {
        message.success('索引重建已触发');
      } else {
        const data = await resp.json().catch(() => ({}));
        message.error(data.error || data.detail || '重建失败');
      }
    } catch {
      message.error('重建失败');
    }
  };

  // ─── 同义词管理 ───
  const handleAddSynonym = async () => {
    const values = synonymForm.getFieldsValue();
    if (!values.word || !values.synonym) {
      message.warning('词和同义词均不能为空');
      return;
    }
    try {
      const resp = await authFetch('/api/synonyms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        message.error(data.error || '添加失败');
        return;
      }
      message.success('同义词已添加');
      setAddSynonymOpen(false);
      synonymForm.resetFields();
      loadData();
    } catch {
      message.error('添加失败');
    }
  };

  const handleDeleteSynonym = async (id) => {
    try {
      const resp = await authFetch(`/api/synonyms/${id}`, { method: 'DELETE' });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        message.error(data.error || '删除失败');
        return;
      }
      message.success('同义词已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;

  // ─── 索引管理 Tab ───
  const renderIndexTab = () => {
    const drift = indexStatus?.drift;
    const hasDrift = !drift?.ok;
    return (
      <div>
        {hasDrift && drift?.warnings?.map((w, i) => (
          <Card key={i} style={{ borderRadius: 8, marginBottom: 12, borderLeft: '4px solid #faad14' }}>
            <Text type="warning" style={{ fontSize: 13 }}>{w}</Text>
          </Card>
        ))}
        <Card title="索引操作" style={{ borderRadius: 12, marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              重建索引包括 BM25 倒排索引、关键词映射索引和文档加载。通常在增删文档后执行。
            </Text>
            <Button type="primary" icon={<SyncOutlined />} onClick={handleRebuild}>
              重建全部索引
            </Button>
          </Space>
        </Card>

        {/* 数据计数 */}
        {indexStatus?.counts && (
          <Card title="数据计数" style={{ borderRadius: 12 }}>
            <Row gutter={[16, 8]}>
              {Object.entries(indexStatus.counts).map(([table, count]) => (
                <Col span={8} key={table}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{table}</Text>
                    <div><Text strong style={{ fontSize: 20 }}>{count ?? '-'}</Text></div>
                  </div>
                </Col>
              ))}
            </Row>
          </Card>
        )}
      </div>
    );
  };

  // ─── 文档统计 Tab ───
  const renderStatsTab = () => {
    if (!stats) return <Empty description="暂无统计数据" />;
    const deptStats = stats.dept_stats || [];
    return (
      <Card title="按部门统计" style={{ borderRadius: 12 }}>
        <Table
          rowKey="dept"
          size="small"
          pagination={false}
          columns={[
            { title: '部门', dataIndex: 'dept', key: 'dept' },
            { title: '文档数', dataIndex: 'doc_count', key: 'doc_count', width: 100, render: v => <Text strong>{v}</Text> },
            { title: 'FAQ 数', dataIndex: 'faq_count', key: 'faq_count', width: 100, render: v => <Text strong>{v}</Text> },
          ]}
          dataSource={deptStats}
        />
      </Card>
    );
  };

  // ─── 同义词管理 Tab ───
  const renderSynonymsTab = () => (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text type="secondary">搜索同义词扩展，添加后搜索时自动匹配同义词</Text>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setAddSynonymOpen(true)}>
          添加同义词
        </Button>
      </div>
      <Table
        rowKey="id"
        size="small"
        pagination={{ pageSize: 20, size: 'small' }}
        columns={[
          { title: '词', dataIndex: 'word', key: 'word', render: v => <Text strong>{v}</Text> },
          { title: '同义词', dataIndex: 'synonym', key: 'synonym' },
          {
            title: '操作', width: 80,
            render: (_, record) => (
              <Button type="link" size="small" danger icon={<DeleteOutlined />}
                onClick={() => {
                  Modal.confirm({
                    title: '删除同义词',
                    content: `确定删除「${record.word} → ${record.synonym}」？`,
                    onConfirm: () => handleDeleteSynonym(record.id),
                  });
                }}
              />
            ),
          },
        ]}
        dataSource={synonyms}
      />

      <Modal title="添加同义词" open={addSynonymOpen}
        onOk={handleAddSynonym}
        onCancel={() => { setAddSynonymOpen(false); synonymForm.resetFields(); }}
        okText="添加" cancelText="取消"
      >
        <Form form={synonymForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="word" label="词" rules={[{ required: true }]}>
            <Input placeholder="如：报销单" />
          </Form.Item>
          <Form.Item name="synonym" label="同义词" rules={[{ required: true }]}>
            <Input placeholder="如：费用报销" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );

  return (
    <AdminShell title="数据管理" description="索引管理、文档统计、同义词管理">
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: 'index', label: '索引管理', icon: <DatabaseOutlined />, children: renderIndexTab() },
        { key: 'stats', label: '文档统计', children: renderStatsTab() },
        { key: 'synonyms', label: '同义词管理', children: renderSynonymsTab() },
      ]} />
    </AdminShell>
  );
}

export default DataManagement;
