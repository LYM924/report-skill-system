/**
 * StatsDashboard.jsx - 问答统计面板
 *
 * 展示问答统计数据和搜索热词 Top 10。
 * 通过 getHotwords API 获取热词数据，无数据时使用默认示例。
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Row, Col } from 'antd';
import { getHotwords } from '../api';

const { Text } = Typography;

/** 问答统计面板 */
function StatsDashboard({ isDark }) {
  const [hotwords, setHotwords] = useState([]);

  useEffect(() => {
    getHotwords().then(data => {
      if (data?.hotwords) setHotwords(data.hotwords);
    });
  }, []);

  return (
    <div style={{ width: '100%' }}>
      <Text strong style={{ fontSize: 20, display: 'block', marginBottom: 20, color: isDark ? '#e5e5e5' : '#1e293b' }}>问答统计</Text>
      <Row gutter={[16, 16]}>
        {[
          { label: '今日搜索', value: 128, color: '#0D9488' },
          { label: 'FAQ 命中', value: 86, color: '#2563EB' },
          { label: 'AI 总结', value: 42, color: '#D97706' },
          { label: '满意度', value: '94%', color: '#7C3AED' },
        ].map((item, i) => (
          <Col span={6} key={i}>
            <Card style={{ borderRadius: 12, border: '1px solid #e2e8f0', textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 13 }}>{item.label}</Text>
              <div style={{ fontSize: 36, fontWeight: 700, color: item.color, marginTop: 8 }}>{item.value}</div>
            </Card>
          </Col>
        ))}
      </Row>
      <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 16 }}>搜索热词 Top 10</Text>
        {(hotwords.length > 0 ? hotwords.map(h => h.word) : ['报销单', '选不到', '预算', '审批', '发票', '合同', '采购', '支付', '工资', '考勤']).map((word, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: '#999', width: 20 }}>{i + 1}</span>
            <span style={{ fontSize: 13, color: isDark ? '#ccc' : '#334155' }}>{word}</span>
            <div style={{ flex: 1, height: 6, background: isDark ? '#333' : '#f0f0f0', borderRadius: 3 }}>
              <div style={{ width: `${100 - i * 8}%`, height: '100%', background: '#0D9488', borderRadius: 3 }} />
            </div>
            <span style={{ fontSize: 12, color: '#999', width: 40, textAlign: 'right' }}>{(hotwords[i]?.count || 100 - i * 8)}次</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

export default StatsDashboard;