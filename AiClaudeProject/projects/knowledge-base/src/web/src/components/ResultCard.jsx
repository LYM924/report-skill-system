/**
 * ResultCard.jsx - 搜索结果卡片
 *
 * 展示单条搜索结果的卡片组件，包含类型图标、标题、摘要片段和面包屑导航。
 * 支持关键词高亮显示和搜索反馈。
 */
import React, { useState } from 'react';
import { Typography, Tag, Button, message, Tooltip } from 'antd';
import { QuestionCircleOutlined, FileTextOutlined, BarChartOutlined, LikeOutlined, DislikeOutlined } from '@ant-design/icons';
import { sendFeedback } from '../api';

const { Text, Paragraph } = Typography;

/** 结果类型图标和颜色 */
const TYPE_CONFIG = {
  faq: { icon: React.createElement(QuestionCircleOutlined), label: 'FAQ', color: '#0D9488', bg: 'rgba(13,148,136,0.08)' },
  doc: { icon: React.createElement(FileTextOutlined), label: '产品文档', color: '#2563EB', bg: 'rgba(37,99,235,0.08)' },
  report: { icon: React.createElement(BarChartOutlined), label: '报表', color: '#D97706', bg: 'rgba(217,119,6,0.08)' },
};

/** 高亮关键词 */
function highlightText(text, keywords) {
  if (!text || !keywords || keywords.length === 0) return text;
  const escaped = keywords
    .filter(Boolean)
    .map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .filter((v, i, arr) => arr.indexOf(v) === i);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const lower = part.toLowerCase();
    const isMatch = escaped.some(k => lower === k.toLowerCase());
    return isMatch
      ? React.createElement('mark', { key: i, style: { background: '#FFF3CD', padding: '0 2px', borderRadius: 2 } }, part)
      : part;
  });
}

/** 结果卡片组件 */
function ResultCard({ item, keywords, onClick, query }) {
  const typeConf = TYPE_CONFIG[item.source === 'faq_knowledge' ? 'faq' : item.source === 'report_data' ? 'report' : 'doc'];
  const snippet = item.snippets ? item.snippets.join(' ... ') : (item.snippet || '');
  const pathParts = (item.path || '').split('/').filter(Boolean);
  const breadcrumb = pathParts.slice(-3).join(' > ');
  const [feedback, setFeedback] = useState(null); // 'useful' | 'not_useful' | null

  const handleFeedback = (type) => {
    if (feedback) return; // 已评价
    setFeedback(type);
    const resultId = item.faq_id || item.path || '';
    const resultPath = item.path || '';
    sendFeedback(query || '', resultId, resultPath, type).then(res => {
      if (res?.ok) {
        message.success(type === 'useful' ? '感谢反馈，结果对你有用！' : '感谢反馈，我们会优化搜索结果');
      }
    }).catch(() => {});
  };

  return (
    <div
      onClick={() => onClick(item)}
      style={{
        padding: '14px 16px',
        borderBottom: '1px solid #f0f0f0',
        cursor: 'pointer',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = '#fafafa'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 6 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 6, background: typeConf.bg,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, marginTop: 2,
        }}>
          {typeConf.icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Text strong style={{ fontSize: 14, color: '#1e293b' }}>{item.title || '无标题'}</Text>
            <Tag style={{ fontSize: 11, borderRadius: 4, lineHeight: '18px', margin: 0, color: typeConf.color, background: typeConf.bg, border: 'none' }}>
              {typeConf.label}
            </Tag>
            {item.score != null && (
              <Tag style={{ fontSize: 11, borderRadius: 4, lineHeight: '18px', margin: 0, color: '#6B7280', background: '#F3F4F6', border: 'none' }}>
                相关度 {Math.round(item.score * 100 / 18)}%
              </Tag>
            )}
          </div>
          <Paragraph
            ellipsis={{ rows: 2 }}
            style={{ fontSize: 13, color: '#6B7280', margin: 0, lineHeight: 1.7 }}
          >
            {highlightText(snippet, keywords)}
          </Paragraph>
          {breadcrumb && (
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
              {breadcrumb}
            </Text>
          )}
          {/* 部门层级路径 */}
          {item.dept_path && item.dept_path !== item.dept && (
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2, color: '#0D9488' }}>
              🏢 {item.dept_path}
            </Text>
          )}
          {/* 搜索反馈按钮 */}
          {query && (
            <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
              <Tooltip title={feedback ? undefined : '这个结果对你有用吗？点击反馈帮助提升搜索质量'}>
                <Button
                  size="small"
                  type={feedback === 'useful' ? 'primary' : 'text'}
                  icon={<LikeOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleFeedback('useful'); }}
                  disabled={feedback !== null}
                  style={{ fontSize: 12, padding: '0 8px', height: 26 }}
                >
                  {feedback === 'useful' ? '已标记有用' : '有用'}
                </Button>
              </Tooltip>
              <Tooltip title={feedback ? undefined : '这个结果不相关？点击反馈帮助我们改进'}>
                <Button
                  size="small"
                  type={feedback === 'not_useful' ? 'primary' : 'text'}
                  danger={feedback === 'not_useful'}
                  icon={<DislikeOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleFeedback('not_useful'); }}
                  disabled={feedback !== null}
                  style={{ fontSize: 12, padding: '0 8px', height: 26 }}
                >
                  {feedback === 'not_useful' ? '已标记没用' : '没用'}
                </Button>
              </Tooltip>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ResultCard;
export { highlightText };