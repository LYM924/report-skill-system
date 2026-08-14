/**
 * CenterContent.jsx - 中间主面板
 *
 * 布局（从上到下）：
 * 1. 搜索栏（全宽一行）→ 对接 searchKnowledge API
 * 2. 快捷按钮（大模型总结、自动关联文档、相似问题推荐、工单知识沉淀）
 * 3. 知识总览（渐变背景卡片）→ 对接 getDashboardStats API
 * 4. AI 搜索结果展示
 * 5. 文档列表表格 → 对接 getDocuments API
 */

import React, { useState, useEffect } from 'react';
import { Typography, Card, Table, Tag, Tabs, Input, Button, Select, Row, Col, Spin, Empty } from 'antd';
import {
  RobotOutlined, SearchOutlined, BulbOutlined,
  LinkOutlined, FileSearchOutlined, CloudUploadOutlined,
} from '@ant-design/icons';
import { searchKnowledge, getDashboardStats, getDocuments } from '../api';

const { Text } = Typography;

const quickActions = [
  { key: 'ai_summary', label: '大模型总结', icon: <RobotOutlined />, color: '#fff', bg: '#1e293b' },
  { key: 'auto_link', label: '自动关联文档', icon: <LinkOutlined />, color: '#333', bg: '#fff' },
  { key: 'similar', label: '相似问题推荐', icon: <FileSearchOutlined />, color: '#333', bg: '#fff' },
  { key: 'ticket_deposit', label: '工单知识沉淀', icon: <CloudUploadOutlined />, color: '#333', bg: '#fff' },
];

function CenterContent() {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchScope, setSearchScope] = useState('all');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);

  const [dashboardStats, setDashboardStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [aiTab, setAiTab] = useState('summary');

  /**
   * 初始化：加载仪表盘数据和文档列表
   */
  useEffect(() => {
    Promise.all([
      getDashboardStats(),
      getDocuments(),
    ]).then(([stats, docs]) => {
      if (stats) setDashboardStats(stats);
      if (docs) setDocuments(docs);
      setLoading(false);
    });
  }, []);

  /**
   * 智能搜索
   */
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    const results = await searchKnowledge(searchQuery.trim(), searchScope);
    setSearchResults(results);
    setSearching(false);
  };

  const stats = dashboardStats || {};

  const columns = [
    { title: '文档', dataIndex: 'name', key: 'name', render: text => <Text strong style={{ fontSize: 13, color: '#333' }}>{text}</Text> },
    { title: '产品记录', dataIndex: 'product', key: 'product', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
    { title: '所属部门', dataIndex: 'dept', key: 'dept', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
    { title: '更新时间', dataIndex: 'updated', key: 'updated', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
  ];

  return (
    <div style={{ maxWidth: 960 }}>
      {/* ===== 1. 搜索栏（全宽一行）对接后端搜索 API ===== */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1, display: 'flex' }}>
          <Select
            value={searchScope}
            onChange={setSearchScope}
            size="large"
            style={{ width: 160, borderRadius: '8px 0 0 8px' }}
            options={[
              { value: 'all', label: '全部知识' },
              { value: 'doc', label: '产品文档' },
              { value: 'faq', label: 'FAQ' },
              { value: 'dept', label: '部门知识' },
            ]}
          />
          <Input
            placeholder="输入关键词搜索知识库..."
            size="large"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onPressEnter={handleSearch}
            style={{ flex: 1, borderRadius: 0, borderLeft: 'none', borderRight: 'none' }}
          />
          <Button
            type="primary"
            size="large"
            icon={<SearchOutlined />}
            onClick={handleSearch}
            loading={searching}
            style={{ borderRadius: '0 8px 8px 0', background: '#0D9488', borderColor: '#0D9488' }}
          >
            智能检索
          </Button>
        </div>
      </div>

      {/* ===== 2. 快捷按钮 ===== */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {quickActions.map(action => (
          <Button
            key={action.key}
            icon={action.icon}
            style={{
              background: action.bg, color: action.color,
              border: action.bg === '#fff' ? '1px solid #d1d5db' : 'none',
              borderRadius: 8, padding: '4px 16px', fontSize: 13, height: 36,
            }}
          >
            {action.label}
          </Button>
        ))}
      </div>

      {/* ===== 3. 知识总览（渐变卡片） ===== */}
      <div style={{
        background: 'linear-gradient(135deg, #334155 0%, #0D9488 100%)',
        borderRadius: 12, padding: '20px 24px', marginBottom: 20, color: '#fff',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Text strong style={{ fontSize: 20, color: '#fff' }}>知识总览</Text>
          <span style={{ cursor: 'pointer', fontSize: 16, opacity: 0.8 }}>▲</span>
        </div>
        {loading ? (
          <Spin />
        ) : (
          <Row gutter={[16, 16]}>
            <Col span={6}>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>知识文档</div>
                <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.totalDocs?.toLocaleString() || '-'}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>FAQ沉淀</div>
                <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.faqCount?.toLocaleString() || '-'}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>本周问题</div>
                <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.weekQuestions || '-'}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>本周新增</div>
                <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>
                  {stats.weekNew || '-'} <span style={{ fontSize: 14, fontWeight: 400 }}>%</span>
                </div>
              </div>
            </Col>
          </Row>
        )}
      </div>

      {/* ===== 4. 搜索结果 / AI 分析 ===== */}
      {searchResults && searchResults.answer && (
        <Card style={{ borderRadius: 12, marginBottom: 20, border: '1px solid #e8e8e8' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8, background: 'linear-gradient(135deg, #e8f0fe 0%, #d4e2fc 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <BulbOutlined style={{ fontSize: 18, color: '#0D9488' }} />
            </div>
            <div>
              <Text strong style={{ fontSize: 15 }}>搜索结果</Text>
              <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                找到 {searchResults.total || 0} 条结果
              </Text>
            </div>
          </div>
          <div style={{ padding: '12px 0', fontSize: 13, lineHeight: 1.9, color: '#555' }}>
            {searchResults.answer?.summary || searchResults.answer?.answer || '暂无内容'}
          </div>
        </Card>
      )}

      {/* ===== 5. 文档列表表格 ===== */}
      <Card style={{ borderRadius: 12, border: '1px solid #e8e8e8' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button size="small" style={{ background: '#1e293b', color: '#fff', borderRadius: 6, border: 'none', fontSize: 12 }}>AI总结果</Button>
            <Button size="small" style={{ background: '#fff', color: '#333', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 12 }}>核心结论</Button>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button size="small" style={{ borderRadius: 6, fontSize: 12 }}>问答统计趋势</Button>
            <Button size="small" style={{ borderRadius: 6, fontSize: 12 }}>引用文档</Button>
            <Button size="small" style={{ background: '#1e293b', color: '#fff', borderRadius: 6, border: 'none', fontSize: 12 }}>置信度92%</Button>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : documents.length === 0 ? (
          <Empty description="暂无文档" />
        ) : (
          <>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>文档</Text>
            <Table
              dataSource={documents}
              columns={columns}
              rowKey="id"
              pagination={{ pageSize: 6, size: 'small' }}
              size="middle"
              rowSelection={{}}
            />
          </>
        )}
      </Card>
    </div>
  );
}

export default CenterContent;