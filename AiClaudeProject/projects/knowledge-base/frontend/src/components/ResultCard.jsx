/**
 * ResultCard.jsx - 搜索结果卡片
 *
 * 展示单条搜索结果的卡片组件，包含类型图标、标题、摘要片段和面包屑导航。
 * 支持关键词高亮显示。
 */
import React from 'react';
import { Typography, Tag } from 'antd';
import { QuestionCircleOutlined, FileTextOutlined, BarChartOutlined } from '@ant-design/icons';

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
function ResultCard({ item, keywords, onClick }) {
  const typeConf = TYPE_CONFIG[item.source === 'faq_knowledge' ? 'faq' : item.source === 'report_data' ? 'report' : 'doc'];
  const snippet = item.snippets ? item.snippets.join(' ... ') : (item.snippet || '');
  const pathParts = (item.path || '').split('/').filter(Boolean);
  const breadcrumb = pathParts.slice(-3).join(' > ');

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
        </div>
      </div>
    </div>
  );
}

export default ResultCard;
export { highlightText };