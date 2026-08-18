/**
 * ManagePanel.jsx - 知识管理面板
 *
 * 知识管理主页，包含 FAQ 草稿管理、上传文档、编辑 FAQ、重建索引、
 * 关键词管理等功能入口。草稿数据存储在 localStorage 中。
 */
import React, { useState } from 'react';
import { Typography, Card, Row, Col, Table, Tag, Button, Empty, Modal, Select, Input } from 'antd';
import { CloudUploadOutlined, QuestionCircleOutlined, ReloadOutlined, SearchOutlined, BugOutlined } from '@ant-design/icons';
import { saveFAQ, deleteFAQ } from '../api';

const { Text } = Typography;

const DEPT_OPTIONS = [
  { label: '数智财务组', value: '数智财务组' },
  { label: '免疫规划组', value: '免疫规划组' },
  { label: '电子档案组', value: '电子档案组' },
  { label: '数字化支撑组', value: '数字化支撑组' },
];

/** 知识管理面板 */
function ManagePanel({ isDark }) {
  const [faqDrafts, setFaqDrafts] = useState(() => {
    try { return JSON.parse(localStorage.getItem('kb_faq_drafts') || '[]'); }
    catch { return []; }
  });
  const [activeSection, setActiveSection] = useState('drafts');

  // 发布弹窗状态
  const [publishModal, setPublishModal] = useState(false);
  const [publishRecord, setPublishRecord] = useState(null);
  const [publishDept, setPublishDept] = useState('数智财务组');
  const [publishModule, setPublishModule] = useState('浙里报');
  const [publishContent, setPublishContent] = useState('');
  const [suggesting, setSuggesting] = useState(false);

  const handleDeleteDraft = async (id, path) => {
    if (path) {
      await deleteFAQ(path);
    }
    const updated = faqDrafts.filter(d => d.id !== id);
    setFaqDrafts(updated);
    localStorage.setItem('kb_faq_drafts', JSON.stringify(updated));
  };

  // 打开发布弹窗，自动检测归属
  const openPublishModal = async (record) => {
    setPublishRecord(record);
    setPublishDept('数智财务组');
    setPublishModule('浙里报');
    const answerText = record.answer || '待补充';
    setPublishContent(`## 问题描述\n\n${record.question}\n\n## 解决方法\n\n${answerText}`);
    setPublishModal(true);
    setSuggesting(true);

    try {
      const kw = (record.keywords || []).join(',');
      const resp = await fetch(`/api/faq/suggest?title=${encodeURIComponent(record.question)}&keywords=${encodeURIComponent(kw)}`);
      const data = await resp.json();
      if (data?.dept) setPublishDept(data.dept);
      if (data?.module) setPublishModule(data.module);
    } catch {} finally {
      setSuggesting(false);
    }
  };

  // 确认发布
  const handlePublish = async () => {
    if (!publishRecord) return;
    await saveFAQ({
      title: publishRecord.question,
      keywords: (publishRecord.keywords || []).join(','),
      dept: publishDept,
      sub_module: publishModule,
      module: publishModule,
      content: publishContent,
      status: 'active',
    });
    handleDeleteDraft(publishRecord.id);
    setPublishModal(false);
  };

  const sections = [
    { key: 'drafts', title: 'FAQ草稿', desc: '从工单/搜索沉淀的 FAQ 草稿', icon: <BugOutlined />, count: faqDrafts.length },
    { key: 'upload', title: '上传文档', desc: '上传 Markdown 或 Word 文档到知识库', icon: <CloudUploadOutlined /> },
    { key: 'faq', title: '编辑 FAQ', desc: '管理和编辑 FAQ 知识库条目', icon: <QuestionCircleOutlined /> },
    { key: 'rebuild', title: '重建索引', desc: '重新构建搜索引擎索引', icon: <ReloadOutlined /> },
    { key: 'keywords', title: '关键词管理', desc: '管理搜索关键词和同义词', icon: <SearchOutlined /> },
  ];

  return (
    <div style={{ width: '100%' }}>
      <Text strong style={{ fontSize: 20, display: 'block', marginBottom: 20, color: isDark ? '#e5e5e5' : '#1e293b' }}>知识管理</Text>
      <Row gutter={[16, 16]}>
        {sections.map((item, i) => (
          <Col span={12} key={i}>
            <Card
              hoverable
              style={{
                borderRadius: 12,
                border: activeSection === item.key ? '2px solid #0D9488' : '1px solid #e2e8f0',
              }}
              onClick={() => setActiveSection(item.key)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 8,
                  background: 'rgba(13,148,136,0.08)', display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  color: '#0D9488', fontSize: 18,
                }}>
                  {item.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <Text strong style={{ fontSize: 14 }}>
                    {item.title}
                    {item.count > 0 && <span style={{ color: '#0D9488', marginLeft: 4 }}>({item.count})</span>}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>{item.desc}</Text>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* FAQ 草稿列表 */}
      {activeSection === 'drafts' && (
        <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
          <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 16 }}>FAQ 草稿箱</Text>
          {faqDrafts.length === 0 ? (
            <Empty description="暂无草稿，搜索后点击「工单知识沉淀」按钮即可保存" />
          ) : (
            <Table
              dataSource={faqDrafts}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
              columns={[
                {
                  title: '问题', dataIndex: 'question', key: 'question',
                  render: text => <Text strong style={{ fontSize: 13, color: '#0D9488' }}>{text}</Text>,
                },
                { title: '关键词', dataIndex: 'keywords', key: 'keywords', render: arr => (arr || []).slice(0, 3).map(k => <Tag key={k} style={{ fontSize: 10, borderRadius: 4, margin: '1px 2px' }}>{k}</Tag>) },
                {
                  title: '时间', dataIndex: 'createdAt', key: 'createdAt',
                  render: text => <Text type="secondary" style={{ fontSize: 12 }}>{new Date(text).toLocaleDateString('zh-CN')}</Text>,
                },
                {
                  title: '操作', key: 'actions',
                  render: (_, record) => (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Button type="link" size="small" style={{ fontSize: 12, padding: 0, color: '#0D9488' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          openPublishModal(record);
                        }}
                      >发布</Button>
                      <Button type="link" size="small" danger style={{ fontSize: 12, padding: 0 }}
                        onClick={(e) => { e.stopPropagation(); handleDeleteDraft(record.id, record.path); }}
                      >删除</Button>
                    </div>
                  ),
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* 其他 section 占位 */}
      {activeSection !== 'drafts' && (
        <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
          <Empty description={`${sections.find(s => s.key === activeSection)?.title}功能开发中...`} />
        </Card>
      )}

      {/* 发布弹窗 */}
      <Modal
        title="发布 FAQ"
        open={publishModal}
        onOk={handlePublish}
        onCancel={() => setPublishModal(false)}
        okText="确认发布"
        cancelText="取消"
        width={600}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>问题</Text>
            <div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{publishRecord?.question}</div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                所属部门 {suggesting && <span style={{ color: '#0D9488' }}>自动检测中...</span>}
              </Text>
              <Select
                value={publishDept}
                onChange={setPublishDept}
                options={DEPT_OPTIONS}
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>所属模块</Text>
              <Input
                value={publishModule}
                onChange={e => setPublishModule(e.target.value)}
                style={{ marginTop: 4 }}
                placeholder="如：浙里报、预防接种"
              />
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>内容（可编辑）</Text>
            <Input.TextArea
              value={publishContent}
              onChange={e => setPublishContent(e.target.value)}
              rows={8}
              style={{ marginTop: 4, fontSize: 13 }}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default ManagePanel;