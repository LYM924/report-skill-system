/**
 * RightPanel.jsx - 右侧侧边信息看板
 *
 * 两种模式：
 * - 默认: 高频FAQ + 最近更新
 * - 选中文档: 文档详情视图（标题、元信息、Markdown 内容、关联 FAQ）
 */

import React, { useState, useEffect } from 'react';
import { Typography, Empty, Tag, Avatar, Row, Col, Button, Spin, Divider, Image } from 'antd';
import {
  QuestionCircleOutlined, FileTextOutlined, ClockCircleOutlined,
  RightOutlined, ArrowLeftOutlined,
  FolderOutlined, TagOutlined,
} from '@ant-design/icons';
import { mockFAQs, trendData, recentUpdates } from '../mock/data';
import { getFAQs, getFAQDetail, getDocumentDetail, getTrends, getRecent } from '../api';

const { Text, Paragraph } = Typography;

/** 迷你 SVG 折线图 */
function MiniChart({ data, color = '#0D9488', height = 50 }) {
  if (!data || data.length === 0) return null;
  const maxVal = Math.max(...data.map(d => d.value));
  const minVal = Math.min(...data.map(d => d.value));
  const range = maxVal - minVal || 1;
  const w = 120;
  const h = height;
  const stepX = w / (data.length - 1);
  const points = data.map((d, i) => {
    const x = i * stepX;
    const y = h - ((d.value - minVal) / range) * (h - 16);
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => {
        const x = i * stepX;
        const y = h - ((d.value - minVal) / range) * (h - 16);
        return <circle key={i} cx={x} cy={y} r="2.5" fill={color} stroke="#fff" strokeWidth="1.5" />;
      })}
    </svg>
  );
}

/** 简单 Markdown 渲染（标题、列表、表格、图片、链接、粗体、代码等） */
function SimpleMarkdown({ content }) {
  if (!content) return <Text type="secondary">暂无内容</Text>;

  /** 渲染行内元素：图片、链接、粗体、行内代码、删除线 */
  function renderInline(text) {
    if (!text) return text;
    const parts = [];
    let remaining = text;
    let key = 0;

    const pattern = /!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|~~([^~]+)~~/g;
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(remaining)) !== null) {
      if (match.index > lastIndex) {
        parts.push(remaining.slice(lastIndex, match.index));
      }

      if (match[1] !== undefined) {
        parts.push(
          <Image key={key++} src={match[2]} alt={match[1]}
            style={{ maxWidth: '100%', borderRadius: 6, margin: '8px 0' }} />
        );
      } else if (match[3] !== undefined) {
        parts.push(
          <a key={key++} href={match[4]} target="_blank" rel="noopener noreferrer" style={{ color: '#0D9488' }}>{match[3]}</a>
        );
      } else if (match[5] !== undefined) {
        parts.push(<strong key={key++}>{match[5]}</strong>);
      } else if (match[6] !== undefined) {
        parts.push(<code key={key++} style={{ background: '#f1f5f9', padding: '1px 5px', borderRadius: 3, fontSize: 12, fontFamily: 'monospace' }}>{match[6]}</code>);
      } else if (match[7] !== undefined) {
        parts.push(<del key={key++} style={{ color: '#999' }}>{match[7]}</del>);
      }

      lastIndex = pattern.lastIndex;
    }

    if (lastIndex < remaining.length) {
      parts.push(remaining.slice(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  }

  const lines = content.split('\n');
  const elements = [];
  let inCodeBlock = false;
  let codeLines = [];
  let codeLang = '';
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 跳过 frontmatter
    if (line === '---' && i === 0 && !inCodeBlock) {
      while (i + 1 < lines.length && lines[i + 1] !== '---') i++;
      i++;
      continue;
    }

    // 代码块
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre key={i} style={{ background: '#1e293b', color: '#e2e8f0', padding: '12px 16px', borderRadius: 8, fontSize: 12, overflow: 'auto', maxHeight: 300, lineHeight: 1.6 }}>
            {codeLang && <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 4 }}>{codeLang}</div>}
            {codeLines.join('\n')}
          </pre>
        );
        codeLines = [];
        codeLang = '';
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // 表格处理
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      // 跳过分隔行
      if (line.match(/^\|[\s\-:|]+\|$/)) continue;
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      // 表格结束，渲染
      const header = tableRows[0];
      const body = tableRows.slice(1);
      // 合并单元格：空单元格继承上一行的值
      const mergedBody = body.map((row, ri) => {
        const prevRow = ri > 0 ? body[ri - 1] : null;
        return row.map((cell, ci) => {
          if (!cell && prevRow && prevRow[ci]) return prevRow[ci];
          return cell;
        });
      });
      elements.push(
        <div key={`tbl-${i}`} style={{ overflow: 'auto', margin: '8px 0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            {header && (
              <thead>
                <tr>
                  {header.map((h, j) => (
                    <th key={j} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', background: '#f8fafc', textAlign: 'left', fontWeight: 600, color: '#334155', whiteSpace: 'nowrap' }}>{renderInline(h)}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {mergedBody.map((row, ri) => (
                <tr key={ri} style={{ background: ri % 2 === 0 ? '#fff' : '#fafafa' }}>
                  {row.map((cell, cj) => (
                    <td key={cj} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', color: '#4B5563', whiteSpace: cj === 0 ? 'nowrap' : 'normal' }}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      inTable = false;
      tableRows = [];
    }

    // 空行
    if (!line.trim()) {
      elements.push(<div key={i} style={{ height: 8 }} />);
      continue;
    }

    // 水平线
    if (line.match(/^[-*_]{3,}$/)) {
      elements.push(<hr key={i} style={{ border: 'none', borderTop: '1px solid #e2e8f0', margin: '12px 0' }} />);
      continue;
    }

    // 标题
    if (line.startsWith('#### ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 13, display: 'block', marginTop: 10, marginBottom: 4, color: '#64748B' }}>{renderInline(line.slice(5))}</Text>);
    } else if (line.startsWith('### ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 14, display: 'block', marginTop: 12, marginBottom: 4 }}>{renderInline(line.slice(4))}</Text>);
    } else if (line.startsWith('## ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 15, display: 'block', marginTop: 16, marginBottom: 6, color: '#0D9488' }}>{renderInline(line.slice(3))}</Text>);
    } else if (line.startsWith('# ')) {
      elements.push(<Text strong key={i} style={{ fontSize: 16, display: 'block', marginTop: 16, marginBottom: 8 }}>{renderInline(line.slice(2))}</Text>);
    }
    // 引用
    else if (line.startsWith('> ')) {
      elements.push(
        <div key={i} style={{ borderLeft: '3px solid #0D9488', padding: '4px 12px', margin: '4px 0', background: 'rgba(13,148,136,0.04)', borderRadius: '0 4px 4px 0', color: '#64748B', fontSize: 13 }}>
          {renderInline(line.replace(/^>\s?/, ''))}
        </div>
      );
    }
    // 有序列表
    else if (line.match(/^\d+\.\s/)) {
      const num = line.match(/^(\d+)\./)[1];
      elements.push(
        <div key={i} style={{ paddingLeft: 16, fontSize: 13, lineHeight: 1.8, color: '#4B5563' }}>
          {num}. {renderInline(line.replace(/^\d+\.\s/, ''))}
        </div>
      );
    }
    // 无序列表
    else if (line.match(/^[-*]\s/)) {
      elements.push(
        <div key={i} style={{ paddingLeft: 16, fontSize: 13, lineHeight: 1.8, color: '#4B5563' }}>
          • {renderInline(line.replace(/^[-*]\s/, ''))}
        </div>
      );
    }
    // 普通段落
    else {
      elements.push(
        <Text key={i} style={{ fontSize: 13, display: 'block', lineHeight: 1.8, color: '#4B5563' }}>
          {renderInline(line)}
        </Text>
      );
    }
  }

  // 处理未关闭的表格
  if (inTable && tableRows.length > 0) {
    const header = tableRows[0];
    const body = tableRows.slice(1);
    const mergedBody = body.map((row, ri) => {
      const prevRow = ri > 0 ? body[ri - 1] : null;
      return row.map((cell, ci) => {
        if (!cell && prevRow && prevRow[ci]) return prevRow[ci];
        return cell;
      });
    });
    elements.push(
      <div key="tbl-end" style={{ overflow: 'auto', margin: '8px 0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          {header && (
            <thead>
              <tr>
                {header.map((h, j) => (
                  <th key={j} style={{ border: '1px solid #e2e8f0', padding: '6px 10px', background: '#f8fafc', textAlign: 'left', fontWeight: 600 }}>{renderInline(h)}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {mergedBody.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? '#fff' : '#fafafa' }}>
                {row.map((cell, cj) => (
                  <td key={cj} style={{ border: '1px solid #e2e8f0', padding: '6px 10px' }}>{renderInline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <div style={{ maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>{elements}</div>;
}

function RightPanel({ selectedDoc, onClearDoc }) {
  const [faqs, setFaqs] = useState([]);
  const [docDetail, setDocDetail] = useState(null);
  const [docLoading, setDocLoading] = useState(false);
  const [selectedFaq, setSelectedFaq] = useState(null); // FAQ 详情
  const [faqLoading, setFaqLoading] = useState(false);
  const [trendData, setTrendData] = useState([]);
  const [faqTrendData, setFaqTrendData] = useState([]);
  const [recentData, setRecentData] = useState([]);

  useEffect(() => {
    getFAQs().then(data => {
      if (data && data.length > 0) setFaqs(data);
    });
  }, []);

  useEffect(() => {
    getTrends().then(data => {
      if (data?.trends) setTrendData(data.trends);
      if (data?.faqTrends) setFaqTrendData(data.faqTrends);
    });
    getRecent().then(data => {
      if (data?.recent) setRecentData(data.recent);
    });
  }, []);

  // 当选中文档时，加载文档详情
  useEffect(() => {
    if (!selectedDoc) {
      setDocDetail(null);
      return;
    }
    setDocLoading(true);
    const path = selectedDoc.path || selectedDoc._source || '';
    getDocumentDetail(path).then(data => {
      if (data) setDocDetail(data);
      setDocLoading(false);
    }).catch(() => {
      // fallback: 使用 selectedDoc 自带的信息
      setDocDetail({
        title: selectedDoc.title || '文档详情',
        path: selectedDoc.path || '',
        content: selectedDoc.snippets?.join('\n') || selectedDoc.snippet || selectedDoc.content || '',
        frontmatter: {},
      });
      setDocLoading(false);
    });
  }, [selectedDoc]);

  // 点击 FAQ 卡片
  const handleFaqClick = async (faq) => {
    setFaqLoading(true);
    setSelectedFaq(faq);
    const detail = await getFAQDetail(faq.id);
    if (detail) {
      setSelectedFaq(prev => ({ ...prev, ...detail }));
    }
    setFaqLoading(false);
  };

  // ===== FAQ 详情视图 =====
  if (selectedFaq && !selectedDoc) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => setSelectedFaq(null)}
          style={{ alignSelf: 'flex-start', marginBottom: 12, padding: '4px 8px', fontSize: 13, color: '#0D9488' }}
        >
          返回
        </Button>

        {faqLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 8, color: '#0D9488' }}>
              {selectedFaq.title || 'FAQ 详情'}
            </Text>
            <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {selectedFaq.keywords?.map(k => (
                <Tag key={k} style={{ fontSize: 11, borderRadius: 4, background: 'rgba(13,148,136,0.08)', color: '#0D9488', border: 'none' }}>
                  {k}
                </Tag>
              ))}
              {selectedFaq.dept && (
                <Tag style={{ fontSize: 11, borderRadius: 4 }}>{selectedFaq.dept}</Tag>
              )}
            </div>
            <Divider style={{ margin: '12px 0' }} />
            <SimpleMarkdown content={selectedFaq.content || selectedFaq.answer} />
          </div>
        )}
      </div>
    );
  }

  // ===== 文档详情视图 =====
  if (selectedDoc) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={onClearDoc}
          style={{ alignSelf: 'flex-start', marginBottom: 12, padding: '4px 8px', fontSize: 13, color: '#0D9488' }}
        >
          返回
        </Button>

        {docLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : docDetail ? (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>
              {docDetail.title || selectedDoc.title || '文档详情'}
            </Text>

            <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {docDetail.frontmatter?.module && (
                <Tag icon={<FolderOutlined />} style={{ fontSize: 11, borderRadius: 4 }}>
                  {docDetail.frontmatter.module}
                </Tag>
              )}
              {docDetail.frontmatter?.dept && (
                <Tag icon={<TagOutlined />} style={{ fontSize: 11, borderRadius: 4 }}>
                  {docDetail.frontmatter.dept}
                </Tag>
              )}
              {docDetail.path && (
                <Text type="secondary" style={{ fontSize: 11, display: 'block', width: '100%', marginTop: 4 }}>
                  路径: {docDetail.path}
                </Text>
              )}
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <SimpleMarkdown content={docDetail.content} />
          </div>
        ) : (
          <Empty description="无法加载文档" />
        )}
      </div>
    );
  }

  // ===== 默认视图 =====
  const displayFAQs = faqs.length > 0 ? faqs : mockFAQs;
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
      {/* ===== 1. 高频FAQ ===== */}
      <div style={{
        background: 'linear-gradient(135deg, #0D9488 0%, #2DD4BF 100%)',
        borderRadius: 12, padding: 16, marginBottom: 20, color: '#fff',
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
      }}>
        <div>
          <Text strong style={{ fontSize: 16, color: '#fff' }}>高频FAQ</Text>
          <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>工单问题沉淀</div>
        </div>
        <span style={{ cursor: 'pointer', fontSize: 14, opacity: 0.8 }}>▲</span>
      </div>

      {/* 工单问题沉淀 + 趋势图 */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 12 }}>工单问题沉淀</Text>
        <Row gutter={[8, 8]}>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 90 }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>高频FAQ</div>
              <MiniChart data={trendData.length > 0 ? trendData : [{month:'-',value:0}]} color="#0D9488" />
            </div>
          </Col>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 90 }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>重复热点问题</div>
              <MiniChart data={faqTrendData.length > 0 ? faqTrendData : [{month:'-',value:0}]} color="#2DD4BF" />
            </div>
          </Col>
        </Row>
      </div>

      {/* FAQ 列表 */}
      <div style={{ marginBottom: 16 }}>
        {displayFAQs.slice(0, 3).map(faq => (
          <div
            key={faq.id}
            onClick={() => handleFaqClick(faq)}
            style={{
              marginBottom: 6, border: '1px solid #f0f0f0', borderRadius: 8,
              padding: '8px 10px', cursor: 'pointer', background: '#fff',
              transition: 'box-shadow 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)'}
            onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
              <Text style={{ fontSize: 12, lineHeight: 1.5 }}>{faq.title}</Text>
              <RightOutlined style={{ fontSize: 10, color: '#ccc', flexShrink: 0 }} />
            </div>
            <div style={{ marginTop: 3, display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              {faq.keywords?.slice(0, 2).map(k => (
                <span key={k} style={{
                  display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                  fontSize: 10, background: 'rgba(13,148,136,0.08)', color: '#0D9488',
                }}>{k}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ===== 2. 相关产品文档 ===== */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 12 }}>相关产品文档</Text>
        <Row gutter={[8, 8]}>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 90 }}></div>
          </Col>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 90 }}>
              <MiniChart data={trendData.length > 0 ? trendData : [{month:'-',value:0}]} color="#0D9488" />
            </div>
          </Col>
        </Row>
      </div>

      {/* ===== 3. 最近更新 ===== */}
      <div style={{ flex: 1 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 12 }}>最近更新</Text>
        <Row gutter={[8, 8]}>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 160 }}>
              {(recentData.length > 0 ? recentData : recentUpdates).slice(0, 3).map(item => (
                <div key={item.name} style={{ marginBottom: 6, fontSize: 11 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Avatar size={16} style={{ backgroundColor: '#0D9488', fontSize: 9 }}>
                      {item.dept?.[0] || '文'}
                    </Avatar>
                    <Text ellipsis style={{ fontSize: 11, flex: 1 }}>{item.name}</Text>
                  </div>
                  <div style={{ paddingLeft: 20, marginTop: 1 }}>
                    <Tag color="default" style={{ fontSize: 9, borderRadius: 3, lineHeight: '14px' }}>
                      更新
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 10 }}>{item.updated}</Text>
                  </div>
                </div>
              ))}
            </div>
          </Col>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 160 }}></div>
          </Col>
        </Row>
      </div>
    </div>
  );
}

export default RightPanel;