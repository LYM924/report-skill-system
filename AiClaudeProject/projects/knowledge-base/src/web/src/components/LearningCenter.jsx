/**
 * LearningCenter.jsx - 学习中心管理面板
 *
 * 展示学习候选池，管理员可审核通过（沉淀为FAQ）或拒绝。
 * 包含统计卡片、候选列表、审核操作。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Typography, Card, Tag, Button, Modal, Input, Space, Empty, Spin, message, Tooltip, Badge, Select } from 'antd';
import { BookOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, RobotOutlined, UserOutlined, ThunderboltOutlined, HistoryOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  getLearningCandidates, getLearningStats,
  approveLearningCandidate, rejectLearningCandidate, expireLearningCandidates,
} from '../api';

const { Text, Paragraph } = Typography;

// 柔和浅青绿色系（与 ChatMode 一致）
const COLORS = {
  primary: '#5B9A8B',
  primaryLight: '#E8F4F1',
  primaryHover: '#4A8A7C',
  cardBg: '#fafbfc',
  divider: '#eef0f2',
  text: '#334155',
  textSecondary: '#94a3b8',
  border: '#eef0f2',
  shadow: '0 1px 3px rgba(0,0,0,0.04)',
  white: '#fff',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
};

const STATUS_CONFIG = {
  0: { label: '待审核', color: 'orange', icon: <ClockCircleOutlined /> },
  1: { label: '已通过', color: 'green', icon: <CheckCircleOutlined /> },
  2: { label: '已拒绝', color: 'red', icon: <CloseCircleOutlined /> },
  3: { label: '已过期', color: 'default', icon: <HistoryOutlined /> },
};

const SOURCE_CONFIG = {
  ai_answer: { label: 'AI 回答', icon: <RobotOutlined />, color: '#5B9A8B' },
  ai_extract: { label: 'AI 提取', icon: <ThunderboltOutlined />, color: '#6366f1' },
  user_feedback: { label: '用户反馈', icon: <UserOutlined />, color: '#f59e0b' },
  manual: { label: '手动提交', icon: <BookOutlined />, color: '#3b82f6' },
};

function LearningCenter({ isDark }) {
  const [candidates, setCandidates] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, expired: 0, total: 0, week_approved: 0 });
  const [statusFilter, setStatusFilter] = useState(0); // 默认显示待审核
  const [editModal, setEditModal] = useState({ open: false, candidate: null });
  const [rejectModal, setRejectModal] = useState({ open: false, candidate: null });
  const [rejectNote, setRejectNote] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // 编辑表单
  const [editForm, setEditForm] = useState({ title: '', summary: '', dept: '', module: '', keywords: '' });

  const theme = isDark ? {
    ...COLORS,
    cardBg: '#1e1e1e',
    text: '#e5e5e5',
    textSecondary: '#888',
    border: '#303030',
    divider: '#303030',
    shadow: 'none',
    white: '#1a1a1a',
  } : COLORS;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [candsRes, statsRes] = await Promise.all([
        getLearningCandidates(statusFilter, page, 20),
        getLearningStats(),
      ]);
      if (candsRes) {
        setCandidates(candsRes.candidates || []);
        setTotal(candsRes.total || 0);
      }
      if (statsRes) {
        setStats(statsRes);
      }
    } catch (e) {
      console.error('加载学习中心失败:', e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 审核通过（带编辑）
  const handleApprove = async () => {
    if (!editModal.candidate) return;
    setActionLoading(true);
    try {
      const edits = {};
      if (editForm.title) edits.title = editForm.title;
      if (editForm.summary) edits.summary = editForm.summary;
      if (editForm.dept) edits.dept = editForm.dept;
      if (editForm.module) edits.module = editForm.module;
      if (editForm.keywords) {
        try {
          edits.keywords = editForm.keywords.split(',').map(k => k.trim()).filter(Boolean);
        } catch { /* ignore */ }
      }
      const res = await approveLearningCandidate(editModal.candidate.id, edits);
      if (res?.ok) {
        message.success(`已沉淀为 FAQ: ${res.faq_id}`);
        setEditModal({ open: false, candidate: null });
        loadData();
      } else {
        message.error(res?.error || '审核通过失败');
      }
    } catch (e) {
      message.error('操作失败: ' + e.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 快速通过（不编辑）
  const handleQuickApprove = async (candidate) => {
    setActionLoading(true);
    try {
      const res = await approveLearningCandidate(candidate.id, {});
      if (res?.ok) {
        message.success(`已沉淀为 FAQ: ${res.faq_id}`);
        loadData();
      } else {
        message.error(res?.error || '审核通过失败');
      }
    } catch (e) {
      message.error('操作失败: ' + e.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 审核拒绝
  const handleReject = async () => {
    if (!rejectModal.candidate) return;
    setActionLoading(true);
    try {
      const res = await rejectLearningCandidate(rejectModal.candidate.id, rejectNote);
      if (res?.ok) {
        message.success('已拒绝');
        setRejectModal({ open: false, candidate: null });
        setRejectNote('');
        loadData();
      } else {
        message.error(res?.error || '拒绝失败');
      }
    } catch (e) {
      message.error('操作失败: ' + e.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 清理过期
  const handleExpire = async () => {
    try {
      const res = await expireLearningCandidates(30);
      if (res?.ok) {
        message.success(`已过期 ${res.expired_count || 0} 条候选`);
        loadData();
      }
    } catch (e) {
      message.error('清理失败: ' + e.message);
    }
  };

  // 打开编辑弹窗
  const openEditModal = (candidate) => {
    setEditForm({
      title: candidate.query || '',
      summary: candidate.summary || candidate.answer?.slice(0, 300) || '',
      dept: candidate.dept || '',
      module: candidate.module || '',
      keywords: (candidate.keywords || []).join(', '),
    });
    setEditModal({ open: true, candidate });
  };

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '0 8px' }}>
      {/* ===== 统计卡片 ===== */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { label: '待审核', value: stats.pending, color: COLORS.warning, icon: <ClockCircleOutlined /> },
          { label: '已通过', value: stats.approved, color: COLORS.success, icon: <CheckCircleOutlined /> },
          { label: '已拒绝', value: stats.rejected, color: COLORS.danger, icon: <CloseCircleOutlined /> },
          { label: '本周沉淀', value: stats.week_approved, color: COLORS.primary, icon: <ThunderboltOutlined /> },
          { label: '总计', value: stats.total, color: COLORS.textSecondary, icon: <BookOutlined /> },
        ].map((item, i) => (
          <div key={i} style={{
            background: theme.cardBg,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: '14px 16px',
            boxShadow: theme.shadow,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ color: item.color, fontSize: 16 }}>{item.icon}</span>
              <Text style={{ fontSize: 12, color: theme.textSecondary }}>{item.label}</Text>
            </div>
            <Text strong style={{ fontSize: 24, color: item.color }}>{item.value}</Text>
          </div>
        ))}
      </div>

      {/* ===== 筛选栏 ===== */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
        flexWrap: 'wrap',
      }}>
        <Text strong style={{ fontSize: 15, color: theme.text }}>学习候选</Text>
        <Select
          value={statusFilter}
          onChange={val => { setStatusFilter(val); setPage(1); }}
          style={{ width: 120 }}
          options={[
            { value: 0, label: '待审核' },
            { value: 1, label: '已通过' },
            { value: 2, label: '已拒绝' },
            { value: 3, label: '已过期' },
            { value: null, label: '全部' },
          ]}
        />
        <div style={{ flex: 1 }} />
        <Tooltip title="清理30天以上未审核的候选">
          <Button size="small" icon={<DeleteOutlined />} onClick={handleExpire}>
            清理过期
          </Button>
        </Tooltip>
        <Button size="small" icon={<ReloadOutlined />} onClick={loadData}>
          刷新
        </Button>
      </div>

      {/* ===== 候选列表 ===== */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
          <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>加载中...</Text>
        </div>
      ) : candidates.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={statusFilter === 0 ? '暂无待审核的学习候选' : '暂无数据'}
          style={{ marginTop: 40 }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {candidates.map((c) => {
            const statusConf = STATUS_CONFIG[c.status] || STATUS_CONFIG[0];
            const sourceConf = SOURCE_CONFIG[c.source] || SOURCE_CONFIG.manual;
            const isPending = c.status === 0;

            return (
              <div key={c.id} style={{
                background: theme.cardBg,
                border: `1px solid ${isPending ? '#f59e0b33' : theme.border}`,
                borderLeft: isPending ? `3px solid ${COLORS.warning}` : `3px solid transparent`,
                borderRadius: 10,
                padding: '16px 20px',
                boxShadow: theme.shadow,
                transition: 'all 0.2s',
              }}>
                {/* 标题行 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <span style={{ color: sourceConf.color, fontSize: 14 }}>{sourceConf.icon}</span>
                  <Text style={{ fontSize: 12, color: sourceConf.color }}>{sourceConf.label}</Text>
                  <Tag color={statusConf.color} style={{ fontSize: 11, margin: 0, lineHeight: '18px' }}>
                    {statusConf.label}
                  </Tag>
                  {c.faq_code && (
                    <Tag color="green" style={{ fontSize: 11, margin: 0 }}>→ {c.faq_code}</Tag>
                  )}
                  <div style={{ flex: 1 }} />
                  <Text type="secondary" style={{ fontSize: 11 }}>{c.create_time?.slice(0, 10)}</Text>
                </div>

                {/* 问题 */}
                <div style={{ marginBottom: 8 }}>
                  <Text strong style={{ fontSize: 14, color: theme.text }}>❓ {c.query}</Text>
                </div>

                {/* AI 提取的摘要（如果有） */}
                {c.summary && (
                  <div style={{
                    background: theme.white,
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    padding: '10px 14px',
                    marginBottom: 8,
                  }}>
                    <Text style={{ fontSize: 12, color: COLORS.primary, fontWeight: 600 }}>
                      💡 AI 提取摘要
                    </Text>
                    <Paragraph
                      ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                      style={{ fontSize: 13, color: theme.text, margin: '4px 0 0', lineHeight: 1.7 }}
                    >
                      {c.summary}
                    </Paragraph>
                  </div>
                )}

                {/* 原始回答（折叠显示） */}
                {!c.summary && c.answer && (
                  <div style={{ marginBottom: 8 }}>
                    <Paragraph
                      ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                      style={{ fontSize: 13, color: theme.textSecondary, margin: 0, lineHeight: 1.6 }}
                    >
                      {c.answer}
                    </Paragraph>
                  </div>
                )}

                {/* 归属信息 */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                  {c.dept && (
                    <Tag style={{ fontSize: 11, margin: 0, background: COLORS.primaryLight, color: COLORS.primary, border: 'none' }}>
                      🏢 {c.dept}
                    </Tag>
                  )}
                  {c.module && (
                    <Tag style={{ fontSize: 11, margin: 0, background: '#f0f0f0', color: theme.text, border: 'none' }}>
                      📦 {c.module}
                    </Tag>
                  )}
                  {(c.keywords || []).map((kw, ki) => (
                    <Tag key={ki} style={{ fontSize: 10, margin: 0 }}>{kw}</Tag>
                  ))}
                </div>

                {/* 操作按钮（仅待审核状态） */}
                {isPending && (
                  <div style={{ display: 'flex', gap: 8, paddingTop: 8, borderTop: `1px solid ${theme.divider}` }}>
                    <Button
                      size="small"
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleQuickApprove(c)}
                      loading={actionLoading}
                      style={{ background: COLORS.primary, borderColor: COLORS.primary, borderRadius: 6 }}
                    >
                      快速通过
                    </Button>
                    <Button
                      size="small"
                      icon={<BookOutlined />}
                      onClick={() => openEditModal(c)}
                      style={{ borderRadius: 6 }}
                    >
                      编辑并通过
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={() => { setRejectModal({ open: true, candidate: c }); setRejectNote(''); }}
                      style={{ borderRadius: 6 }}
                    >
                      拒绝
                    </Button>
                  </div>
                )}

                {/* 已审核信息 */}
                {!isPending && c.reviewed_by && (
                  <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 4 }}>
                    {c.reviewed_by} · {c.reviewed_at?.slice(0, 10)}
                    {c.review_note && ` · "${c.review_note}"`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ===== 分页 ===== */}
      {total > 20 && (
        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Space>
            <Button size="small" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
            <Text type="secondary" style={{ fontSize: 12 }}>第 {page} 页 / 共 {Math.ceil(total / 20)} 页</Text>
            <Button size="small" disabled={page >= Math.ceil(total / 20)} onClick={() => setPage(p => p + 1)}>下一页</Button>
          </Space>
        </div>
      )}

      {/* ===== 编辑弹窗 ===== */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOutlined style={{ color: COLORS.primary }} />
            <span>编辑并沉淀为 FAQ</span>
          </div>
        }
        open={editModal.open}
        onOk={handleApprove}
        onCancel={() => setEditModal({ open: false, candidate: null })}
        okText="审核通过并沉淀"
        cancelText="取消"
        confirmLoading={actionLoading}
        width={600}
        okButtonProps={{ style: { background: COLORS.primary, borderColor: COLORS.primary } }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>FAQ 标题</Text>
            <Input
              value={editForm.title}
              onChange={e => setEditForm(prev => ({ ...prev, title: e.target.value }))}
              placeholder="简明标题"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>知识摘要</Text>
            <Input.TextArea
              value={editForm.summary}
              onChange={e => setEditForm(prev => ({ ...prev, summary: e.target.value }))}
              placeholder="核心知识点，去除对话套话"
              autoSize={{ minRows: 3, maxRows: 8 }}
              style={{ marginTop: 4 }}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>归属部门</Text>
              <Input
                value={editForm.dept}
                onChange={e => setEditForm(prev => ({ ...prev, dept: e.target.value }))}
                placeholder="如：数智财务组"
                style={{ marginTop: 4 }}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>归属模块</Text>
              <Input
                value={editForm.module}
                onChange={e => setEditForm(prev => ({ ...prev, module: e.target.value }))}
                placeholder="如：浙里报"
                style={{ marginTop: 4 }}
              />
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>关键词（逗号分隔）</Text>
            <Input
              value={editForm.keywords}
              onChange={e => setEditForm(prev => ({ ...prev, keywords: e.target.value }))}
              placeholder="如：报销单, 审批, 流程"
              style={{ marginTop: 4 }}
            />
          </div>
        </div>
      </Modal>

      {/* ===== 拒绝弹窗 ===== */}
      <Modal
        title="拒绝学习候选"
        open={rejectModal.open}
        onOk={handleReject}
        onCancel={() => { setRejectModal({ open: false, candidate: null }); setRejectNote(''); }}
        okText="确认拒绝"
        cancelText="取消"
        confirmLoading={actionLoading}
        okButtonProps={{ danger: true }}
      >
        <Text style={{ fontSize: 13, color: theme.text }}>
          确定拒绝「{rejectModal.candidate?.query?.slice(0, 50)}」？
        </Text>
        <Input.TextArea
          value={rejectNote}
          onChange={e => setRejectNote(e.target.value)}
          placeholder="拒绝原因（可选）"
          autoSize={{ minRows: 2, maxRows: 4 }}
          style={{ marginTop: 12 }}
        />
      </Modal>
    </div>
  );
}

export default LearningCenter;
