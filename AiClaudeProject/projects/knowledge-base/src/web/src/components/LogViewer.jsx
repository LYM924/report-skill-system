/**
 * LogViewer.jsx - 系统日志查看器
 *
 * 展示搜索服务器日志，支持颜色编码和刷新。
 */
import React, { useState, useEffect } from 'react';
import { Typography, Card, Button, Empty, Spin } from 'antd';

const { Text } = Typography;

function LogViewer() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadLogs = () => {
    setLoading(true);
    fetch('/api/logs?lines=200')
      .then(r => r.json())
      .then(data => {
        setLogs(data?.logs || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadLogs(); }, []);

  return (
    <Card style={{ borderRadius: 12, marginTop: 20, border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text strong style={{ fontSize: 15 }}>系统日志</Text>
        <Button size="small" onClick={loadLogs} loading={loading}>刷新</Button>
      </div>
      {/* 颜色图例 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
        {[
          { color: '#f87171', label: '错误 ERROR' },
          { color: '#60a5fa', label: '搜索 SEARCH' },
          { color: '#4ade80', label: 'FAQ操作' },
          { color: '#fbbf24', label: '服务启动' },
          { color: '#94a3b8', label: '常规日志' },
        ].map(item => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#666' }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: item.color }} />
            {item.label}
          </div>
        ))}
      </div>
      {loading ? (
        <Spin />
      ) : logs.length === 0 ? (
        <Empty description="暂无日志" />
      ) : (
        <div style={{
          background: '#1e293b', color: '#e2e8f0', borderRadius: 8, padding: '12px 16px',
          maxHeight: 500, overflow: 'auto', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.8,
          whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        }}>
          {logs.map((line, i) => (
            <div key={i} style={{
              color: line.includes('ERROR') ? '#f87171' :
                     line.includes('SEARCH') ? '#60a5fa' :
                     line.includes('FAQ_SAVE') ? '#4ade80' :
                     line.includes('SERVER_START') ? '#fbbf24' : '#94a3b8',
            }}>
              {line}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default LogViewer;