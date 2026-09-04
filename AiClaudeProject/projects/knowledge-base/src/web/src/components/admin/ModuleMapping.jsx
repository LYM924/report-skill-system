/**
 * ModuleMapping.jsx - 模块关联映射管理
 *
 * 功能：
 *   - 模块列表（搜索/筛选/分页）
 *   - 编辑弹窗（修改关联 → 级联预览 → 确认保存）
 *   - 查看详情弹窗
 *   - 业务域管理 Tab
 *   - 废弃/恢复操作
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Input, Select, Tag, Modal, Form, Space, Tooltip,
  Cascader, message, Tabs, Descriptions, Badge, Popconfirm, Empty, Spin,
} from 'antd';
import {
  PlusOutlined, EditOutlined, EyeOutlined, StopOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, AppstoreOutlined,
  TagOutlined, ApartmentOutlined, SaveOutlined,
} from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';
import { useAppContext } from '../AppContext';

const { Search } = Input;

// 状态映射
const STATUS_MAP = { 0: { text: '草稿', color: 'default' }, 1: { text: '正常', color: 'green' }, 2: { text: '废弃', color: 'red' } };

export default function ModuleMapping() {
  const { isDark } = useAppContext();
  const [modules, setModules] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [productLines, setProductLines] = useState([]);
  const [domains, setDomains] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [products, setProducts] = useState([]);
  const [filterPL, setFilterPL] = useState(0);
  const [filterDomain, setFilterDomain] = useState(0);
  const [filterStatus, setFilterStatus] = useState(-1);

  // 编辑弹窗
  const [editVisible, setEditVisible] = useState(false);
  const [editModule, setEditModule] = useState(null);
  const [editForm] = Form.useForm();
  const [cascadePreview, setCascadePreview] = useState(null);
  const [saving, setSaving] = useState(false);

  // 详情弹窗
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailModule, setDetailModule] = useState(null);

  // 加载下拉选项
  useEffect(() => {
    authFetch('/api/mapping/product-lines').then(r => r.json()).then(d => setProductLines(d.product_lines || []));
    authFetch('/api/mapping/domains').then(r => r.json()).then(d => setDomains(d.domains || []));
    authFetch('/api/mapping/departments').then(r => r.json()).then(d => {
      // 转换为 Cascader 树
      const tree = buildDeptTree(d.departments || []);
      setDepartments(tree);
    });
    authFetch('/api/mapping/products').then(r => r.json()).then(d => setProducts(d.products || []));
  }, []);

  // 加载模块列表
  const fetchModules = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ q, page, page_size: pageSize });
      if (filterPL) params.set('product_line_id', filterPL);
      if (filterDomain) params.set('domain_id', filterDomain);
      if (filterStatus >= 0) params.set('status', filterStatus);
      const res = await authFetch(`/api/mapping/modules?${params}`);
      const data = await res.json();
      setModules(data.modules || []);
      setTotal(data.total || 0);
    } catch (e) { message.error('加载失败'); }
    setLoading(false);
  }, [q, page, pageSize, filterPL, filterDomain, filterStatus]);

  useEffect(() => { fetchModules(); }, [fetchModules]);

  // 构建部门树（供 Cascader 多选用）
  const buildDeptTree = (rows) => {
    const map = {};
    rows.forEach(r => { map[r.id] = { ...r, value: r.id, label: r.name, children: [] }; });
    const roots = [];
    rows.forEach(r => {
      if (r.parent_id && map[r.parent_id]) map[r.parent_id].children.push(map[r.id]);
      else roots.push(map[r.id]);
    });
    return roots;
  };

  // ──── 编辑弹窗操作 ────

  const openEdit = async (mod) => {
    // 获取完整详情
    const res = await authFetch(`/api/mapping/modules/${mod.id}`);
    const detail = await res.json();
    setEditModule(detail);
    editForm.setFieldsValue({
      name: detail.name,
      product_id: detail.product_id,
      department_id: detail.department_id,
      dept_ids: detail.dept_ids || [],
      domain_ids: detail.domain_ids || [],
      dev_owner: detail.dev_owner,
      module_owner: detail.module_owner,
    });
    setCascadePreview(null);
    setEditVisible(true);
  };

  const handlePreview = async () => {
    try {
      const values = editForm.getFieldsValue();
      const changes = {};
      if (values.product_id !== editModule.product_id) changes.product_id = values.product_id;
      if (values.department_id !== editModule.department_id) changes.department_id = values.department_id;
      if (JSON.stringify(values.dept_ids || []) !== JSON.stringify(editModule.dept_ids || [])) changes.dept_ids = values.dept_ids;
      if (JSON.stringify(values.domain_ids || []) !== JSON.stringify(editModule.domain_ids || [])) changes.domain_ids = values.domain_ids;
      if (!Object.keys(changes).length) { message.info('无变更'); return; }
      const res = await authFetch('/api/mapping/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module_id: editModule.id, changes }),
      });
      const data = await res.json();
      setCascadePreview(data);
    } catch (e) { message.error('预览失败'); }
  };

  const handleSave = async () => {
    try {
      const values = editForm.getFieldsValue();
      const body = {};
      // 只传有变更的字段
      if (values.name && values.name !== editModule.name) body.name = values.name;
      if (values.product_id !== editModule.product_id) body.product_id = values.product_id;
      if (values.department_id !== editModule.department_id) body.department_id = values.department_id;
      if (JSON.stringify(values.dept_ids || []) !== JSON.stringify(editModule.dept_ids || [])) body.dept_ids = values.dept_ids;
      if (JSON.stringify(values.domain_ids || []) !== JSON.stringify(editModule.domain_ids || [])) body.domain_ids = values.domain_ids;
      if (values.dev_owner !== editModule.dev_owner) body.dev_owner = values.dev_owner;
      if (values.module_owner !== editModule.module_owner) body.module_owner = values.module_owner;
      if (!Object.keys(body).length) { message.info('无变更'); return; }

      setSaving(true);
      const res = await authFetch(`/api/mapping/modules/${editModule.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.ok) {
        message.success('保存成功');
        setEditVisible(false);
        fetchModules();
      } else {
        message.error(data.error || '保存失败');
      }
    } catch (e) { message.error('保存失败'); }
    setSaving(false);
  };

  // ──── 查看详情 ────

  const openDetail = async (mod) => {
    const res = await authFetch(`/api/mapping/modules/${mod.id}`);
    const data = await res.json();
    setDetailModule(data);
    setDetailVisible(true);
  };

  // ──── 废弃/恢复 ────

  const handleStatusChange = async (moduleId, newStatus) => {
    try {
      const res = await authFetch(`/api/mapping/modules/${moduleId}/status`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      const data = await res.json();
      if (data.ok) {
        message.success(newStatus === 2 ? '已废弃' : '已恢复');
        fetchModules();
      } else { message.error(data.error || '操作失败'); }
    } catch (e) { message.error('操作失败'); }
  };

  // ──── 业务域管理 ────

  const [domainName, setDomainName] = useState('');
  const [domainCode, setDomainCode] = useState('');
  const handleAddDomain = async () => {
    if (!domainName.trim()) return;
    try {
      const res = await authFetch('/api/mapping/domains', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: domainName.trim(), code: domainCode.trim() }),
      });
      const data = await res.json();
      if (data.ok) {
        message.success('业务域已添加');
        setDomainName('');
        setDomainCode('');
        // 刷新
        const d = await authFetch('/api/mapping/domains').then(r => r.json());
        setDomains(d.domains || []);
      } else { message.error(data.error || '添加失败'); }
    } catch (e) { message.error('添加失败'); }
  };

  const handleDeleteDomain = async (id) => {
    try {
      const res = await authFetch(`/api/mapping/domains/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.ok) {
        message.success('已删除');
        const d = await authFetch('/api/mapping/domains').then(r => r.json());
        setDomains(d.domains || []);
      } else { message.error(data.error || '删除失败'); }
    } catch (e) { message.error('删除失败'); }
  };

  // ──── 表格列 ────

  const columns = [
    { title: '模块名称', dataIndex: 'name', key: 'name', width: 160,
      render: (t, r) => <Space><span style={{ fontWeight: 500 }}>{t}</span>
        {r.status === 2 && <Tag color="red">废弃</Tag>}</Space> },
    { title: '所属产品', dataIndex: 'product_name', key: 'product', width: 140,
      render: t => t || <span style={{ color: '#94a3b8' }}>未关联</span> },
    { title: '产品线', dataIndex: 'product_line_name', key: 'product_line', width: 100,
      render: t => t || '-' },
    { title: '业务域', dataIndex: 'domain_summary', key: 'domain', width: 120,
      render: t => t || '-' },
    { title: '关联部门', dataIndex: 'dept_summary', key: 'depts', width: 180,
      render: (t, r) => t ? <Tooltip title={t}>{t.length > 20 ? t.slice(0, 20) + '...' : t}{r.dept_count > 5 ? `等${r.dept_count}个` : ''}</Tooltip> : '-' },
    { title: '模块负责人', dataIndex: 'module_owner', key: 'module_owner', width: 90 },
    { title: '研发负责人', dataIndex: 'dev_owner', key: 'dev_owner', width: 90 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 70,
      render: s => { const m = STATUS_MAP[s] || STATUS_MAP[1]; return <Badge status={m.color} text={m.text} />; } },
    { title: '操作', key: 'actions', width: 200, fixed: 'right',
      render: (_, r) => <Space size={4}>
        <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => openDetail(r)}>查看</Button>
        <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>修改</Button>
        {r.status === 1 ? (
          <Popconfirm title="确认废弃该模块？" onConfirm={() => handleStatusChange(r.id, 2)}>
            <Button size="small" type="link" danger icon={<StopOutlined />}>废弃</Button>
          </Popconfirm>
        ) : r.status === 2 ? (
          <Button size="small" type="link" icon={<CheckCircleOutlined />} onClick={() => handleStatusChange(r.id, 1)}>恢复</Button>
        ) : null}
      </Space>,
    },
  ];

  // 筛选产品（按产品线）
  const filteredProducts = filterPL ? products.filter(p => p.product_line_id === filterPL) : products;

  return (
    <AdminShell title="模块关联映射管理" description="管理模块与部门、产品、产品线、业务域的关联映射，修改后自动级联更新所有关联数据">
      <Tabs items={[
        { key: 'modules', label: <span><AppstoreOutlined /> 模块管理</span>, children: (
          <div>
            {/* 筛选栏 */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <Search placeholder="搜索模块名称" allowClear style={{ width: 200 }} onSearch={v => { setQ(v); setPage(1); }} />
              <Select placeholder="产品线" allowClear style={{ width: 140 }} value={filterPL || undefined}
                onChange={v => { setFilterPL(v || 0); setPage(1); }}
                options={productLines.map(pl => ({ value: pl.id, label: pl.name }))} />
              <Select placeholder="业务域" allowClear style={{ width: 140 }} value={filterDomain || undefined}
                onChange={v => { setFilterDomain(v || 0); setPage(1); }}
                options={domains.map(d => ({ value: d.id, label: d.name }))} />
              <Select placeholder="状态" allowClear style={{ width: 100 }} value={filterStatus >= 0 ? filterStatus : undefined}
                onChange={v => { setFilterStatus(v ?? -1); setPage(1); }}
                options={[{ value: 1, label: '正常' }, { value: 2, label: '废弃' }, { value: 0, label: '草稿' }]} />
            </div>

            {/* 表格 */}
            <Table columns={columns} dataSource={modules} rowKey="id" loading={loading}
              size="small" scroll={{ x: 1200 }}
              pagination={{ current: page, pageSize, total, showSizeChanger: false, showTotal: t => `共 ${t} 个模块`,
                onChange: (p, ps) => { setPage(p); setPageSize(ps); } }} />
          </div>
        )},
        { key: 'domains', label: <span><TagOutlined /> 业务域管理</span>, children: (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <Input placeholder="新业务域名称" value={domainName} onChange={e => setDomainName(e.target.value)} style={{ width: 200 }} />
              <Input placeholder="编码(可选)" value={domainCode} onChange={e => setDomainCode(e.target.value)} style={{ width: 120 }} />
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAddDomain}>添加</Button>
            </div>
            <Table dataSource={domains} rowKey="id" size="small" pagination={false}
              columns={[
                { title: '业务域名称', dataIndex: 'name' },
                { title: '编码', dataIndex: 'code', render: t => t || '-' },
                { title: '关联模块数', dataIndex: 'module_count', width: 100 },
                { title: '操作', width: 80, render: (_, r) =>
                  r.module_count === 0 ? <Popconfirm title="确认删除？" onConfirm={() => handleDeleteDomain(r.id)}><Button size="small" type="link" danger>删除</Button></Popconfirm>
                  : <Tooltip title="该域下有模块关联，无法删除"><span style={{ color: '#94a3b8' }}>删除</span></Tooltip> },
              ]} />
          </div>
        )},
      ]} />

      {/* ──── 编辑弹窗 ──── */}
      <Modal title="修改模块关联" open={editVisible} onCancel={() => setEditVisible(false)} width={640}
        footer={<Space>
          <Button onClick={() => setEditVisible(false)}>取消</Button>
          <Button onClick={handlePreview} icon={<ExclamationCircleOutlined />}>预览级联影响</Button>
          <Button type="primary" onClick={handleSave} loading={saving} icon={<SaveOutlined />}>确认保存</Button>
        </Space>}>
        {editModule && <Form form={editForm} layout="vertical" size="small">
          <Form.Item label="模块名称" name="name"><Input /></Form.Item>
          <Form.Item label="所属产品" name="product_id">
            <Select allowClear showSearch optionFilterProp="label" placeholder="选择产品"
              options={filteredProducts.map(p => ({ value: p.id, label: p.name }))} />
          </Form.Item>
          <Form.Item label="L2 部门" name="department_id">
            <Select allowClear showSearch optionFilterProp="label" placeholder="选择二级部门"
              options={buildDeptFlat(departments).map(d => ({ value: d.id, label: `${'　'.repeat(d.level - 1)}${d.name}` }))} />
          </Form.Item>
          <Form.Item label="关联 L3 部门（多选）" name="dept_ids">
            <Select mode="multiple" allowClear showSearch optionFilterProp="label" placeholder="选择关联的L3部门"
              options={buildDeptFlat(departments).filter(d => d.level >= 2).map(d => ({ value: d.id, label: `${'　'.repeat(d.level - 1)}${d.name}` }))} />
          </Form.Item>
          <Form.Item label="业务域（多选）" name="domain_ids">
            <Select mode="multiple" allowClear placeholder="选择业务域"
              options={domains.map(d => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item label="模块负责人" name="module_owner"><Input /></Form.Item>
          <Form.Item label="研发负责人" name="dev_owner"><Input /></Form.Item>
        </Form>}

        {/* 级联预览 */}
        {cascadePreview && <div style={{ marginTop: 16, padding: 12, borderRadius: 8,
          background: isDark ? '#1a1a1a' : '#f8fafc', border: `1px solid ${isDark ? '#303030' : '#e2e8f0'}` }}>
          <div style={{ fontWeight: 500, marginBottom: 8, color: '#f59e0b' }}>⚡ 级联影响预览</div>
          <Space size={16}>
            {cascadePreview.affected_documents > 0 && <span>📄 文档: {cascadePreview.affected_documents} 篇</span>}
            {cascadePreview.affected_faqs > 0 && <span>❓ FAQ: {cascadePreview.affected_faqs} 篇</span>}
            {cascadePreview.affected_keyword_mappings > 0 && <span>🔑 关键词: {cascadePreview.affected_keyword_mappings} 个</span>}
            {cascadePreview.affected_document_departments > 0 && <span>📁 部门关联: {cascadePreview.affected_document_departments} 条</span>}
            {Object.values(cascadePreview).every(v => !v) && <span style={{ color: '#94a3b8' }}>无级联影响</span>}
          </Space>
        </div>}
      </Modal>

      {/* ──── 详情弹窗 ──── */}
      <Modal title={detailModule ? `模块详情: ${detailModule.name}` : '模块详情'}
        open={detailVisible} onCancel={() => setDetailVisible(false)} width={600} footer={null}>
        {detailModule && <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="模块名称" span={2}>{detailModule.name}</Descriptions.Item>
          <Descriptions.Item label="所属产品">{detailModule.product_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="产品线">{detailModule.product_line_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="L2部门">{detailModule.dept_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Badge status={(STATUS_MAP[detailModule.status] || STATUS_MAP[1]).color}
              text={(STATUS_MAP[detailModule.status] || STATUS_MAP[1]).text} />
          </Descriptions.Item>
          <Descriptions.Item label="模块负责人">{detailModule.module_owner || '-'}</Descriptions.Item>
          <Descriptions.Item label="研发负责人">{detailModule.dev_owner || '-'}</Descriptions.Item>
          <Descriptions.Item label="L3关联部门" span={2}>
            {detailModule.dept_names?.length ? detailModule.dept_names.map((n, i) =>
              <Tag key={i} color={i === 0 ? 'blue' : 'default'}>{n}{i === 0 ? ' (主)' : ''}</Tag>
            ) : <span style={{ color: '#94a3b8' }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="业务域" span={2}>
            {detailModule.domain_names?.length ? detailModule.domain_names.map((n, i) =>
              <Tag key={i} color="cyan">{n}</Tag>
            ) : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="关联数据" span={2}>
            <Space>
              {detailModule.stats?.doc_count > 0 && <span>📄 文档 {detailModule.stats.doc_count} 篇</span>}
              {detailModule.stats?.faq_count > 0 && <span>❓ FAQ {detailModule.stats.faq_count} 篇</span>}
              {detailModule.stats?.kw_count > 0 && <span>🔑 关键词 {detailModule.stats.kw_count} 个</span>}
            </Space>
          </Descriptions.Item>
        </Descriptions>}
      </Modal>
    </AdminShell>
  );
}

// 辅助：扁平化部门树（供 Select 使用）
function buildDeptFlat(tree, result = []) {
  tree.forEach(node => {
    result.push({ id: node.value || node.id, name: node.label || node.name, level: node.level || 1 });
    if (node.children?.length) buildDeptFlat(node.children, result);
  });
  return result;
}
