/**
 * CenterContent.jsx - 中间主面板
 *
 * 布局（从上到下）：
 * 1. 搜索栏（全宽一行）
 * 2. 快捷按钮
 * 3. AI 总结面板（搜索后自动流式展示）
 * 4. 搜索结果卡片列表（按类型分组）
 * 5. 知识总览（渐变卡片）
 *
 * 子组件已拆分到独立文件：
 * - AISummaryPanel.jsx
 * - ResultCard.jsx
 * - StatsDashboard.jsx
 * - ChatMode.jsx
 * - ManagePanel.jsx
 */

import React, { useState, useEffect, useMemo, useRef, Suspense } from 'react';
import { authFetch } from '../api';
import { Typography, Card, Tag, Input, Button, Select, Row, Col, Spin, Empty, Table, Tooltip, Skeleton } from 'antd';
import {
  SearchOutlined, RobotOutlined, LinkOutlined, FileSearchOutlined, CloudUploadOutlined,
  BulbOutlined, LoadingOutlined, HistoryOutlined, CloseOutlined,
  FileTextOutlined, QuestionCircleOutlined, BarChartOutlined, RightOutlined,
  InfoCircleOutlined, TeamOutlined,
} from '@ant-design/icons';
import { searchKnowledge, getDashboardStats, getDocuments } from '../api';
import AISummaryPanel from './AISummaryPanel';
import ResultCard from './ResultCard';
import FaqBrowser from './FaqBrowser';
import ReportBrowser from './ReportBrowser';
import DeptBrowser from './DeptBrowser';
import SettingsCenter from './SettingsCenter';
import UserManager from './UserManager';

// 非首屏 Tab 组件懒加载，减少首屏 JS bundle 体积
const StatsDashboard = React.lazy(() => import('./StatsDashboard'));
const ChatMode = React.lazy(() => import('./ChatMode'));
const ManagePanel = React.lazy(() => import('./ManagePanel'));

/** 懒加载 Fallback */
function TabFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
      <Spin size="large" />
    </div>
  );
}

const { Text, Paragraph } = Typography;

const quickActions = [
  { key: 'ai_summary', label: '大模型总结', icon: <RobotOutlined />, color: '#fff', bg: '#1e293b' },
  { key: 'auto_link', label: '自动关联文档', icon: <LinkOutlined />, color: '#333', bg: '#fff' },
  { key: 'similar', label: '相似问题推荐', icon: <FileSearchOutlined />, color: '#333', bg: '#fff' },
  { key: 'ticket_deposit', label: '工单知识沉淀', icon: <CloudUploadOutlined />, color: '#333', bg: '#fff' },
];

function CenterContent({ searchResults, onSearchResultsChange, onSelectDoc, searchScope, onSearchScopeChange, isDark, topTab, selectedNav }) {
  const [searchQuery, setSearchQuery] = useState(() => {
    try { return localStorage.getItem('kb_last_query') || ''; } catch { return ''; }
  });
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [searchTime, setSearchTime] = useState(null); // 搜索耗时(ms)

  const [quickActionMsg, setQuickActionMsg] = useState(null);
  const [aiSummaryText, setAiSummaryText] = useState(''); // 当前 AI 总结文本
  const [searchPage, setSearchPage] = useState(1);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const suggestTimer = useRef(null);  // 防抖定时器
  const [relatedSearches, setRelatedSearches] = useState([]);  // 相关搜索推荐
  const [activeFacets, setActiveFacets] = useState({});  // 当前激活的分面筛选 {dept: "xxx", source: "faq_knowledge"}
  const [summaryRetryKey, setSummaryRetryKey] = useState(0);  // "大模型总结"按钮重试计数

  const handleQuickAction = (key) => {
    if (key === 'ai_summary') {
      if (!searchResults?.claude_stream_url) {
        setQuickActionMsg('请先搜索后再使用大模型总结');
        setTimeout(() => setQuickActionMsg(null), 3000);
        return;
      }
      // 重新触发 AI 总结（retryKey 递增使 AISummaryPanel 强制重新起流）
      setSummaryRetryKey(k => k + 1);
      onSearchResultsChange({ ...searchResults });
    } else if (key === 'auto_link') {
      if (!searchQuery.trim()) {
        setQuickActionMsg('请先搜索后再使用自动关联文档');
        setTimeout(() => setQuickActionMsg(null), 3000);
        return;
      }
      // 扩展搜索，展示关联文档
      setQuickActionMsg('正在搜索关联文档...');
      searchKnowledge(searchQuery.trim(), 'doc').then(results => {
        if (results?.results?.length) {
          onSearchResultsChange(results);
          setQuickActionMsg(`已找到 ${results.results.length} 条关联文档`);
        } else {
          setQuickActionMsg('未找到关联文档');
        }
        setTimeout(() => setQuickActionMsg(null), 3000);
      });
    } else if (key === 'similar') {
      if (!searchQuery.trim()) {
        setQuickActionMsg('请先输入搜索关键词');
        setTimeout(() => setQuickActionMsg(null), 3000);
        return;
      }
      const kw = (searchResults?.tokens || [searchQuery.trim()]).join(',');
      setQuickActionMsg('正在匹配相似问题...');
      authFetch(`/api/faq/similar?keywords=${encodeURIComponent(kw)}`)
        .then(r => r.json())
        .then(data => {
          const faqs = data?.faqs || [];
          if (faqs.length > 0) {
            setQuickActionMsg(`找到 ${faqs.length} 个相似 FAQ，请查看右侧面板`);
            // 取第一个 FAQ 展示在右侧面板
            onSelectDoc({ ...faqs[0], title: faqs[0].title });
          } else {
            setQuickActionMsg('未找到相似 FAQ');
          }
          setTimeout(() => setQuickActionMsg(null), 4000);
        })
        .catch(() => {
          setQuickActionMsg('匹配失败，请重试');
          setTimeout(() => setQuickActionMsg(null), 3000);
        });
    } else if (key === 'ticket_deposit') {
      if (!searchQuery.trim()) {
        setQuickActionMsg('请先搜索后再使用工单知识沉淀');
        setTimeout(() => setQuickActionMsg(null), 3000);
        return;
      }
      // 保存为 FAQ 草稿到 localStorage
      const drafts = JSON.parse(localStorage.getItem('kb_faq_drafts') || '[]');
      drafts.unshift({
        id: Date.now(),
        question: searchQuery.trim(),
        answer: aiSummaryText || '（AI 总结尚未生成，请等待总结完成后再沉淀）',
        keywords: searchResults?.tokens || [],
        results: searchResults?.results?.slice(0, 5) || [],
        createdAt: new Date().toISOString(),
        status: 'draft',
      });
      localStorage.setItem('kb_faq_drafts', JSON.stringify(drafts.slice(0, 50)));
      setQuickActionMsg('已保存为 FAQ 草稿，请到「知识管理 → FAQ草稿」中审核编辑');
      setTimeout(() => setQuickActionMsg(null), 4000);
    }
  };

  const [dashboardStats, setDashboardStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  // 搜索历史（最近5条，存 localStorage）
  const SEARCH_HISTORY_KEY = 'kb_search_history';
  const [searchHistory, setSearchHistory] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]');
    } catch { return []; }
  });
  const [showHistory, setShowHistory] = useState(false);

  // 保存搜索历史
  const saveToHistory = (query) => {
    const updated = [query, ...searchHistory.filter(q => q !== query)].slice(0, 5);
    setSearchHistory(updated);
    try { localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(updated)); } catch {}
  };

  // Esc 键清除搜索，回到首页
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && searchResults) {
        onSearchResultsChange(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [searchResults, onSearchResultsChange]);

  useEffect(() => {
    Promise.all([
      getDashboardStats(),
      getDocuments(),
    ]).then(([stats, docs]) => {
      if (stats) setDashboardStats(stats);
      if (docs) setDocuments(docs);
      setLoading(false);
    });
  }, []);

  const handleSearch = async (queryOverride) => {
    const q = (queryOverride || searchQuery).trim();
    if (!q) return;
    // 持久化搜索 query
    try { localStorage.setItem('kb_last_query', q); } catch {}
    setSearching(true);
    setSearchError(null);
    const startTime = performance.now();
    try {
      setSearchPage(1);
      const results = await searchKnowledge(q, searchScope, 1);
      onSearchResultsChange(results);
      saveToHistory(q);
      setSearchTime(Math.round(performance.now() - startTime));
      setShowHistory(false);
      // 获取相关搜索推荐
      authFetch(`/api/search/related?q=${encodeURIComponent(q)}`)
        .then(r => r.json())
        .then(data => setRelatedSearches(data?.related || []))
        .catch(() => setRelatedSearches([]));
    } catch (err) {
      setSearchError(err.message || '搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const handleLoadMore = async () => {
    const nextPage = searchPage + 1;
    const results = await searchKnowledge(searchQuery.trim(), searchScope, nextPage);
    if (results?.results?.length) {
      onSearchResultsChange({
        ...results,
        results: [...(searchResults?.results || []), ...results.results],
      });
      setSearchPage(nextPage);
    }
  };

  const handleInputChange = (e) => {
    const val = e.target.value;
    setSearchQuery(val);

    // 防抖：300ms 内不再输入才发起 suggest 请求
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    if (val.trim().length >= 2) {
      suggestTimer.current = setTimeout(() => {
        authFetch(`/api/suggest?q=${encodeURIComponent(val.trim())}`)
          .then(r => r.json())
          .then(data => {
            setSuggestions(data?.suggestions || []);
            setShowSuggestions(true);
          });
      }, 300);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  // 分组搜索结果（含分面筛选：按部门/来源过滤当前结果集）
  const groupedResults = useMemo(() => {
    if (!searchResults || !searchResults.results) return { faq: [], doc: [], report: [] };
    const groups = { faq: [], doc: [], report: [] };
    const filters = activeFacets || {};
    searchResults.results.forEach(item => {
      if (filters.dept && item.dept !== filters.dept) return;
      if (filters.source && (item.source || '') !== filters.source) return;
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
  }, [searchResults, activeFacets]);

  const filteredCount = (groupedResults.faq?.length || 0) + (groupedResults.doc?.length || 0) + (groupedResults.report?.length || 0);

  const stats = dashboardStats || {};
  const hasResults = searchResults && searchResults.results && searchResults.results.length > 0;
  const keywords = searchResults?.tokens || [];

  // 系统管理页（左侧菜单 系统管理 → 配置中心/用户管理）
  // 必须在 topTab 判断之前：点击系统管理菜单时 topTab 会切到 manage
  if (selectedNav === 'settings-ai') return <SettingsCenter isDark={isDark} />;
  if (selectedNav === 'settings-users') return <UserManager isDark={isDark} />;

  if (topTab === 'stats') return <Suspense fallback={<TabFallback />}><StatsDashboard isDark={isDark} /></Suspense>;
  if (topTab === 'ai') return <Suspense fallback={<TabFallback />}><ChatMode isDark={isDark} /></Suspense>;
  if (topTab === 'manage') return <Suspense fallback={<TabFallback />}><ManagePanel isDark={isDark} /></Suspense>;

  // FAQ 部门浏览（左侧 FAQ库 点击部门触发）
  if (selectedNav && selectedNav.startsWith('faq-dept-')) {
    const dept = selectedNav.replace('faq-dept-', '');
    return <FaqBrowser dept={dept} isDark={isDark} onSelectDoc={onSelectDoc} />;
  }

  // 报表数据浏览（左侧菜单 报表数据 触发）
  if (selectedNav === 'reports') {
    return <ReportBrowser isDark={isDark} onSelectDoc={onSelectDoc} />;
  }

  // 部门知识浏览（key 格式: dept-browse-{deptId}-{deptName}）
  if (selectedNav && selectedNav.startsWith('dept-browse-')) {
    const parts = selectedNav.replace('dept-browse-', '').split('-');
    const deptId = parts[0];
    const deptName = parts.slice(1).join('-');
    return <DeptBrowser key={selectedNav} deptId={deptId} deptName={deptName} isDark={isDark} onSelectDoc={onSelectDoc} />;
  }

  // 业务模块/产品模块浏览（左侧菜单 biz-* 或 prod-* 点击触发）
  if (selectedNav && (selectedNav.startsWith('biz-') || selectedNav.startsWith('prod-'))) {
    const segments = selectedNav.split('-');
    const moduleName = segments[segments.length - 1];
    return <DeptBrowser dept={moduleName} isDark={isDark} onSelectDoc={onSelectDoc} />;
  }

  // 工单知识浏览（左侧菜单 工单知识 触发）
  if (selectedNav === 'ticket') {
    return <DeptBrowser dept="工单" isDark={isDark} onSelectDoc={onSelectDoc} />;
  }

  return (
    <div style={{ width: '100%' }}>
      {/* ===== 1. 搜索栏 ===== */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1, display: 'flex' }}>
          <Select
            value={searchScope}
            onChange={onSearchScopeChange}
            size="large"
            style={{ width: 160, borderRadius: '8px 0 0 8px' }}
            options={[
              { value: 'all', label: '全部知识' },
              { value: 'doc', label: '产品文档' },
              { value: 'faq', label: 'FAQ' },
              { value: 'dept', label: '部门知识' },
            ]}
          />
          <div style={{ flex: 1, position: 'relative' }}>
            <Input
              placeholder="输入关键词搜索知识库... (Ctrl+K)"
              size="large"
              value={searchQuery}
              onChange={handleInputChange}
              onPressEnter={() => handleSearch()}
              onFocus={() => setShowHistory(searchHistory.length > 0)}
              onBlur={() => setTimeout(() => setShowHistory(false), 200)}
              style={{ borderRadius: 0, borderLeft: 'none', borderRight: 'none' }}
            />
            {/* 搜索历史下拉 */}
            {showHistory && searchHistory.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                background: '#fff', border: '1px solid #e2e8f0', borderRadius: '0 0 8px 8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)', zIndex: 10, overflow: 'hidden',
              }}>
                <div style={{ padding: '6px 12px', fontSize: 11, color: '#999', borderBottom: '1px solid #f0f0f0' }}>
                  最近搜索
                </div>
                {searchHistory.map((q, i) => (
                  <div
                    key={i}
                    onMouseDown={() => { setSearchQuery(q); handleSearch(q); }}
                    style={{
                      padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      borderBottom: i < searchHistory.length - 1 ? '1px solid #f5f5f5' : 'none',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <HistoryOutlined style={{ color: '#999', fontSize: 12 }} />
                      {q}
                    </span>
                    <CloseOutlined
                      style={{ color: '#ccc', fontSize: 10 }}
                      onMouseDown={e => {
                        e.stopPropagation();
                        const updated = searchHistory.filter((_, j) => j !== i);
                        setSearchHistory(updated);
                        localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(updated));
                      }}
                    />
                  </div>
                ))}
              </div>
            )}
            {showSuggestions && suggestions.length > 0 && !searchResults && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                background: '#fff', border: '1px solid #e2e8f0', borderRadius: '0 0 8px 8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)', zIndex: 10, overflow: 'hidden',
              }}>
                {suggestions.map((s, i) => (
                  <div
                    key={i}
                    onMouseDown={() => { setSearchQuery(s); handleSearch(s); setShowSuggestions(false); }}
                    style={{
                      padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                      borderBottom: i < suggestions.length - 1 ? '1px solid #f5f5f5' : 'none',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <SearchOutlined style={{ color: '#999', fontSize: 12, marginRight: 8 }} />
                    {s}
                  </div>
                ))}
              </div>
            )}
          </div>
          <Button
            type="primary"
            size="large"
            icon={<SearchOutlined />}
            onClick={() => handleSearch()}
            loading={searching}
            style={{ borderRadius: '0 8px 8px 0', background: '#0D9488', borderColor: '#0D9488' }}
          >
            智能检索
          </Button>
        </div>
      </div>

      {/* 搜索结果统计 */}
      {searchResults && searchResults.total != null && !searching && (
        <div style={{ marginBottom: 12, fontSize: 12, color: '#999' }}>
          找到 <Text strong style={{ color: '#0D9488' }}>{searchResults.total}</Text> 条结果
          {searchTime != null && <span>，耗时 <Text strong style={{ color: '#666' }}>{searchTime}ms</Text></span>}
          <span style={{ marginLeft: 12, color: '#bbb' }}>按 Esc 清除搜索结果</span>
        </div>
      )}

      {/* 搜索错误提示 */}
      {searchError && (
        <div style={{
          marginBottom: 12, padding: '8px 16px',
          background: '#FEF2F2', border: '1px solid #FECACA',
          borderRadius: 8, color: '#DC2626', fontSize: 13,
        }}>
          ⚠️ 搜索失败：{searchError}
        </div>
      )}

      {/* 拼写纠错提示 */}
      {searchResults?.correction?.has_correction && (
        <div style={{
          marginBottom: 12, padding: '8px 16px',
          background: '#FFF7ED', border: '1px solid #FED7AA',
          borderRadius: 8, fontSize: 13,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{ color: '#9A3412' }}>🔍 您是不是要找：</span>
          {searchResults.correction.corrections.map((c, i) => (
            <Button
              key={i}
              size="small"
              type="link"
              onClick={() => { setSearchQuery(c.correction); handleSearch(c.correction); }}
              style={{ padding: 0, fontSize: 13, fontWeight: 600, color: '#0D9488' }}
            >
              {c.correction}
            </Button>
          ))}
          <span style={{ color: '#9A3412', fontSize: 11, marginLeft: 4 }}>
            （原词：{searchResults.correction.original}）
          </span>
        </div>
      )}

      {/* ===== 2. 快捷按钮 ===== */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {quickActions.map(action => (
          <Button
            key={action.key}
            icon={action.icon}
            onClick={() => handleQuickAction(action.key)}
            style={{
              background: action.bg, color: action.color,
              border: action.bg === '#fff' ? '1px solid #d1d5db' : 'none',
              borderRadius: 8, padding: '4px 16px', fontSize: 13, height: 36,
              cursor: 'pointer',
            }}
          >
            {action.label}
          </Button>
        ))}
      </div>

      {/* 快捷按钮消息提示 */}
      {quickActionMsg && (
        <div style={{
          marginBottom: 12, padding: '8px 16px',
          background: isDark ? 'rgba(13,148,136,0.15)' : 'rgba(13,148,136,0.08)',
          borderRadius: 8, color: '#0D9488', fontSize: 13,
        }}>
          💡 {quickActionMsg}
        </div>
      )}

      {/* ===== 3. AI 总结面板 ===== */}
      {searchResults?.claude_stream_url && (
        <AISummaryPanel
          streamUrl={searchResults.claude_stream_url}
          retryKey={summaryRetryKey}
          onSummaryText={setAiSummaryText}
        />
      )}

      {/* ===== 4. 搜索结果卡片列表 ===== */}
      {searchResults && (
        <Card style={{ borderRadius: 12, marginBottom: 20, border: isDark ? '1px solid #303030' : '1px solid #e2e8f0' }}>
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
              {/* 分面筛选 */}
              {searchResults?.facets && (
                <div style={{ marginBottom: 12, padding: '8px 16px', background: '#fafafa', borderRadius: 8 }}>
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    {/* 按部门筛选 */}
                    {searchResults.facets.dept?.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>部门：</Text>
                        {searchResults.facets.dept.map(d => (
                          <Tag
                            key={d.value}
                            color={activeFacets.dept === d.value ? 'teal' : 'default'}
                            style={{ cursor: 'pointer', fontSize: 11, margin: 0 }}
                            onClick={() => {
                              if (activeFacets.dept === d.value) {
                                setActiveFacets({});
                              } else {
                                setActiveFacets({ dept: d.value });
                              }
                            }}
                          >
                            {d.value} ({d.count})
                          </Tag>
                        ))}
                      </div>
                    )}
                    {/* 按来源筛选 */}
                    {searchResults.facets.source?.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>类型：</Text>
                        {searchResults.facets.source.map(s => {
                          const label = { faq_knowledge: 'FAQ', knowledge_base: '文档', report_data: '报表', keyword_index: '关键词', vector_search: '语义', module_name: '模块' }[s.value] || s.value;
                          return (
                            <Tag
                              key={s.value}
                              color={activeFacets.source === s.value ? 'blue' : 'default'}
                              style={{ cursor: 'pointer', fontSize: 11, margin: 0 }}
                              onClick={() => {
                                if (activeFacets.source === s.value) {
                                  setActiveFacets({});
                                } else {
                                  setActiveFacets({ source: s.value });
                                }
                              }}
                            >
                              {label} ({s.count})
                            </Tag>
                          );
                        })}
                      </div>
                    )}
                    {/* 清除筛选 */}
                    {Object.keys(activeFacets).length > 0 && (
                      <Button size="small" type="link" onClick={() => setActiveFacets({})} style={{ fontSize: 11, padding: 0 }}>
                        清除筛选
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {/* 筛选无结果提示 */}
              {Object.keys(activeFacets).length > 0 && filteredCount === 0 && (
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#999', fontSize: 13 }}>
                  当前筛选条件下无匹配结果
                  <Button size="small" type="link" onClick={() => setActiveFacets({})}>清除筛选</Button>
                </div>
              )}

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
                    <ResultCard key={item.faq_id || item.path || i} item={item} keywords={keywords} onClick={onSelectDoc} query={searchQuery} />
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
            {hasResults && searchResults?.has_more && (
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <Button onClick={handleLoadMore} loading={searching} style={{ borderRadius: 8 }}>
                  加载更多...
                </Button>
              </div>
            )}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div style={{ textAlign: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 13 }}>未找到与「{searchQuery}」相关的结果</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    建议：检查关键词拼写，或使用更通用的词汇（如"报销单"、"选不到"、"预算指标"）
                  </Text>
                  {searchResults?.correction?.has_correction && (
                    <>
                      <br />
                      <Text style={{ fontSize: 13, color: '#0D9488' }}>
                        您是不是要找：{' '}
                        {searchResults.correction.corrections.map((c, i) => (
                          <Button
                            key={i}
                            type="link"
                            size="small"
                            onClick={() => { setSearchQuery(c.correction); handleSearch(c.correction); }}
                            style={{ padding: 0, fontSize: 13, fontWeight: 600 }}
                          >
                            {c.correction}
                          </Button>
                        ))}
                      </Text>
                    </>
                  )}
                  <br />
                  <Text type="secondary" style={{ fontSize: 11, color: '#bbb', marginTop: 4 }}>
                    提示：可使用左侧菜单按部门或产品模块浏览全部文档，或使用高级语法如 dept:免疫规划组 接种
                  </Text>
                </div>
              }
              style={{ padding: '24px 0' }}
            />
          )}
        </Card>
      )}

      {/* 相关搜索推荐 */}
      {searchResults && relatedSearches.length > 0 && (
        <Card style={{ borderRadius: 12, marginBottom: 20, border: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <FileSearchOutlined style={{ color: '#0D9488', fontSize: 14 }} />
            <Text strong style={{ fontSize: 14 }}>相关搜索</Text>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {relatedSearches.map((s, i) => (
              <Tag
                key={i}
                color="default"
                style={{ cursor: 'pointer', fontSize: 12, padding: '4px 12px', borderRadius: 16 }}
                onClick={() => { setSearchQuery(s.query); handleSearch(s.query); }}
              >
                {s.query}
              </Tag>
            ))}
          </div>
        </Card>
      )}

      {/* ===== 5. 知识总览 ===== */}
      {!searchResults && (
        <div style={{
          background: isDark ? 'linear-gradient(135deg, #1a2a2a 0%, #0D9488 100%)' : 'linear-gradient(135deg, #334155 0%, #0D9488 100%)',
          borderRadius: 12, padding: '20px 24px', marginBottom: 20, color: '#fff',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Text strong style={{ fontSize: 20, color: '#fff' }}>知识总览</Text>
            <span style={{ cursor: 'pointer', fontSize: 16, opacity: 0.8 }}>▲</span>
          </div>
          {loading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : (
            <Row gutter={[16, 16]}>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                    知识文档
                    <Tooltip title="知识库文档，不含 FAQ 和报表">
                      <InfoCircleOutlined style={{ fontSize: 12, opacity: 0.6, cursor: 'help' }} />
                    </Tooltip>
                  </div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.totalKbDocs?.toLocaleString() || '-'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                    FAQ沉淀
                    <Tooltip title="FAQ 知识库条目总数">
                      <InfoCircleOutlined style={{ fontSize: 12, opacity: 0.6, cursor: 'help' }} />
                    </Tooltip>
                  </div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.faqCount?.toLocaleString() || '-'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                    报表数据
                    <Tooltip title="周报/月报等报表数据">
                      <InfoCircleOutlined style={{ fontSize: 12, opacity: 0.6, cursor: 'help' }} />
                    </Tooltip>
                  </div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.totalReports?.toLocaleString() || '0'}</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: '16px 20px' }}>
                  <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                    总计
                    <Tooltip title="知识文档 + FAQ + 报表 = 知识库总量">
                      <InfoCircleOutlined style={{ fontSize: 12, opacity: 0.6, cursor: 'help' }} />
                    </Tooltip>
                  </div>
                  <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}>{stats.totalDocs?.toLocaleString() || '-'}</div>
                </div>
              </Col>
            </Row>
          )}
        </div>
      )}

      {/* ===== 文档列表（仅首页展示） ===== */}
      {!searchResults && (
        <Card style={{ borderRadius: 12, border: isDark ? '1px solid #303030' : '1px solid #e2e8f0' }}>
          <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>文档</Text>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Skeleton active paragraph={{ rows: 4 }} /></div>
          ) : documents.length === 0 ? (
            <Empty description="暂无文档" />
          ) : (
            <Table
              dataSource={documents}
              columns={[
                { title: '文档', dataIndex: 'name', key: 'name', render: text => <Text strong style={{ fontSize: 13, color: '#0D9488', cursor: 'pointer' }}>{text}</Text> },
                { title: '产品记录', dataIndex: 'product', key: 'product', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
                { title: '所属部门', dataIndex: 'dept', key: 'dept', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
                { title: '更新时间', dataIndex: 'updated', key: 'updated', render: text => <span style={{ color: '#555' }}>{text || '-'}</span> },
              ]}
              rowKey="id"
              pagination={{ pageSize: 6, size: 'small' }}
              size="middle"
              onRow={(record) => ({
                onClick: () => onSelectDoc(record),
                style: { cursor: 'pointer' },
              })}
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
                    }} />
                  ),
                },
              }}
            />
          )}
        </Card>
      )}
    </div>
  );
}

export default CenterContent;