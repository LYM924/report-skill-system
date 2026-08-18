/**
 * ChatMode.jsx - AI 对话模式
 *
 * 全屏对话界面，支持用户输入和 AI 回复。
 * 当前为前端模拟版本，完整对话需后端支持 `/api/chat` 端点。
 */
import React, { useState } from 'react';
import { Typography, Input, Button, Empty } from 'antd';
import { RobotOutlined } from '@ant-design/icons';

const { Text } = Typography;

/** AI 对话模式 */
function ChatMode({ isDark, onSearchResultsChange }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    // Simulate AI response (would need backend SSE endpoint for chat)
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'assistant', content: '这是 AI 对话模式。当前版本支持搜索后 AI 总结，纯对话模式需要后端额外支持 `/api/chat` 端点。' }]);
    }, 1000);
    setInput('');
  };

  return (
    <div style={{ width: '100%', height: 'calc(100vh - 140px)', display: 'flex', flexDirection: 'column' }}>
      <Text strong style={{ fontSize: 20, display: 'block', marginBottom: 20, color: isDark ? '#e5e5e5' : '#1e293b' }}>AI 助手</Text>
      <div style={{ flex: 1, overflow: 'auto', marginBottom: 16 }}>
        {messages.length === 0 ? (
          <Empty description="输入问题开始对话" style={{ marginTop: 80 }} />
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 16, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                maxWidth: '70%', padding: '12px 16px', borderRadius: 12,
                background: msg.role === 'user' ? '#0D9488' : (isDark ? '#333' : '#f1f5f9'),
                color: msg.role === 'user' ? '#fff' : (isDark ? '#e5e5e5' : '#334155'),
                fontSize: 14, lineHeight: 1.7,
              }}>
                {msg.content}
              </div>
            </div>
          ))
        )}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Input.TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => { e.preventDefault(); handleSend(); }}
          placeholder="输入问题..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1 }}
        />
        <Button type="primary" onClick={handleSend} icon={<RobotOutlined />}>发送</Button>
      </div>
    </div>
  );
}

export default ChatMode;