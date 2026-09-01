/**
 * FaqEditor.jsx - FAQ 编辑器组件
 *
 * 展示所有 FAQ 列表，支持搜索和编辑 FAQ 的标题、关键词、部门和内容。
 */
import React, { useState, useEffect, useRef } from 'react';
import { authFetch } from '../api';
import { Typography, Card, Table, Tag, Button, Input, Modal, Select, message, Upload, Space } from 'antd';
import { EditOutlined, PlusOutlined, UploadOutlined, DeleteOutlined } from '@ant-design/icons';
import ModuleSelect from './ModuleSelect';
import DeptCascader from './DeptCascader';

const { Text } = Typography;

function FaqEditor({ isDark }) {
  const [faqs, setFaqs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editModal, setEditModal] = useState(false);
  const [editRecord, setEditRecord] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editDept, setEditDept] = useState('数智财务组');
  const [editDeptIds, setEditDeptIds] = useState([]);  // 部门ID数组
  const [editModule, setEditModule] = useState('');
  const [editModuleId, setEditModuleId] = useState(0);  // 模块唯一 ID
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef(null);

  const loadFaqs = () => {
    setLoading(true);
    authFetch('/api/faq')
      .then(r => r.json())
      .then(data => { setFaqs(data?.faqs || []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadFaqs(); }, []);

  const filteredFaqs = search
    ? faqs.filter(f => f.title.includes(search) || f.id.includes(search) || (f.keywords || []).some(k => k.includes(search)))
    : faqs;

  const openEdit = async (faq) => {
    setEditRecord(faq);
    setEditTitle(faq.title || '');
    setEditKeywords((faq.keywords || []).join(', '));
    setEditDept(faq.dept || '数智财务组');
    setEditDeptIds(faq.dept_id ? [faq.dept_id] : []);
    setEditModule(faq.sub_module || '');
    setEditModuleId(faq.module_id || 0);
    setIsNew(false);
    // 加载完整内容
    setEditContent('加载中...');
    setEditModal(true);
    try {
      const resp = await authFetch(`/api/faq?id=${faq.id}`);
      const data = await resp.json();
      if (data && !data.error) {
        setEditContent(data.content || '');
      } else {
        setEditContent('（无法加载内容）');
      }
    } catch {
      setEditContent('（加载失败）');
    }
  };

  const openNew = () => {
    setEditRecord(null);
    setEditTitle('');
    setEditKeywords('');
    setEditDept('数智财务组');
    setEditDeptIds([]);
    setEditModule('');
    setEditModuleId(0);
    setEditContent('');
    setIsNew(true);
    setEditModal(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const params = new URLSearchParams({
        id: isNew ? '' : editRecord.id,
        title: editTitle,
        keywords: editKeywords,
        dept: editDept,
        dept_id: String(editDeptIds.length ? editDeptIds[editDeptIds.length - 1] : 0),
        sub_module: editModule,
        module: editModule,
        module_id: String(editModuleId || 0),
        content: editContent,
        status: 'active',
      });
      const resp = await authFetch(`/api/faq/save?${params.toString()}`);
      const data = await resp.json();
      if (!resp.ok || data.error) throw new Error(data.error || '保存失败');
      message.success('FAQ 已保存');
      setEditModal(false);
      loadFaqs();
    } catch (err) {
      message.error(`保存失败: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleExcelImport = async (file) => {
    setImporting(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await authFetch('/api/faq/import', { method: 'POST', body: formData });
      const data = await resp.json();
      if (data.error) { message.error(data.error); }
      else { message.success(`导入完成: 成功 ${data.success || 0} 条, 失败 ${data.fail || 0} 条`); }
      loadFaqs();
    } catch (err) {
      message.error(`导入失败: ${err.message}`);
    } finally {
      setImporting(false);
    }
    return false;
  };

  const handleDelete = (record) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 FAQ「${record.title}」吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const resp = await authFetch(`/api/faq/delete?path=${encodeURIComponent(record.path || '')}`);
          const data = await resp.json();
          if (data.error) { message.error(data.error); }
          else { message.success('已删除'); loadFaqs(); }
        } catch (err) {
          message.error(`删除失败: ${err.message}`);
        }
      },
    });
  };

  return (
    <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Text strong style={{ fontSize: 15 }}>FAQ 管理 ({faqs.length})</Text>
        <Space>
          <Upload accept=".xlsx,.xls" showUploadList={false} beforeUpload={handleExcelImport}>
            <Button icon={<UploadOutlined />} loading={importing} size="small">导入 Excel</Button>
          </Upload>
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew} size="small">新增 FAQ</Button>
          <Input.Search
            placeholder="搜索 FAQ..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: 230 }}
            allowClear
            size="small"
          />
        </Space>
      </div>
      <Table
        dataSource={filteredFaqs}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={{ pageSize: 10, size: 'small' }}
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id', width: 180, render: t => <Text code style={{ fontSize: 11 }}>{t}</Text> },
          { title: '标题', dataIndex: 'title', key: 'title', render: t => <Text strong style={{ fontSize: 13, color: isDark ? '#e5e5e5' : '#303133' }}>{t}</Text> },
          { title: '部门', dataIndex: 'dept', key: 'dept', width: 100, render: t => <Tag style={{ fontSize: 10 }}>{t}</Tag> },
          { title: '模块', dataIndex: 'sub_module', key: 'sub_module', width: 100, render: t => <span style={{ fontSize: 12 }}>{t || '-'}</span> },
          {
            title: '操作', key: 'actions', width: 120,
            render: (_, record) => (
              <Space size={0}>
                <Button type="link" size="small" icon={<EditOutlined />}
                  onClick={() => openEdit(record)} style={{ fontSize: 12, padding: '0 4px' }}>编辑</Button>
                <Button type="link" size="small" danger icon={<DeleteOutlined />}
                  onClick={() => handleDelete(record)} style={{ fontSize: 12, padding: '0 4px' }}>删除</Button>
              </Space>
            ),
          },
        ]}
      />

      {/* 编辑弹窗 */}
      <Modal
        title={isNew ? '新增 FAQ' : `编辑 FAQ: ${editRecord?.id || ''}`}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        width={650}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Input value={editTitle} onChange={e => setEditTitle(e.target.value)} placeholder="FAQ 标题" />
          <Input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} placeholder="关键词（逗号分隔）" />
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>所属部门</Text>
              <DeptCascader value={editDeptIds} onChange={(ids, names) => { setEditDeptIds(ids); setEditDept(names.join(', ')); }} placeholder="选择部门" />
            </div>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>所属模块</Text>
              <ModuleSelect
                value={editModule}
                onChange={(name, id) => { setEditModule(name); setEditModuleId(id || 0); }}
                placeholder="输入模块名搜索..."
              />
            </div>
          </div>
          <Input.TextArea value={editContent} onChange={e => setEditContent(e.target.value)} rows={12} placeholder="FAQ 内容" />
        </div>
      </Modal>
    </Card>
  );
}

export default FaqEditor;