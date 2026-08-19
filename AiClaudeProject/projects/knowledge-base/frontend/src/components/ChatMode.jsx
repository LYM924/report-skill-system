/**
 * ChatMode.jsx - AI 对话模式
 *
 * 对接 /api/chat SSE 流式接口，实时展示 AI 回复
 */
import React, { useState, useRef } from 'react';
import { Typography, Input, Button, Card, Avatar, Space } from 'antd';
import { RobotOutlined, LoadingOutlined, SendOutlined, UserOutlined, ThunderboltOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

const SUGGESTIONS = [
  '浙里报报销单怎么创建？',
  '预算指标同步失败怎么处理？',
  '发票上传后无法识别怎么办？',
  '合同审批流程在哪里配置？',
  '公务出行报销单选不到申请单？',
  '预防接种记录无法保存？',
];

function ChatMode({ isDark }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);

  const handleSend = (text) => {
    const msg = (text || input).trim();
    if (!msg || streaming) return;
    const userMsg = { role: 'user', content: msg };
    setMessages(prev => [...prev, userMsg]);
    if (!text) setInput('');
    setStreaming(true);

    const aiMsg = { role: 'assistant', content: '' };
    setMessages(prev => [...prev, aiMsg]);

    const controller = new AbortController();
    abortRef.current = controller;

    fetch(`${API_BASE}/chat?message=${encodeURIComponent(userMsg.content)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') { setStreaming(false); return; }
              try {
                const parsed = JSON.parse(data);
                if (parsed.error) {
                  setMessages(prev => { const u = [...prev]; u[u.length-1] = {...u[u.length-1], content: `⚠️ ${parsed.error}`}; return u; });
                  setStreaming(false); return;
                }
                if (parsed.text) {
                  setMessages(prev => { const u = [...prev]; u[u.length-1] = {...u[u.length-1], content: u[u.length-1].content + parsed.text}; return u; });
                }
              } catch (e) {}
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setMessages(prev => { const u = [...prev]; u[u.length-1] = {...u[u.length-1], content: `⚠️ 请求失败：${err.message}`}; return u; });
        }
        setStreaming(false);
      });
  };

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div style={{ width: '100%', height: 'calc(100vh - 140px)', display: 'flex', flexDirection: 'column' }}>
      {/* 头部 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexShrink: 0 }}>
        <Avatar size={40} icon={<RobotOutlined />} style={{ backgroundColor: '#0D9488' }} />
        <div>
          <Text strong style={{ fontSize: 18, color: isDark ? '#e5e5e5' : '#1e293b' }}>AI 助手</Text>
          <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>基于 Claude 大模型，实时流式回复</Text>
        </div>
      </div>

      {/* 对话区 */}
      <div style={{ flex: 1, overflow: 'auto', marginBottom: 16 }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', paddingTop: 60 }}>
            <RobotOutlined style={{ fontSize: 48, color: '#0D9488', opacity: 0.3, marginBottom: 16 }} />
            <Text type="secondary" style={{ fontSize: 15, display: 'block', marginBottom: 24 }}>
              输入问题开始对话，AI 将实时流式回复
            </Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 600, margin: '0 auto' }}>
              {SUGGESTIONS.map((s, i) => (
                <Button
                  key={i}
                  size="small"
                  onClick={() => handleSend(s)}
                  style={{
                    borderRadius: 16, fontSize: 12, padding: '4px 14px',
                    border: `1px solid ${isDark ? '#333' : '#e2e8f0'}`,
                    color: isDark ? '#bbb' : '#555',
                    background: isDark ? '#1e1e1e' : '#fff',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#0D9488'; e.currentTarget.style.color = '#0D9488'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = isDark ? '#333' : '#e2e8f0'; e.currentTarget.style.color = isDark ? '#bbb' : '#555'; }}
                >
                  {s}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 20, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              alignItems: 'flex-start', gap: 10,
            }}>
              {msg.role === 'assistant' && (
                <Avatar size={32} icon={<RobotOutlined />} style={{ backgroundColor: '#0D9488', flexShrink: 0 }} />
              )}
              <div style={{
                maxWidth: '75%', padding: '12px 16px', borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                background: msg.role === 'user' ? '#0D9488' : (isDark ? '#262626' : '#f1f5f9'),
                color: msg.role === 'user' ? '#fff' : (isDark ? '#e5e5e5' : '#334155'),
                fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {msg.content}
                {i === messages.length - 1 && msg.role === 'assistant' && streaming && (
                  <LoadingOutlined style={{ marginLeft: 4, color: '#0D9488', fontSize: 12 }} />
                )}
              </div>
              {msg.role === 'user' && (
                <Avatar size={32} icon={<UserOutlined />} style={{ backgroundColor: '#2563EB', flexShrink: 0 }} />
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        <Input.TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => { e.preventDefault(); handleSend(); }}
          placeholder="输入问题，Enter 发送..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1, borderRadius: 10 }}
          disabled={streaming}
        />
        <Button
          type="primary"
          size="large"
          onClick={() => handleSend()}
          icon={streaming ? <LoadingOutlined /> : <SendOutlined />}
          loading={streaming}
          style={{ borderRadius: 10, minWidth: 80 }}
        >
          发送
        </Button>
      </div>
    </div>
  );
}

export default ChatMode;