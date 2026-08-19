/**
 * ManagePanel.jsx - 知识管理面板
 *
 * 知识管理主页，包含 FAQ 草稿管理、上传文档、编辑 FAQ、重建索引、
 * 关键词管理等功能入口。草稿数据存储在 localStorage 中。
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Row, Col, Table, Tag, Button, Empty, Modal, Select, Input, Spin, message } from 'antd';
import { CloudUploadOutlined, QuestionCircleOutlined, ReloadOutlined, SearchOutlined, BugOutlined, FileTextOutlined } from '@ant-design/icons';
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

  const [editModal, setEditModal] = useState(false);
  const [editRecord, setEditRecord] = useState(null);
  const [editQuestion, setEditQuestion] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editAnswer, setEditAnswer] = useState('');

  const [uploadModal, setUploadModal] = useState(false);
  const [uploadContent, setUploadContent] = useState('');
  const [uploadFilename, setUploadFilename] = useState('');
  const [uploadDept, setUploadDept] = useState('数智财务组');
  const [uploadModule, setUploadModule] = useState('浙里报');

  const handleDeleteDraft = async (id, path) => {
    if (path) {
      await deleteFAQ(path);
    }
    const updated = faqDrafts.filter(d => d.id !== id);
    setFaqDrafts(updated);
    localStorage.setItem('kb_faq_drafts', JSON.stringify(updated));
  };

  const openEditModal = (record) => {
    setEditRecord(record);
    setEditQuestion(record.question || '');
    setEditKeywords((record.keywords || []).join(', '));
    setEditAnswer(record.answer || '');
    setEditModal(true);
  };

  const handleSaveEdit = () => {
    if (!editRecord) return;
    const drafts = JSON.parse(localStorage.getItem('kb_faq_drafts') || '[]');
    const idx = drafts.findIndex(d => d.id === editRecord.id);
    if (idx >= 0) {
      drafts[idx] = {
        ...drafts[idx],
        question: editQuestion,
        keywords: editKeywords.split(',').map(k => k.trim()).filter(Boolean),
        answer: editAnswer,
      };
      localStorage.setItem('kb_faq_drafts', JSON.stringify(drafts));
      setFaqDrafts(drafts);
    }
    setEditModal(false);
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
    { key: 'logs', title: '系统日志', desc: '查看服务运行日志', icon: <FileTextOutlined /> },
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
              onClick={() => {
                setActiveSection(item.key);
                if (item.key === 'upload') setUploadModal(true);
              }}
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
                      <Button type="link" size="small" style={{ fontSize: 12, padding: 0 }}
                        onClick={(e) => { e.stopPropagation(); openEditModal(record); }}
                      >编辑</Button>
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

      {/* 系统日志 */}
      {activeSection === 'logs' && <LogViewer />}

      {/* 关键词管理 */}
      {activeSection === 'keywords' && <KeywordManager />}

      {/* 重建索引 */}
      {activeSection === 'rebuild' && (
        <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
          <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 12 }}>重建索引</Text>
          <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 16 }}>
            重新构建搜索引擎索引，包括 BM25、FAISS 向量和关键词索引。通常在增删文档后执行。
          </Text>
          <Button type="primary" icon={<ReloadOutlined />}
            onClick={async () => {
              await fetch('/api/rebuild');
              message.success('索引重建完成');
            }}>
            开始重建
          </Button>
        </Card>
      )}

      {/* 其他 section 占位 */}
      {activeSection !== 'drafts' && activeSection !== 'logs' && activeSection !== 'keywords' && activeSection !== 'rebuild' && (
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

      {/* 编辑弹窗 */}
      <Modal
        title="编辑 FAQ 草稿"
        open={editModal}
        onOk={handleSaveEdit}
        onCancel={() => setEditModal(false)}
        okText="保存"
        cancelText="取消"
        width={600}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>问题</Text>
            <Input value={editQuestion} onChange={e => setEditQuestion(e.target.value)} style={{ marginTop: 4 }} />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>关键词（逗号分隔）</Text>
            <Input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} style={{ marginTop: 4 }} />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>解决方法</Text>
            <Input.TextArea value={editAnswer} onChange={e => setEditAnswer(e.target.value)} rows={8} style={{ marginTop: 4, fontSize: 13 }} />
          </div>
        </div>
      </Modal>

      {/* 上传文档弹窗 */}
      <Modal
        title="上传文档到知识库"
        open={uploadModal}
        onCancel={() => {
          setUploadModal(false);
          setUploadContent('');
          setUploadFilename('');
        }}
        footer={null}
        width={500}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>选择 .md 文件</Text>
            <input
              type="file"
              accept=".md,.txt"
              onChange={async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const text = await file.text();
                setUploadContent(text);
                setUploadFilename(file.name.replace('.md', '').replace('.txt', ''));
              }}
              style={{ marginTop: 4, display: 'block' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>所属部门</Text>
              <Select
                value={uploadDept}
                onChange={setUploadDept}
                options={DEPT_OPTIONS}
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>所属模块</Text>
              <Input
                value={uploadModule}
                onChange={e => setUploadModule(e.target.value)}
                style={{ marginTop: 4 }}
                placeholder="如：浙里报"
              />
            </div>
          </div>
          {uploadContent && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>文件内容预览</Text>
              <div style={{
                maxHeight: 200, overflow: 'auto', background: '#f8fafc',
                borderRadius: 6, padding: 12, marginTop: 4,
                fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
              }}>
                {uploadContent.slice(0, 2000)}
              </div>
            </div>
          )}
          <Button
            type="primary"
            block
            disabled={!uploadContent}
            onClick={async () => {
              const body = JSON.stringify({
                filename: uploadFilename,
                content: uploadContent,
                dept: uploadDept,
                module: uploadModule,
              });
              const resp = await fetch('/api/document/upload', {
                method: 'POST',
                body,
              });
              const result = await resp.json();
              if (result.ok) {
                message.success(`已上传: ${result.filename}`);
                setUploadModal(false);
                setUploadContent('');
                setUploadFilename('');
              } else {
                message.error(result.error || '上传失败');
              }
            }}
          >
            上传到知识库
          </Button>
        </div>
      </Modal>
    </div>
  );
}

/** 关键词管理组件 */
function KeywordManager() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [addKw, setAddKw] = useState('');
  const [addModule, setAddModule] = useState('');
  const [addDept, setAddDept] = useState('');

  const loadKeywords = () => {
    setLoading(true);
    fetch(`/api/keywords?q=${encodeURIComponent(search)}&page_size=100`)
      .then(r => r.json())
      .then(data => { setKeywords(data?.keywords || []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadKeywords(); }, []);

  const handleAdd = async () => {
    if (!addKw.trim() || !addModule.trim()) return;
    await fetch(`/api/keywords/add?keyword=${encodeURIComponent(addKw.trim())}&module=${encodeURIComponent(addModule.trim())}&dept=${encodeURIComponent(addDept.trim())}`);
    setAddKw(''); setAddModule(''); setAddDept('');
    loadKeywords();
  };

  const handleDelete = async (kw) => {
    await fetch(`/api/keywords/delete?keyword=${encodeURIComponent(kw)}`);
    loadKeywords();
  };

  return (
    <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
      <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 12 }}>关键词管理</Text>
      {/* Add form */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Input placeholder="关键词" value={addKw} onChange={e => setAddKw(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="模块" value={addModule} onChange={e => setAddModule(e.target.value)} style={{ width: 150 }} />
        <Input placeholder="部门" value={addDept} onChange={e => setAddDept(e.target.value)} style={{ width: 120 }} />
        <Button type="primary" size="small" onClick={handleAdd}>添加</Button>
      </div>
      {/* Search */}
      <Input.Search placeholder="搜索关键词..." value={search} onChange={e => setSearch(e.target.value)} onSearch={loadKeywords} style={{ marginBottom: 12 }} />
      {/* List */}
      <Table
        dataSource={keywords}
        rowKey="keyword"
        size="small"
        loading={loading}
        pagination={{ pageSize: 20, size: 'small' }}
        columns={[
          { title: '关键词', dataIndex: 'keyword', key: 'keyword', render: t => <Text code style={{ fontSize: 12 }}>{t}</Text> },
          { title: '模块', dataIndex: 'modules', key: 'modules', render: arr => (arr||[]).slice(0,3).map(m => <Tag key={m} style={{fontSize:10,margin:'1px 2px'}}>{m}</Tag>) },
          { title: '部门', dataIndex: 'depts', key: 'depts', render: arr => (arr||[]).slice(0,2).map(d => <Tag key={d} style={{fontSize:10,margin:'1px 2px'}}>{d}</Tag>) },
          { title: '引用', dataIndex: 'count', key: 'count', width: 60 },
          { title: '操作', key: 'act', width: 60, render: (_,r) => <Button type="link" size="small" danger style={{fontSize:12,padding:0}} onClick={() => handleDelete(r.keyword)}>删除</Button> },
        ]}
      />
    </Card>
  );
}

export default ManagePanel;

/** 系统日志查看器 */
function LogViewer() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadLogs = () => {
    setLoading(true);
    fetch('/api/logs?lines=200')
      .then(r => r.json())
      .then(data => {
        setLogs(data?.logs || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadLogs(); }, []);

  return (
    <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text strong style={{ fontSize: 15 }}>系统日志</Text>
        <Button size="small" onClick={loadLogs} loading={loading}>刷新</Button>
      </div>
      {/* 颜色图例 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
        {[
          { color: '#f87171', label: '错误 ERROR' },
          { color: '#60a5fa', label: '搜索 SEARCH' },
          { color: '#4ade80', label: 'FAQ操作' },
          { color: '#fbbf24', label: '服务启动' },
          { color: '#94a3b8', label: '常规日志' },
        ].map(item => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#666' }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: item.color }} />
            {item.label}
          </div>
        ))}
      </div>
      {loading ? (
        <Spin />
      ) : logs.length === 0 ? (
        <Empty description="暂无日志" />
      ) : (
        <div style={{
          background: '#1e293b', color: '#e2e8f0', borderRadius: 8, padding: '12px 16px',
          maxHeight: 500, overflow: 'auto', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.8,
          whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        }}>
          {logs.map((line, i) => (
            <div key={i} style={{
              color: line.includes('ERROR') ? '#f87171' :
                     line.includes('SEARCH') ? '#60a5fa' :
                     line.includes('FAQ_SAVE') ? '#4ade80' :
                     line.includes('SERVER_START') ? '#fbbf24' : '#94a3b8',
            }}>
              {line}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}