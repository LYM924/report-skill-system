/**
 * DeptBrowser.jsx - 部门知识浏览组件
 *
 * 左侧部门知识/业务模块点击后，在中间面板展示该部门下的文档表格
 * 支持编辑文档元数据（部门、产品模块、关键词）
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Table, Tag, Input, Button, Spin, Empty, Modal, AutoComplete, message } from 'antd';
import { SearchOutlined, EditOutlined } from '@ant-design/icons';
import ModuleSelect from './ModuleSelect';
import DeptCascader from './DeptCascader';

const { Text } = Typography;

function DeptBrowser({ deptId, deptName, dept, dept3, isDark, onSelectDoc }) {
  // 兼容旧 props：dept/dept3 作为 fallback
  const effectiveDeptId = deptId || '';
  const effectiveDeptName = deptName || dept3 || dept || '';
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');

  // 编辑弹窗
  const [editModal, setEditModal] = useState(false);
  const [editRecord, setEditRecord] = useState(null);
  const [editDept, setEditDept] = useState('');
  const [editDeptIds, setEditDeptIds] = useState([]);  // 部门ID数组
  const [editProduct, setEditProduct] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editFilename, setEditFilename] = useState('');
  const [saving, setSaving] = useState(false);

  const loadDocs = () => {
    setLoading(true);
    const params = new URLSearchParams({ page_size: '200' });
    if (effectiveDeptId) {
      params.set('dept_id', effectiveDeptId);
    }
    if (effectiveDeptName) {
      params.set('module', effectiveDeptName);
    }
    fetch(`/api/documents?${params.toString()}`)
      .then(r => r.json())
      .then(data => {
        setDocs(data?.documents || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadDocs(); }, [effectiveDeptId, effectiveDeptName]);

  const filteredDocs = searchFilter
    ? docs.filter(d => d.name.includes(searchFilter) || d.dept.includes(searchFilter))
    : docs;

  const openEdit = (record) => {
    setEditRecord(record);
    setEditDept(record.dept || '');
    setEditDeptIds([]);  // 从已有文档中难以恢复ID，暂为空
    setEditProduct(record.product || '');
    setEditKeywords((record.keywords || []).join(', '));
    setEditFilename(record.name || '');
    setEditModal(true);
  };

  const handleSave = async () => {
    if (!editRecord) return;
    setSaving(true);
    try {
      const params = new URLSearchParams({
        path: editRecord.path,
        dept: editDept,
        product: editProduct,
        keywords: editKeywords,
      });
      if (editDeptIds.length > 0) {
        params.set('dept_ids', editDeptIds.join(','));
      }
      if (editFilename && editFilename !== editRecord.name) {
        params.set('new_filename', editFilename);
      }
      const resp = await fetch(`/api/document/update?${params.toString()}`);
      const data = await resp.json();
      if (!resp.ok || data.error) throw new Error(data.error || '保存失败');
      message.success('文档元数据已更新，索引已刷新');
      setEditModal(false);
      loadDocs();
    } catch (err) {
      message.error(`保存失败: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const borderColor = isDark ? '#303030' : '#ebeef5';

  return (
    <div style={{ width: '100%' }}>
      <Card
        style={{ borderRadius: 12, border: `1px solid ${isDark ? '#303030' : '#e2e8f0'}`, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
        styles={{ body: { padding: '20px 24px' } }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <Text strong style={{ fontSize: 20, fontWeight: 600, color: isDark ? '#e5e5e5' : '#222' }}>
            {effectiveDeptName || effectiveDeptId}
          </Text>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ display: 'flex', border: `1px solid ${borderColor}`, borderRadius: 8, overflow: 'hidden' }}>
              <Input
                placeholder="搜索文档..."
                value={searchFilter}
                onChange={e => setSearchFilter(e.target.value)}
                style={{ border: 'none', width: 200, outline: 'none' }}
              />
              <Button type="text" icon={<SearchOutlined />} style={{ border: 'none', color: '#999' }} />
            </div>
            <Text type="secondary" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
              共 {filteredDocs.length} 条
            </Text>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : filteredDocs.length === 0 ? (
          <Empty description={searchFilter ? '无匹配文档' : '该部门暂无知识文档'} style={{ padding: '40px 0' }} />
        ) : (
          <Table
            dataSource={filteredDocs}
            rowKey="id"
            size="middle"
            pagination={{ pageSize: 15, size: 'small', showTotal: t => `共 ${t} 条` }}
            onRow={(record) => ({
              onClick: () => onSelectDoc({ ...record, title: record.name, path: record.path }),
              style: { cursor: 'pointer' },
            })}
            columns={[
              {
                title: '文档名称', dataIndex: 'name', key: 'name', width: '22%',
                render: text => <Text strong style={{ fontSize: 14, color: isDark ? '#e5e5e5' : '#303133' }}>{text}</Text>,
              },
              {
                title: '产品模块', dataIndex: 'product', key: 'product', width: 110,
                render: text => <span style={{ color: isDark ? '#bbb' : '#606266', whiteSpace: 'nowrap' }}>{text || '-'}</span>,
              },
              {
                title: '所属部门', dataIndex: 'dept', key: 'dept', width: 110,
                render: text => <span style={{ color: isDark ? '#bbb' : '#606266', whiteSpace: 'nowrap' }}>{text || '-'}</span>,
              },
              {
                title: '更新时间', dataIndex: 'updated', key: 'updated', width: 100,
                render: text => <span style={{ color: isDark ? '#bbb' : '#606266', whiteSpace: 'nowrap' }}>{text || '-'}</span>,
              },
              {
                title: '关键词', dataIndex: 'keywords', key: 'keywords', width: 150,
                render: arr => (arr || []).slice(0, 4).map(k => (
                  <Tag key={k} style={{ fontSize: 10, borderRadius: 4, margin: '1px 3px', background: 'rgba(13,148,136,0.06)', color: '#0D9488', border: 'none' }}>{k}</Tag>
                )),
              },
              {
                title: '操作', key: 'actions', width: 60,
                render: (_, record) => (
                  <Button type="link" size="small" icon={<EditOutlined />}
                    onClick={(e) => { e.stopPropagation(); openEdit(record); }}
                    style={{ fontSize: 12, padding: 0 }} />
                ),
              },
            ]}
            components={{
              header: {
                cell: (props) => (
                  <th {...props} style={{
                    ...props.style,
                    background: isDark ? '#252525' : '#f5f7fa',
                    color: isDark ? '#bbb' : '#606266',
                    fontWeight: 500,
                    fontSize: 14,
                    whiteSpace: 'nowrap',
                    padding: '12px 10px',
                  }} />
                ),
              },
            }}
          />
        )}
      </Card>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑文档元数据"
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        width={500}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>文档名称（可修改）</Text>
            <Input
              value={editFilename}
              onChange={e => setEditFilename(e.target.value)}
              placeholder="文档名称.md"
              suffix={<Text type="secondary" style={{ fontSize: 11 }}>.md</Text>}
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>所属部门</Text>
            <DeptCascader
              multiple
              value={editDeptIds}
              placeholder="选择部门（支持多选）"
              onChange={(ids, names) => {
                setEditDeptIds(ids);
                setEditDept(names.join(', '));
              }}
              style={{ width: '100%' }}
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>产品模块</Text>
            <ModuleSelect value={editProduct} onChange={setEditProduct} placeholder="搜索或输入模块名" />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>关键词（逗号分隔）</Text>
            <Input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} placeholder="如：报销, 审批, 预算" />
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default DeptBrowser;