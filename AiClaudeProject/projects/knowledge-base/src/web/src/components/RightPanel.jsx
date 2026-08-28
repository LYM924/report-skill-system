/**
 * RightPanel.jsx - 右侧侧边信息看板
 *
 * 两种模式：
 * - 默认: 高频FAQ + 最近更新
 * - 选中文档: 文档详情视图（标题、元信息、Markdown 内容、关联 FAQ）
 */

import React, { useState, useEffect } from 'react';
import { Typography, Empty, Tag, Avatar, Row, Col, Button, Spin, Divider, Input, Select, message } from 'antd';
import {
  QuestionCircleOutlined, FileTextOutlined, ClockCircleOutlined,
  RightOutlined, ArrowLeftOutlined,
  FolderOutlined, TagOutlined,
} from '@ant-design/icons';
import { mockFAQs, trendData, recentUpdates } from '../mock/data';
import { getFAQs, getFAQDetail, getDocumentDetail, getTrends, getRecent } from '../api';
import SimpleMarkdown from './SimpleMarkdown';
import MiniChart from './MiniChart';
import ModuleSelect from './ModuleSelect';
import DeptCascader from './DeptCascader';

const { Text, Paragraph } = Typography;

function RightPanel({ selectedDoc, onClearDoc, isDark }) {
  const [faqs, setFaqs] = useState([]);
  const [docDetail, setDocDetail] = useState(null);
  const [docLoading, setDocLoading] = useState(false);
  const [selectedFaq, setSelectedFaq] = useState(null); // FAQ 详情
  const [faqLoading, setFaqLoading] = useState(false);
  const [trendData, setTrendData] = useState([]);
  const [faqTrendData, setFaqTrendData] = useState([]);
  const [recentData, setRecentData] = useState([]);
  const [editingFaq, setEditingFaq] = useState(false);
  const [savingFaq, setSavingFaq] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editDept, setEditDept] = useState('');
  const [editDeptIds, setEditDeptIds] = useState([]);  // 部门ID数组
  const [editModule, setEditModule] = useState('');

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
    // 切换文档时清除旧的 FAQ 详情，避免新 FAQ 加载被跳过
    setSelectedFaq(null);
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

  const handleEditFaq = () => {
    setEditingFaq(true);
    setEditTitle(selectedFaq.title || '');
    setEditKeywords((selectedFaq.keywords || []).join(', '));
    setEditContent(selectedFaq.content || selectedFaq.answer || '');
    setEditDept(selectedFaq.dept || '数智财务组');
    setEditModule(selectedFaq.sub_module || selectedFaq.module || '');
  };

  const handleSaveFaq = async () => {
    setSavingFaq(true);
    try {
      const params = new URLSearchParams({
        title: editTitle,
        keywords: editKeywords,
        dept: editDept,
        sub_module: editModule,
        module: editModule,
        content: editContent,
        status: 'active',
      });
      const resp = await fetch(`/api/faq/save?${params.toString()}`);
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || `保存失败 (HTTP ${resp.status})`);
      }
      setEditingFaq(false);
      setSelectedFaq(prev => ({
        ...prev,
        title: editTitle,
        keywords: editKeywords.split(',').map(k => k.trim()).filter(Boolean),
        content: editContent,
      }));
      message.success(data.warning || 'FAQ 保存成功');
    } catch (err) {
      message.error(`保存失败: ${err.message}`);
    } finally {
      setSavingFaq(false);
    }
  };

  // ===== FAQ 详情视图 =====
  if (selectedFaq && !selectedDoc) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => { setSelectedFaq(null); setEditingFaq(false); }}
            style={{ padding: '4px 8px', fontSize: 13, color: '#0D9488' }}>返回</Button>
          {!editingFaq ? (
            <Button type="text" size="small" onClick={handleEditFaq} style={{ fontSize: 12, color: '#0D9488' }}>编辑</Button>
          ) : (
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="small" onClick={() => setEditingFaq(false)} style={{ fontSize: 12 }}>取消</Button>
              <Button type="primary" size="small" onClick={handleSaveFaq} loading={savingFaq} style={{ fontSize: 12 }}>保存</Button>
            </div>
          )}
        </div>

        {faqLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : editingFaq ? (
          <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Input value={editTitle} onChange={e => setEditTitle(e.target.value)} placeholder="FAQ 标题" />
            <Input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} placeholder="关键词（逗号分隔）" />
            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>所属部门</Text>
                <DeptCascader
                  value={editDeptIds}
                  onChange={(ids, names) => { setEditDeptIds(ids); setEditDept(names.join(', ')); }}
                  placeholder="选择部门"
                />
              </div>
              <div style={{ flex: 1 }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>所属模块</Text>
                <ModuleSelect value={editModule} onChange={setEditModule} placeholder="输入模块名搜索..." />
              </div>
            </div>
            <Input.TextArea value={editContent} onChange={e => setEditContent(e.target.value)} rows={12} placeholder="FAQ 内容" />
          </div>
        ) : (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 8, color: isDark ? '#e5e5e5' : '#0D9488' }}>
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
            <SimpleMarkdown content={selectedFaq.content || selectedFaq.answer} isDark={isDark} />
          </div>
        )}
      </div>
    );
  }

  // ===== 文档详情视图 =====
  if (selectedDoc) {
    // FAQ 文档自动切换到 FAQ 详情视图（支持编辑）
    const isFaqDoc = selectedDoc.path?.includes('faq/') || selectedDoc.path?.includes('FAQ知识库');
    if (isFaqDoc && !selectedFaq) {
      const faqId = selectedDoc.id || selectedDoc.faq_id || '';
      const faqInfo = {
        id: faqId,
        title: selectedDoc.title || '',
        path: selectedDoc.path || '',
        keywords: selectedDoc.keywords || [],
        dept: selectedDoc.dept || '',
        sub_module: selectedDoc.sub_module || '',
        module: selectedDoc.module || '',
        content: selectedDoc.content || selectedDoc.snippets?.join('\n') || '',
      };
      // 异步加载完整FAQ内容，加载后清除 selectedDoc 让 FAQ 视图渲染
      fetch(`/api/faq?id=${faqId}`).then(r => r.json()).then(data => {
        if (data && !data.error) {
          setSelectedFaq({ ...faqInfo, ...data, content: data.content || faqInfo.content });
        } else {
          setSelectedFaq(faqInfo);
        }
        onClearDoc(); // 清除 selectedDoc，让 FAQ 视图接管
      }).catch(() => {
        setSelectedFaq(faqInfo);
        onClearDoc();
      });
      return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>;
    }

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

            <SimpleMarkdown content={docDetail.content} isDark={isDark} />
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
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto', padding: 16 }}>
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

      {/* FAQ 列表 */}
      <div style={{ marginBottom: 16, flexShrink: 0 }}>
        {displayFAQs.slice(0, 3).map(faq => (
          <div
            key={faq.id}
            onClick={() => handleFaqClick(faq)}
            style={{
              marginBottom: 6, border: `1px solid ${isDark ? '#333' : '#f0f0f0'}`, borderRadius: 8,
              padding: '8px 10px', cursor: 'pointer', background: isDark ? '#1e1e1e' : '#fff',
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

      {/* ===== 趋势图（一行两个） ===== */}
      <div style={{ marginBottom: 16, flexShrink: 0 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>数据趋势</Text>
        <Row gutter={[8, 8]}>
          <Col span={12}>
            <div style={{ border: `1px solid ${isDark ? '#333' : '#f0f0f0'}`, borderRadius: 8, padding: 8, background: isDark ? '#1e1e1e' : '#fff' }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>FAQ趋势</div>
              <MiniChart data={faqTrendData.length > 0 ? faqTrendData : [{month:'-',value:0}]} color="#2DD4BF" height={40} />
            </div>
          </Col>
          <Col span={12}>
            <div style={{ border: `1px solid ${isDark ? '#333' : '#f0f0f0'}`, borderRadius: 8, padding: 8, background: isDark ? '#1e1e1e' : '#fff' }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>文档趋势</div>
              <MiniChart data={trendData.length > 0 ? trendData : [{month:'-',value:0}]} color="#0D9488" height={40} />
            </div>
          </Col>
        </Row>
      </div>

      {/* ===== 最近更新 ===== */}
      <div style={{ flexShrink: 0 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>最近更新</Text>
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: '8px 10px' }}>
          {(recentData.length > 0 ? recentData : recentUpdates).slice(0, 5).map((item, i) => (
            <div key={item.name || i} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '4px 0',
              borderBottom: i < 4 ? `1px solid ${isDark ? '#333' : '#f5f5f5'}` : 'none',
            }}>
              <Avatar size={20} style={{ backgroundColor: '#0D9488', fontSize: 10, flexShrink: 0 }}>
                {item.dept?.[0] || '文'}
              </Avatar>
              <Text ellipsis style={{ fontSize: 11, flex: 1 }}>{item.name}</Text>
              <Text type="secondary" style={{ fontSize: 10, whiteSpace: 'nowrap', flexShrink: 0 }}>
                {item.updated?.slice(5) || ''}
              </Text>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default RightPanel;