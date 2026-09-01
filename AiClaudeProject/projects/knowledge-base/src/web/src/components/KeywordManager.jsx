/**
 * KeywordManager.jsx - 关键词管理组件
 *
 * 管理系统关键词映射，支持添加、编辑、删除关键词。
 * 使用 ID 方案：mapping_id 精准定位，dept_id 关联部门。
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../api';
import { Typography, Card, Table, Tag, Button, Input, Modal, message } from 'antd';
import ModuleSelect from './ModuleSelect';
import DeptCascader from './DeptCascader';
import { addKeyword, updateKeyword, deleteKeyword } from '../api';

const { Text } = Typography;

function KeywordManager() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // 添加表单
  const [addKw, setAddKw] = useState('');
  const [addModule, setAddModule] = useState('');
  const [addModuleId, setAddModuleId] = useState(0);
  const [addDeptIds, setAddDeptIds] = useState([]);
  const [addDeptNames, setAddDeptNames] = useState('');

  // 编辑弹窗
  const [editModal, setEditModal] = useState(false);
  const [editRecord, setEditRecord] = useState(null);
  const [editMappingId, setEditMappingId] = useState(0);
  const [editKw, setEditKw] = useState('');
  const [editModule, setEditModule] = useState('');
  const [editModuleId, setEditModuleId] = useState(0);
  const [editDeptIds, setEditDeptIds] = useState([]);
  const [editDeptNames, setEditDeptNames] = useState('');

  const loadKeywords = () => {
    setLoading(true);
    authFetch(`/api/keywords?q=${encodeURIComponent(search)}&page_size=200`)
      .then(r => r.json())
      .then(data => { setKeywords(data?.keywords || []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadKeywords(); }, []);

  const handleAdd = async () => {
    if (!addKw.trim() || !addModule.trim()) return;
    const deptId = addDeptIds.length > 0 ? addDeptIds[addDeptIds.length - 1] : 0;
    await addKeyword({
      keyword: addKw.trim(),
      module: addModule.trim(),
      module_id: addModuleId,
      dept_id: deptId,
      dept: addDeptNames,
    });
    setAddKw(''); setAddModule(''); setAddModuleId(0); setAddDeptIds([]); setAddDeptNames('');
    loadKeywords();
  };

  const handleDelete = async (record) => {
    // 删除该关键词的第一个映射（可通过 mapping_id 精准删除）
    const mapping = record.mappings?.[0];
    if (mapping?.mapping_id) {
      await deleteKeyword({ mapping_id: mapping.mapping_id });
    } else {
      // 回退：删除整个关键词
      const kwId = record.mappings?.[0]?.keyword_id;
      if (kwId) await deleteKeyword({ keyword_id: kwId });
    }
    loadKeywords();
  };

  const openEdit = (record) => {
    const mapping = record.mappings?.[0] || {};
    setEditRecord(record);
    setEditMappingId(mapping.mapping_id || 0);
    setEditKw(record.keyword || '');
    setEditModule(mapping.module || record.modules?.[0] || '');
    setEditModuleId(mapping.module_id || 0);
    setEditDeptIds(mapping.dept_id ? [mapping.dept_id] : []);
    setEditDeptNames(mapping.dept || record.depts?.[0] || '');
    setEditModal(true);
  };

  const handleEdit = async () => {
    if (!editKw.trim() || !editModule.trim()) return;
    const deptId = editDeptIds.length > 0 ? editDeptIds[editDeptIds.length - 1] : 0;
    await updateKeyword({
      mapping_id: editMappingId,
      keyword: editKw.trim(),
      module: editModule.trim(),
      module_id: editModuleId,
      dept_id: deptId,
      dept: editDeptNames,
    });
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
          <ModuleSelect
            value={addModule}
            onChange={(name, id) => { setAddModule(name); setAddModuleId(id || 0); }}
            placeholder="模块（搜索或输入）"
          />
        </div>
        <div style={{ width: 200 }}>
          <DeptCascader
            value={addDeptIds}
            onChange={(ids, names) => { setAddDeptIds(ids); setAddDeptNames(names.join(' > ')); }}
            placeholder="选择部门"
            style={{ width: '100%' }}
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
                <Button type="link" size="small" danger style={{ fontSize: 12, padding: 0 }} onClick={() => handleDelete(r)}>删除</Button>
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
        width={480}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>关键词</Text>
            <Input value={editKw} onChange={e => setEditKw(e.target.value)} placeholder="关键词" />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>模块</Text>
            <ModuleSelect
              value={editModule}
              onChange={(name, id) => { setEditModule(name); setEditModuleId(id || 0); }}
              placeholder="模块（搜索或输入）"
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>部门</Text>
            <DeptCascader
              value={editDeptIds}
              onChange={(ids, names) => { setEditDeptIds(ids); setEditDeptNames(names.join(' > ')); }}
              placeholder="选择部门"
              style={{ width: '100%' }}
            />
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default KeywordManager;