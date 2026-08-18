/**
 * ChatMode.jsx - AI 对话模式
 *
 * 对接 /api/chat SSE 流式接口，实时展示 AI 回复
 */
import React, { useState, useRef } from 'react';
import { Typography, Input, Button, Empty, Spin } from 'antd';
import { RobotOutlined, LoadingOutlined, SendOutlined } from '@ant-design/icons';

const { Text } = Typography;

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

function ChatMode({ isDark }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);

  const handleSend = () => {
    if (!input.trim() || streaming) return;
    const userMsg = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setStreaming(true);

    // 创建 AI 回复占位
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
              if (data === '[DONE]') {
                setStreaming(false);
                return;
              }
              try {
                const parsed = JSON.parse(data);
                if (parsed.error) {
                  setMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1] = {
                      ...updated[updated.length - 1],
                      content: `⚠️ 错误：${parsed.error}`,
                    };
                    return updated;
                  });
                  setStreaming(false);
                  return;
                }
                if (parsed.text) {
                  setMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1] = {
                      ...updated[updated.length - 1],
                      content: updated[updated.length - 1].content + parsed.text,
                    };
                    return updated;
                  });
                }
              } catch (e) {
                // 跳过解析失败的行
              }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: `⚠️ 请求失败：${err.message}`,
            };
            return updated;
          });
        }
        setStreaming(false);
      });
  };

  // 自动滚动到底部
  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div style={{ width: '100%', height: 'calc(100vh - 140px)', display: 'flex', flexDirection: 'column' }}>
      <Text strong style={{ fontSize: 20, display: 'block', marginBottom: 20, color: isDark ? '#e5e5e5' : '#1e293b' }}>AI 助手</Text>
      <div style={{ flex: 1, overflow: 'auto', marginBottom: 16 }}>
        {messages.length === 0 ? (
          <Empty description="输入问题开始对话，AI 将实时流式回复" style={{ marginTop: 80 }} />
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 16, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                maxWidth: '70%', padding: '12px 16px', borderRadius: 12,
                background: msg.role === 'user' ? '#0D9488' : (isDark ? '#333' : '#f1f5f9'),
                color: msg.role === 'user' ? '#fff' : (isDark ? '#e5e5e5' : '#334155'),
                fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {msg.content}
                {i === messages.length - 1 && msg.role === 'assistant' && streaming && (
                  <LoadingOutlined style={{ marginLeft: 4, color: '#0D9488', fontSize: 12 }} />
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Input.TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => { e.preventDefault(); handleSend(); }}
          placeholder="输入问题..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1 }}
          disabled={streaming}
        />
        <Button
          type="primary"
          onClick={handleSend}
          icon={streaming ? <LoadingOutlined /> : <SendOutlined />}
          loading={streaming}
        >
          发送
        </Button>
      </div>
    </div>
  );
}

export default ChatMode;