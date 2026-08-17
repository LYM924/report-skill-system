/**
 * CenterContent.jsx - 中间主面板
 *
 * 布局（从上到下）：
 * 1. 搜索栏（全宽一行）
 * 2. 快捷按钮
 * 3. AI 总结面板（搜索后自动流式展示）
 * 4. 搜索结果卡片列表（按类型分组）
 * 5. 知识总览（渐变卡片）
 */

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Typography, Card, Tag, Input, Button, Select, Row, Col, Spin, Empty } from 'antd';
import {
  RobotOutlined, SearchOutlined, BulbOutlined,
  LinkOutlined, FileSearchOutlined, CloudUploadOutlined,
  LoadingOutlined, ReloadOutlined,
  DownOutlined, FileTextOutlined,
  QuestionCircleOutlined, BarChartOutlined,
} from '@ant-design/icons';
import { searchKnowledge, getDashboardStats, streamClaudeSummary } from '../api';

const { Text, Paragraph } = Typography;

/** 光标闪烁动画 (定义一次，避免每次渲染重新注入 <style>) */
const BLINK_KEYFRAMES = <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>;

const quickActions = [
  { key: 'ai_summary', label: '大模型总结', icon: <RobotOutlined />, color: '#fff', bg: '#1e293b' },
  { key: 'auto_link', label: '自动关联文档', icon: <LinkOutlined />, color: '#333', bg: '#fff' },
  { key: 'similar', label: '相似问题推荐', icon: <FileSearchOutlined />, color: '#333', bg: '#fff' },
  { key: 'ticket_deposit', label: '工单知识沉淀', icon: <CloudUploadOutlined />, color: '#333', bg: '#fff' },
];

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

/** 结果类型图标和颜色 */
const TYPE_CONFIG = {
  faq: { icon: React.createElement(QuestionCircleOutlined), label: 'FAQ', color: '#0D9488', bg: 'rgba(13,148,136,0.08)' },
  doc: { icon: React.createElement(FileTextOutlined), label: '产品文档', color: '#2563EB', bg: 'rgba(37,99,235,0.08)' },
  report: { icon: React.createElement(BarChartOutlined), label: '报表', color: '#D97706', bg: 'rgba(217,119,6,0.08)' },
};

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

/** AI 总结面板 */
function AISummaryPanel({ streamUrl }) {
  const [summary, setSummary] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [deepMode, setDeepMode] = useState(false);
  const abortRef = useRef(null);

  const startStream = useCallback((url) => {
    const abort = streamClaudeSummary(url, {
      onToken: (text) => {
        setSummary(prev => prev + text);
      },
      onComplete: () => {
        setStreaming(false);
        setDone(true);
      },
      onError: (err) => {
        setStreaming(false);
        setError(err.message);
      },
    });
    abortRef.current = abort;
    return abort;
  }, []);

  // 自动触发摘要
  useEffect(() => {
    if (!streamUrl) return;
    setSummary('');
    setDone(false);
    setError(null);
    setStreaming(true);
    setDeepMode(false);

    const abort = startStream(streamUrl);

    return () => abort();
  }, [streamUrl, startStream]);

  // 深度分析
  const handleDeepAnalysis = () => {
    setDeepMode(true);
    setSummary('');
    setDone(false);
    setError(null);
    setStreaming(true);

    const deepUrl = streamUrl.includes('?')
      ? streamUrl + '&deep=1'
      : streamUrl + '?deep=1';

    startStream(deepUrl);
  };

  if (!streamUrl) return null;

  return (
    <Card
      style={{
        borderRadius: 12, marginBottom: 20,
        border: '1px solid #e2e8f0',
        background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
      }}
      styles={{ body: { padding: '16px 20px' } }}
    >
      {/* 标题栏 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #0D9488 0%, #2DD4BF 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          <Text strong style={{ fontSize: 15 }}>
            {deepMode ? 'AI 深度分析' : 'AI 智能总结'}
          </Text>
          {streaming && <LoadingOutlined style={{ color: '#0D9488' }} />}
          {done && <Tag color="success" style={{ fontSize: 11, borderRadius: 4, lineHeight: '18px' }}>完成</Tag>}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {done && !deepMode && (
            <Button
              size="small"
              type="text"
              icon={<DownOutlined />}
              onClick={handleDeepAnalysis}
              style={{ fontSize: 12, color: '#0D9488' }}
            >
              展开深度分析
            </Button>
          )}
          {error && (
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={handleDeepAnalysis}
              style={{ fontSize: 12, color: '#EF4444' }}
            >
              重试
            </Button>
          )}
        </div>
      </div>

      {/* 内容区 */}
      {error ? (
        <div style={{ padding: '12px 0', color: '#EF4444', fontSize: 13 }}>
          ⚠️ 总结生成失败：{error}
        </div>
      ) : summary ? (
        <div style={{
          fontSize: 14, lineHeight: 1.9, color: '#334155',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {summary}
          {streaming && <span style={{
            display: 'inline-block', width: 2, height: 16,
            background: '#0D9488', verticalAlign: 'text-bottom',
            marginLeft: 2, animation: 'blink 1s step-end infinite',
          }} />}
        </div>
      ) : streaming ? (
        <div style={{ padding: '12px 0' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 20 }} spin />} />
          <Text type="secondary" style={{ marginLeft: 10, fontSize: 13 }}>正在生成总结...</Text>
        </div>
      ) : null}

      {BLINK_KEYFRAMES}
    </Card>
  );
}

function CenterContent({ searchResults, onSearchResultsChange, onSelectDoc }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchScope, setSearchScope] = useState('all');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  const [dashboardStats, setDashboardStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboardStats().then(stats => {
      if (stats) setDashboardStats(stats);
      setLoading(false);
    });
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const results = await searchKnowledge(searchQuery.trim(), searchScope);
      onSearchResultsChange(results);
    } catch (err) {
      setSearchError(err.message || '搜索失败');
    } finally {
      setSearching(false);
    }
  };

  // 分组搜索结果
  const groupedResults = useMemo(() => {
    if (!searchResults || !searchResults.results) return { faq: [], doc: [], report: [] };
    const groups = { faq: [], doc: [], report: [] };
    searchResults.results.forEach(item => {
      const source = item.source || '';
      if (source === 'faq_knowledge') {
        groups.faq.push(item);
      } else if (source === 'report_data') {
        groups.report.push(item);
      } else {
        groups.doc.push(item);
      }
    });
    return groups;
  }, [searchResults]);

  const stats = dashboardStats || {};
  const hasResults = searchResults && searchResults.results && searchResults.results.length > 0;
  const keywords = searchResults?.tokens || [];

  return (
    <div style={{ maxWidth: 960 }}>
      {/* ===== 1. 搜索栏 ===== */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1, display: 'flex' }}>
          <Select
            value={searchScope}
            onChange={setSearchScope}
            size="large"
            style={{ width: 160, borderRadius: '8px 0 0 8px' }}
            options={[
              { value: 'all', label: '全部知识' },
              { value: 'doc', label: '产品文档' },
              { value: 'faq', label: 'FAQ' },
              { value: 'dept', label: '部门知识' },
            ]}
          />
          <Input
            placeholder="输入关键词搜索知识库..."
            size="large"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onPressEnter={handleSearch}
            style={{ flex: 1, borderRadius: 0, borderLeft: 'none', borderRight: 'none' }}
          />
          <Button
            type="primary"
            size="large"
            icon={<SearchOutlined />}
            onClick={handleSearch}
            loading={searching}
            style={{ borderRadius: '0 8px 8px 0', background: '#0D9488', borderColor: '#0D9488' }}
          >
            智能检索
          </Button>
        </div>
      </div>

      {/* ===== 2. 快捷按钮 ===== */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {quickActions.map(action => (
          <Button
            key={action.key}
            icon={action.icon}
            style={{
              background: action.bg, color: action.color,
              border: action.bg === '#fff' ? '1px solid #d1d5db' : 'none',
              borderRadius: 8, padding: '4px 16px', fontSize: 13, height: 36,
            }}
          >
            {action.label}
          </Button>
        ))}
      </div>

      {/* ===== 3. AI 总结面板 ===== */}
      {searchResults?.claude_stream_url && (
        <AISummaryPanel
          streamUrl={searchResults.claude_stream_url}
        />
      )}

      {/* ===== 4. 搜索结果卡片列表 ===== */}
      {searchResults && (
        <Card style={{ borderRadius: 12, marginBottom: 20, border: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: hasResults ? 16 : 0 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8, background: 'linear-gradient(135deg, #e8f0fe 0%, #d4e2fc 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <BulbOutlined style={{ fontSize: 18, color: '#0D9488' }} />
            </div>
            <div>
              <Text strong style={{ fontSize: 15 }}>
                {hasResults ? `搜索结果 (${searchResults.total || 0} 条)` : '无结果'}
              </Text>
              {searching && <LoadingOutlined style={{ marginLeft: 8, color: '#0D9488' }} />}
            </div>
          </div>

          {hasResults ? (
            <div>
              {/* FAQ 分组 */}
              {groupedResults.faq.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 16px', background: 'rgba(13,148,136,0.04)',
                    borderRadius: '8px 8px 0 0', borderBottom: '1px solid #f0f0f0',
                  }}>
                    <QuestionCircleOutlined style={{ color: '#0D9488', fontSize: 14 }} />
                    <Text strong style={{ fontSize: 13, color: '#0D9488' }}>
                      FAQ 匹配 ({groupedResults.faq.length})
                    </Text>
                  </div>
                  {groupedResults.faq.map((item, i) => (
                    <ResultCard key={item.faq_id || item.path || i} item={item} keywords={keywords} onClick={onSelectDoc} />
                  ))}
                </div>
              )}

              {/* 产品文档分组 */}
              {groupedResults.doc.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 16px', background: 'rgba(37,99,235,0.04)',
                    borderRadius: groupedResults.faq.length === 0 ? '8px 8px 0 0' : '0',
                    borderBottom: '1px solid #f0f0f0',
                  }}>
                    <FileTextOutlined style={{ color: '#2563EB', fontSize: 14 }} />
                    <Text strong style={{ fontSize: 13, color: '#2563EB' }}>
                      产品文档 ({groupedResults.doc.length})
                    </Text>
                  </div>
                  {groupedResults.doc.map((item, i) => (
                    <ResultCard key={item.path || i} item={item} keywords={keywords} onClick={onSelectDoc} />
                  ))}
                </div>
              )}

              {/* 报表分组 */}
              {groupedResults.report.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 16px', background: 'rgba(217,119,6,0.04)',
                    borderRadius: '0',
                    borderBottom: '1px solid #f0f0f0',
                  }}>
                    <BarChartOutlined style={{ color: '#D97706', fontSize: 14 }} />
                    <Text strong style={{ fontSize: 13, color: '#D97706' }}>
                      报表数据 ({groupedResults.report.length})
                    </Text>
                  </div>
                  {groupedResults.report.map((item, i) => (
                    <ResultCard key={item.path || i} item={item} keywords={keywords} onClick={onSelectDoc} />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div style={{ textAlign: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 13 }}>未找到相关结果</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 12 }}>试试其他关键词，如"报销单"、"选不到"</Text>
                </div>
              }
              style={{ padding: '24px 0' }}
            />
          )}
        </Card>
      )}

      {/* ===== 5. 知识总览 ===== */}
      {!searchResults && (
        <div style={{
          background: 'linear-gradient(135deg, #334155 0%, #0D9488 100%)',
          borderRadius: 12, padding: '20px 24px', marginBottom: 20, color: '#fff',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Text strong style={{ fontSize: 20, color: '#fff' }}>知识总览</Text>
            <span style={{ cursor: 'pointer', fontSize: 16, opacity: 0.8 }}>▲</span>
          </div>
          {loading ? (
            <Spin />
          ) : (
            <Row gutter={[16, 16]}>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>知识文档</div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.totalDocs?.toLocaleString() || '-'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>FAQ沉淀</div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.faqCount?.toLocaleString() || '-'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>本周问题</div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.weekQuestions || '-'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>本周新增</div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>
                    {stats.weekNew || '-'}
                  </div>
                  {stats.weekNewGrowth != null && (
                    <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2 }}>
                      较上周 {stats.weekNewGrowth}%
                    </div>
                  )}
                </div>
              </Col>
            </Row>
          )}
        </div>
      )}
    </div>
  );
}

export default CenterContent;