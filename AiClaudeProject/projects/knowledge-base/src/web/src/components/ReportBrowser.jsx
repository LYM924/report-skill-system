/**
 * ReportBrowser.jsx - 报表数据浏览组件
 *
 * 展示周报、月报、年度报表列表。支持分类筛选和预览。
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Spin, Empty, Tag, Segmented } from 'antd';
import { BarChartOutlined, RightOutlined, CalendarOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

function ReportBrowser({ isDark, onSelectDoc }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('');

  const loadReports = (cat) => {
    setLoading(true);
    const url = cat ? `/api/reports?category=${encodeURIComponent(cat)}` : '/api/reports';
    fetch(url)
      .then(r => r.json())
      .then(data => {
        setReports(data?.reports || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadReports(''); }, []);

  const handleCategoryChange = (val) => {
    setCategory(val || '');
    loadReports(val || '');
  };

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BarChartOutlined style={{ fontSize: 20, color: '#D97706' }} />
          <Text strong style={{ fontSize: 18, color: isDark ? '#e5e5e5' : '#1e293b' }}>
            报表数据 ({reports.length})
          </Text>
        </div>
        <Segmented
          options={[
            { label: '全部', value: '' },
            { label: '周报', value: '周报' },
            { label: '月报', value: '月报' },
            { label: '年度', value: '年度报表' },
          ]}
          value={category}
          onChange={handleCategoryChange}
        />
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : reports.length === 0 ? (
        <Empty description="暂无报表数据" />
      ) : (
        <Card style={{ borderRadius: 12, border: `1px solid ${isDark ? '#303030' : '#e2e8f0'}` }}>
          {reports.map((r, i) => (
            <div
              key={r.id || i}
              onClick={() => onSelectDoc({ ...r, title: r.title, path: r.path, source: 'report_data' })}
              style={{
                padding: '14px 16px',
                borderBottom: i < reports.length - 1 ? `1px solid ${isDark ? '#303030' : '#f0f0f0'}` : 'none',
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = isDark ? '#222' : '#fafafa'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 6,
                  background: 'rgba(217,119,6,0.1)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, marginTop: 2,
                }}>
                  <BarChartOutlined style={{ color: '#D97706', fontSize: 14 }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <Text strong style={{ fontSize: 14, color: isDark ? '#e5e5e5' : '#1e293b' }}>
                      {r.title}
                    </Text>
                    {r.week && (
                      <Tag color="orange" style={{ fontSize: 11, borderRadius: 4, margin: 0 }}>
                        W{r.week}
                      </Tag>
                    )}
                    {r.category && (
                      <Tag style={{ fontSize: 11, borderRadius: 4, margin: 0 }}>
                        {r.category}
                      </Tag>
                    )}
                  </div>
                  {r.summary && (
                    <Paragraph
                      ellipsis={{ rows: 2 }}
                      style={{ fontSize: 12, color: isDark ? '#999' : '#6B7280', margin: '4px 0 0', lineHeight: 1.7 }}
                    >
                      {r.summary}
                    </Paragraph>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }}>
                    <CalendarOutlined style={{ fontSize: 11, color: '#999' }} />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : (r.year ? `${r.year}年` : '')}
                    </Text>
                  </div>
                </div>
                <RightOutlined style={{ color: '#ccc', fontSize: 12, marginTop: 8 }} />
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

export default ReportBrowser;