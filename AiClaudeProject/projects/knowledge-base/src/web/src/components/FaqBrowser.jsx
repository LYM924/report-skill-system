/**
 * FaqBrowser.jsx - FAQ 部门浏览组件
 *
 * 左侧 FAQ库 点击部门后，在中间面板展示该部门下的 FAQ 列表
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Tag, Spin, Empty } from 'antd';
import { QuestionCircleOutlined, RightOutlined } from '@ant-design/icons';

const { Text } = Typography;

function FaqBrowser({ dept, isDark, onSelectDoc }) {
  const [faqs, setFaqs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch('/api/faq')
      .then(r => r.json())
      .then(data => {
        const all = data?.faqs || [];
        setFaqs(all.filter(f => f.dept === dept));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [dept]);

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <QuestionCircleOutlined style={{ fontSize: 20, color: '#0D9488' }} />
        <Text strong style={{ fontSize: 18, color: isDark ? '#e5e5e5' : '#1e293b' }}>
          {dept} · FAQ ({faqs.length})
        </Text>
      </div>
      {loading ? (
        <Spin />
      ) : faqs.length === 0 ? (
        <Empty description="该部门暂无 FAQ" />
      ) : (
        <Card style={{ borderRadius: 12, border: `1px solid ${isDark ? '#303030' : '#e2e8f0'}` }}>
          {faqs.map((faq, i) => (
            <div
              key={faq.id || i}
              onClick={() => onSelectDoc({ ...faq, title: faq.title, path: faq.path })}
              style={{
                padding: '14px 16px',
                borderBottom: i < faqs.length - 1 ? `1px solid ${isDark ? '#303030' : '#f0f0f0'}` : 'none',
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = isDark ? '#222' : '#fafafa'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <QuestionCircleOutlined style={{ color: '#0D9488', fontSize: 14, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <Text strong style={{ fontSize: 14, color: isDark ? '#e5e5e5' : '#1e293b' }}>
                    {faq.title}
                  </Text>
                  <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {faq.keywords?.slice(0, 4).map(k => (
                      <Tag key={k} style={{ fontSize: 10, borderRadius: 4, margin: 0 }}>{k}</Tag>
                    ))}
                    <Tag style={{ fontSize: 10, borderRadius: 4, margin: 0, color: '#0D9488', background: 'rgba(13,148,136,0.08)', border: 'none' }}>
                      {faq.id || faq.faq_id}
                    </Tag>
                  </div>
                </div>
                <RightOutlined style={{ color: '#ccc', fontSize: 12 }} />
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

export default FaqBrowser;