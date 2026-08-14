/**
 * RightPanel.jsx - 右侧侧边信息看板
 *
 * 模块：
 * 1. 高频FAQ + 工单问题沉淀（含趋势折线图）
 * 2. 相关产品文档（含趋势图）
 * 3. 最近更新
 */

import React, { useState, useEffect } from 'react';
import { Typography, Empty, Tag, Badge, Avatar, Row, Col } from 'antd';
import {
  QuestionCircleOutlined, FileTextOutlined, ClockCircleOutlined,
  ArrowUpOutlined, RightOutlined,
} from '@ant-design/icons';
import { mockFAQs, trendData, recentUpdates, docListData } from '../mock/data';
import { getFAQs } from '../api';

const { Text } = Typography;

/**
 * 迷你 SVG 折线图
 */
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

function RightPanel() {
  const [faqs, setFaqs] = useState([]);

  // 加载 FAQ 数据
  useEffect(() => {
    getFAQs().then(data => {
      if (data && data.length > 0) setFaqs(data);
    });
  }, []);

  const displayFAQs = faqs.length > 0 ? faqs : mockFAQs;
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
      {/* ===== 1. 高频FAQ - 工单问题沉淀 ===== */}
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
              <MiniChart data={trendData} color="#0D9488" />
            </div>
          </Col>
          <Col span={12}>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 8, height: 90 }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>重复热点问题</div>
              <MiniChart data={trendData.slice().reverse()} color="#2DD4BF" />
            </div>
          </Col>
        </Row>
      </div>

      {/* FAQ 列表 */}
      <div style={{ marginBottom: 16 }}>
        {displayFAQs.slice(0, 3).map(faq => (
          <div
            key={faq.id}
            style={{
              marginBottom: 6, border: '1px solid #f0f0f0', borderRadius: 8,
              padding: '8px 10px', cursor: 'pointer', background: '#fff',
            }}
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
              <MiniChart data={trendData} color="#0D9488" />
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
              {recentUpdates.slice(0, 3).map(item => (
                <div key={item.id} style={{ marginBottom: 6, fontSize: 11 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Avatar size={16} style={{ backgroundColor: item.type === 'add' ? '#52c41a' : '#0D9488', fontSize: 9 }}>
                      {item.author[0]}
                    </Avatar>
                    <Text ellipsis style={{ fontSize: 11, flex: 1 }}>{item.title}</Text>
                  </div>
                  <div style={{ paddingLeft: 20, marginTop: 1 }}>
                    <Tag color={item.type === 'add' ? 'green' : 'default'} style={{ fontSize: 9, borderRadius: 3, lineHeight: '14px' }}>
                      {item.type === 'add' ? '新增' : '编辑'}
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