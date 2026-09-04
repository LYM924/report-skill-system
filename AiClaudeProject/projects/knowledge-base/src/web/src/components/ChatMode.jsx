/**
 * ChatMode.jsx - AI 对话模式
 *
 * 卡片式设计，自适应页面宽度
 * 主色：浅青绿（降低饱和度，柔和护眼）
 * 卡片背景：#fafbfc，分割线：浅灰细线，圆角：10-12px
 *
 * v2: 新增 👍👎📚 反馈+学习按钮，用户可标记回答并沉淀为知识
 */
import React, { useState, useRef } from 'react';
import { authFetch } from '../api';
import { Typography, Input, Button, Avatar, Tag, Modal, message, Tooltip } from 'antd';
import { RobotOutlined, LoadingOutlined, SendOutlined, UserOutlined, ThunderboltOutlined, BulbOutlined, FileTextOutlined, LinkOutlined, LikeOutlined, DislikeOutlined, BookOutlined, CheckCircleFilled, DislikeFilled } from '@ant-design/icons';
import { submitLearningCandidate, autoLearnFromFeedback } from '../api';

const { Text, Paragraph } = Typography;

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
  // 每条 AI 消息的反馈状态：msgIndex → 'useful' | 'not_useful' | null
  const [feedbackMap, setFeedbackMap] = useState({});
  // 学习弹窗
  const [learnModal, setLearnModal] = useState({ open: false, query: '', answer: '', idx: -1 });
  const [learnSubmitting, setLearnSubmitting] = useState(false);

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

    authFetch(`${API_BASE}/rag`, {
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

  // 👍 反馈
  const handleUseful = (idx, query, answer) => {
    if (feedbackMap[idx]) return;
    setFeedbackMap(prev => ({ ...prev, [idx]: 'useful' }));
    // 自动触发学习建议
    autoLearnFromFeedback({ query, answer, feedback_id: 0, session_id: '' })
      .then(res => {
        if (res?.ok) {
          message.success('已标记有用并加入学习候选池');
        }
      })
      .catch(() => {
        message.success('已标记有用');
      });
  };

  // 👎 反馈
  const handleNotUseful = (idx) => {
    if (feedbackMap[idx]) return;
    setFeedbackMap(prev => ({ ...prev, [idx]: 'not_useful' }));
    message.info('感谢反馈，我们会持续优化回答');
  };

  // 📚 学习按钮
  const handleLearn = (idx) => {
    const aiMsg = messages[idx];
    // 找到紧邻的前一条用户消息
    let userQuery = '';
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userQuery = messages[i].content;
        break;
      }
    }
    setLearnModal({ open: true, query: userQuery, answer: aiMsg?.content || '', idx });
  };

  const handleLearnSubmit = async () => {
    setLearnSubmitting(true);
    try {
      const res = await submitLearningCandidate({
        query: learnModal.query,
        answer: learnModal.answer,
        summary: '',  // 后台 AI 自动提取
        dept: '',
        module: '',
        keywords: [],
        source: 'manual',
      });
      if (res?.ok) {
        message.success('已提交到学习候选池，管理员审核后将沉淀为 FAQ');
        setLearnModal(prev => ({ ...prev, open: false }));
      } else {
        message.error(res?.error || '提交失败');
      }
    } catch (e) {
      message.error('提交失败：' + e.message);
    } finally {
      setLearnSubmitting(false);
    }
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
            RAG 检索增强 · 基于知识库实时回答 · 支持学习沉淀
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
              <div style={{ maxWidth: '78%' }}>
                <div style={{
                  padding: '12px 18px',
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

                {/* AI 回答反馈按钮（仅在回答完成后显示） */}
                {msg.role === 'assistant' && msg.content && !streaming && (
                  <div style={{
                    display: 'flex', gap: 4, marginTop: 6, paddingLeft: 4,
                  }}>
                    <Tooltip title={feedbackMap[i] ? undefined : '回答有用'}>
                      <Button
                        size="small" type="text"
                        icon={feedbackMap[i] === 'useful' ? <CheckCircleFilled style={{ color: COLORS.primary }} /> : <LikeOutlined />}
                        onClick={() => handleUseful(i, messages.slice(0, i).filter(m => m.role === 'user').pop()?.content || '', msg.content)}
                        disabled={!!feedbackMap[i]}
                        style={{
                          fontSize: 12, padding: '0 6px', height: 24,
                          color: feedbackMap[i] === 'useful' ? COLORS.primary : theme.textSecondary,
                        }}
                      />
                    </Tooltip>
                    <Tooltip title={feedbackMap[i] ? undefined : '回答没用'}>
                      <Button
                        size="small" type="text"
                        icon={feedbackMap[i] === 'not_useful' ? <DislikeFilled style={{ color: '#EF4444' }} /> : <DislikeOutlined />}
                        onClick={() => handleNotUseful(i)}
                        disabled={!!feedbackMap[i]}
                        style={{
                          fontSize: 12, padding: '0 6px', height: 24,
                          color: feedbackMap[i] === 'not_useful' ? '#EF4444' : theme.textSecondary,
                        }}
                      />
                    </Tooltip>
                    <Tooltip title="沉淀为知识">
                      <Button
                        size="small" type="text"
                        icon={<BookOutlined />}
                        onClick={() => handleLearn(i)}
                        style={{
                          fontSize: 12, padding: '0 6px', height: 24,
                          color: COLORS.primary,
                        }}
                      >
                        学习
                      </Button>
                    </Tooltip>
                  </div>
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

      {/* ===== 学习确认弹窗 ===== */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOutlined style={{ color: COLORS.primary }} />
            <span>沉淀为知识</span>
          </div>
        }
        open={learnModal.open}
        onOk={handleLearnSubmit}
        onCancel={() => setLearnModal(prev => ({ ...prev, open: false }))}
        okText="提交学习"
        cancelText="取消"
        confirmLoading={learnSubmitting}
        okButtonProps={{ style: { background: COLORS.primary, borderColor: COLORS.primary } }}
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>用户问题</Text>
          <Paragraph style={{ fontSize: 14, margin: '4px 0 0', color: theme.text }}>
            {learnModal.query}
          </Paragraph>
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>AI 回答</Text>
          <Paragraph
            ellipsis={{ rows: 6, expandable: true, symbol: '展开' }}
            style={{ fontSize: 13, margin: '4px 0 0', color: theme.text, background: theme.aiBubble, padding: 8, borderRadius: 8 }}
          >
            {learnModal.answer}
          </Paragraph>
        </div>
        <div style={{ marginTop: 12, padding: '8px 12px', background: COLORS.primaryLight, borderRadius: 8 }}>
          <Text style={{ fontSize: 12, color: COLORS.primary }}>
            💡 提交后，管理员将在「学习中心」审核。审核通过后自动沉淀为 FAQ，后续类似问题可直接命中。
          </Text>
        </div>
      </Modal>

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
