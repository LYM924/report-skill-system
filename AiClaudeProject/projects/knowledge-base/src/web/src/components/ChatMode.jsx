/**
 * ChatMode.jsx - AI 对话模式
 *
 * 卡片式设计，自适应页面宽度
 * 主色：浅青绿（降低饱和度，柔和护眼）
 * 卡片背景：#fafbfc，分割线：浅灰细线，圆角：10-12px
 */
import React, { useState, useRef } from 'react';
import { Typography, Input, Button, Avatar, Tag } from 'antd';
import { RobotOutlined, LoadingOutlined, SendOutlined, UserOutlined, ThunderboltOutlined, BulbOutlined, FileTextOutlined, LinkOutlined } from '@ant-design/icons';

const { Text } = Typography;

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

// 柔和浅青绿色系
const COLORS = {
  primary: '#5B9A8B',        // 浅青绿主色
  primaryLight: '#E8F4F1',   // 主色浅底
  primaryHover: '#4A8A7C',   // hover 加深
  cardBg: '#fafbfc',         // 卡片背景（非纯白）
  divider: '#eef0f2',        // 浅灰分割线
  userBubble: '#5B9A8B',     // 用户气泡
  aiBubble: '#f5f7f8',       // AI 气泡
  text: '#334155',           // 正文
  textSecondary: '#94a3b8',  // 辅助文字
  border: '#eef0f2',         // 卡片边框
  shadow: '0 1px 3px rgba(0,0,0,0.04)', // 极浅阴影
  white: '#fff',
};

const SUGGESTIONS = [
  { icon: '浙里报报销单怎么创建？', key: '报销' },
  { icon: '预算指标同步失败怎么处理？', key: '预算' },
  { icon: '发票上传后无法识别怎么办？', key: '发票' },
  { icon: '合同审批流程在哪里配置？', key: '合同' },
  { icon: '公务出行报销单选不到申请单？', key: '出行' },
  { icon: '预防接种记录无法保存？', key: '接种' },
];

const QUESTIONS = [
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

    fetch(`${API_BASE}/rag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userMsg.content }),
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
                  const msg = parsed.message || parsed.error;
                  setMessages(prev => { const u = [...prev]; u[u.length-1] = {...u[u.length-1], content: `⚠️ ${msg}`}; return u; });
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

  // 深色模式适配
  const theme = isDark ? {
    ...COLORS,
    cardBg: '#1e1e1e',
    aiBubble: '#262626',
    text: '#e5e5e5',
    textSecondary: '#888',
    border: '#303030',
    divider: '#303030',
    shadow: 'none',
    white: '#1a1a1a',
  } : COLORS;

  return (
    <div style={{
      width: '100%', height: 'calc(100vh - 140px)',
      display: 'flex', flexDirection: 'column',
      maxWidth: 900, margin: '0 auto',
    }}>
      {/* ===== 头部卡片 ===== */}
      <div style={{
        background: theme.cardBg,
        border: `1px solid ${theme.border}`,
        borderRadius: 12,
        padding: '16px 20px',
        marginBottom: 16,
        flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 14,
        boxShadow: theme.shadow,
      }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: `linear-gradient(135deg, ${COLORS.primary} 0%, #7EC8B8 100%)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <RobotOutlined style={{ fontSize: 22, color: '#fff' }} />
        </div>
        <div style={{ flex: 1 }}>
          <Text strong style={{ fontSize: 17, color: theme.text }}>AI 智能问答</Text>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', color: theme.textSecondary }}>
            RAG 检索增强 · 基于知识库实时回答 · 引用来源
          </Text>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 12px', borderRadius: 20,
          background: COLORS.primaryLight,
          fontSize: 11, color: COLORS.primary,
        }}>
          <div style={{ width: 6, height: 6, borderRadius: 3, background: '#22c55e' }} />
          在线
        </div>
      </div>

      {/* ===== 对话区 ===== */}
      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 8 }}>
        {messages.length === 0 ? (
          /* ===== 欢迎页 ===== */
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            paddingTop: '8%',
          }}>
            {/* 大图标 */}
            <div style={{
              width: 72, height: 72, borderRadius: 18,
              background: `linear-gradient(135deg, ${COLORS.primary} 0%, #7EC8B8 100%)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 20, opacity: 0.9,
            }}>
              <RobotOutlined style={{ fontSize: 36, color: '#fff' }} />
            </div>

            <Text style={{ fontSize: 18, fontWeight: 600, color: theme.text, marginBottom: 6 }}>
              你好，有什么可以帮你？
            </Text>
            <Text style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 28 }}>
              AI 将基于知识库检索相关文档后回答，并标注引用来源
            </Text>

            {/* 推荐问题卡片网格 */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 10, width: '100%', maxWidth: 750,
            }}>
              {QUESTIONS.map((q, i) => (
                <div
                  key={i}
                  onClick={() => handleSend(q)}
                  style={{
                    background: theme.cardBg,
                    border: `1px solid ${theme.border}`,
                    borderRadius: 10,
                    padding: '14px 16px',
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 10,
                    transition: 'all 0.2s ease',
                    boxShadow: theme.shadow,
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = COLORS.primary;
                    e.currentTarget.style.boxShadow = `0 2px 8px rgba(91,154,139,0.12)`;
                    e.currentTarget.style.transform = 'translateY(-1px)';
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = theme.border;
                    e.currentTarget.style.boxShadow = theme.shadow;
                    e.currentTarget.style.transform = 'none';
                  }}
                >
                  <div style={{
                    width: 32, height: 32, borderRadius: 8,
                    background: COLORS.primaryLight,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <BulbOutlined style={{ fontSize: 14, color: COLORS.primary }} />
                  </div>
                  <Text style={{ fontSize: 13, color: theme.text, lineHeight: 1.4 }}>{q}</Text>
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* ===== 消息列表 ===== */
          messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 16, display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              alignItems: 'flex-start', gap: 10,
              padding: '0 2px',
            }}>
              {/* AI 头像 */}
              {msg.role === 'assistant' && (
                <div style={{
                  width: 34, height: 34, borderRadius: 10,
                  background: `linear-gradient(135deg, ${COLORS.primary} 0%, #7EC8B8 100%)`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <RobotOutlined style={{ fontSize: 16, color: '#fff' }} />
                </div>
              )}

              {/* 消息气泡卡片 */}
              <div style={{
                maxWidth: '78%', padding: '12px 18px',
                borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                background: msg.role === 'user'
                  ? `linear-gradient(135deg, ${COLORS.primary} 0%, #6DAFA0 100%)`
                  : theme.aiBubble,
                border: msg.role === 'assistant' ? `1px solid ${theme.border}` : 'none',
                color: msg.role === 'user' ? '#fff' : theme.text,
                fontSize: 14, lineHeight: 1.75,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                boxShadow: msg.role === 'assistant' ? 'none' : `0 1px 3px rgba(91,154,139,0.15)`,
              }}>
                {msg.content}
                {i === messages.length - 1 && msg.role === 'assistant' && streaming && (
                  <LoadingOutlined style={{ marginLeft: 4, color: COLORS.primary, fontSize: 12 }} />
                )}
              </div>

              {/* 用户头像 */}
              {msg.role === 'user' && (
                <div style={{
                  width: 34, height: 34, borderRadius: 10,
                  background: '#e2e8f0',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <UserOutlined style={{ fontSize: 16, color: '#64748b' }} />
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* ===== 分割线 ===== */}
      <div style={{ height: 1, background: theme.divider, margin: '0 0 12px 0', flexShrink: 0 }} />

      {/* ===== 输入区卡片 ===== */}
      <div style={{
        background: theme.cardBg,
        border: `1px solid ${theme.border}`,
        borderRadius: 12,
        padding: '12px 16px',
        display: 'flex', gap: 10, alignItems: 'flex-end',
        flexShrink: 0,
        boxShadow: theme.shadow,
      }}>
        <Input.TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => { e.preventDefault(); handleSend(); }}
          placeholder="输入问题，Enter 发送..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
          style={{
            flex: 1, borderRadius: 10, border: `1px solid ${theme.border}`,
            background: theme.white,
            fontSize: 14,
          }}
        />
        <Button
          type="primary"
          size="large"
          onClick={() => handleSend()}
          icon={streaming ? <LoadingOutlined /> : <SendOutlined />}
          loading={streaming}
          style={{
            borderRadius: 10, minWidth: 80, height: 40,
            background: `linear-gradient(135deg, ${COLORS.primary} 0%, #6DAFA0 100%)`,
            border: 'none',
            boxShadow: 'none',
          }}
        >
          发送
        </Button>
      </div>
    </div>
  );
}

export default ChatMode;