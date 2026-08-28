/**
 * KeywordManager.jsx - 关键词管理组件
 *
 * 管理系统关键词映射，支持添加、编辑、删除关键词，
 * 以及按关键词搜索查看。
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Table, Tag, Button, Input, AutoComplete, Modal, message } from 'antd';
import ModuleSelect from './ModuleSelect';
import { fetchDeptOptions } from './constants';

const { Text } = Typography;

function KeywordManager() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [addKw, setAddKw] = useState('');
  const [addModule, setAddModule] = useState('');
  const [addDept, setAddDept] = useState('');
  const [deptOptions, setDeptOptions] = useState([]);

  // 编辑弹窗状态
  const [editModal, setEditModal] = useState(false);
  const [editRecord, setEditRecord] = useState(null);
  const [editKw, setEditKw] = useState('');
  const [editModule, setEditModule] = useState('');
  const [editDept, setEditDept] = useState('');

  useEffect(() => {
    fetchDeptOptions().then(opts => setDeptOptions(opts));
  }, []);

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

  const openEdit = (record) => {
    setEditRecord(record);
    setEditKw(record.keyword || '');
    setEditModule(record.modules?.[0] || '');
    setEditDept(record.depts?.[0] || '');
    setEditModal(true);
  };

  const handleEdit = async () => {
    if (!editKw.trim() || !editModule.trim()) return;
    // 原地更新关键词，保留关联关系（文档/FAQ/报表等引用不中断）
    await fetch(
      `/api/keywords/update?old_keyword=${encodeURIComponent(editRecord.keyword)}` +
      `&old_module=${encodeURIComponent(editRecord.modules?.[0] || '')}` +
      `&new_keyword=${encodeURIComponent(editKw.trim())}` +
      `&new_module=${encodeURIComponent(editModule.trim())}` +
      `&new_dept=${encodeURIComponent(editDept.trim())}`
    );
    setEditModal(false);
    loadKeywords();
  };

  return (
    <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
      <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 12 }}>关键词管理</Text>
      {/* Add form */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <Input placeholder="关键词" value={addKw} onChange={e => setAddKw(e.target.value)} style={{ width: 150 }} />
        <div style={{ width: 180 }}>
          <ModuleSelect value={addModule} onChange={setAddModule} placeholder="模块（搜索或输入）" />
        </div>
        <div style={{ width: 160 }}>
          <AutoComplete
            value={addDept}
            onChange={setAddDept}
            options={deptOptions}
            placeholder="部门（搜索或输入）"
            filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())}
            style={{ width: '100%' }}
            allowClear
          />
        </div>
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
          {
            title: '操作', key: 'act', width: 100,
            render: (_, r) => (
              <div style={{ display: 'flex', gap: 4 }}>
                <Button type="link" size="small" style={{ fontSize: 12, padding: 0 }} onClick={() => openEdit(r)}>编辑</Button>
                <Button type="link" size="small" danger style={{ fontSize: 12, padding: 0 }} onClick={() => handleDelete(r.keyword)}>删除</Button>
              </div>
            ),
          },
        ]}
      />

      {/* 编辑弹窗 */}
      <Modal
        title="编辑关键词"
        open={editModal}
        onOk={handleEdit}
        onCancel={() => setEditModal(false)}
        okText="保存"
        cancelText="取消"
        width={450}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>关键词</Text>
            <Input value={editKw} onChange={e => setEditKw(e.target.value)} placeholder="关键词" />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>模块</Text>
            <ModuleSelect value={editModule} onChange={setEditModule} placeholder="模块（搜索或输入）" />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>部门</Text>
            <AutoComplete
              value={editDept}
              onChange={setEditDept}
              options={deptOptions}
              placeholder="部门（搜索或输入）"
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())}
              style={{ width: '100%' }}
              allowClear
            />
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default KeywordManager;