/**
 * AISummaryPanel.jsx - AI 总结面板
 *
 * 流式展示 AI 对搜索结果的总结，支持深度分析模式。
 * 通过 streamClaudeSummary API 获取实时流式文本。
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Tag, Button, Spin, Typography, Alert } from 'antd';
import { RobotOutlined, LoadingOutlined, ReloadOutlined, DownOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { streamClaudeSummary } from '../api';

const { Text } = Typography;

/** 光标闪烁动画 (定义一次，避免每次渲染重新注入 <style>) */
const BLINK_KEYFRAMES = <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>;

/** 判断是否为限流错误 */
function isRateLimitError(err) {
  if (!err) return false;
  return err.message?.includes('频率过高') || err.message?.includes('rate_limit');
}

/** AI 总结面板 */
function AISummaryPanel({ streamUrl, onSummaryText }) {
  const [summary, setSummary] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [errorHint, setErrorHint] = useState(null);
  const [deepMode, setDeepMode] = useState(false);
  const abortRef = useRef(null);
  const lastStreamUrlRef = useRef(null);
  const fullTextRef = useRef(''); // 累积完整文本，避免闭包问题 // 累积完整文本，避免闭包问题 // 防止 Tab 切换回来自动重触发

  const startStream = useCallback((url) => {
    fullTextRef.current = '';
    const abort = streamClaudeSummary(url, {
      onToken: (text) => {
        fullTextRef.current += text;
        setSummary(prev => prev + text);
      },
      onComplete: () => {
        setStreaming(false);
        setDone(true);
        if (onSummaryText) onSummaryText(fullTextRef.current);
      },
      onError: (err, parsed) => {
        setStreaming(false);
        setError(err.message);
        if (parsed?.hint) setErrorHint(parsed.hint);
      },
    });
    abortRef.current = abort;
    return abort;
  }, []);

  // 自动触发摘要（仅首次挂载或 streamUrl 变化时）
  useEffect(() => {
    if (!streamUrl) return;
    // 如果是同一个 streamUrl（Tab 切换后重新挂载），跳过
    if (lastStreamUrlRef.current === streamUrl) return;
    lastStreamUrlRef.current = streamUrl;

    setSummary('');
    setDone(false);
    setError(null);
    setStreaming(true);
    setDeepMode(false);

    const abort = startStream(streamUrl);

    return () => {
      abortRef.current?.(); // 卸载时中止当前流（包括深度分析）
    };
  }, [streamUrl, startStream]);

  // 深度分析
  const handleDeepAnalysis = () => {
    setDeepMode(true);
    setSummary('');
    setDone(false);
    setError(null);
    setStreaming(true);

    const deepUrl = streamUrl.includes('?')
      ? streamUrl + '&deep=1'
      : streamUrl + '?deep=1';

    startStream(deepUrl);
  };

  if (!streamUrl) return null;

  return (
    <Card
      style={{
        borderRadius: 12, marginBottom: 20,
        border: '1px solid #e2e8f0',
        background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
      }}
      styles={{ body: { padding: '16px 20px' } }}
    >
      {/* 标题栏 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #0D9488 0%, #2DD4BF 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          <Text strong style={{ fontSize: 15 }}>
            {deepMode ? 'AI 深度分析' : 'AI 智能总结'}
          </Text>
          {streaming && <LoadingOutlined style={{ color: '#0D9488' }} />}
          {done && <Tag color="success" style={{ fontSize: 11, borderRadius: 4, lineHeight: '18px' }}>完成</Tag>}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {done && !deepMode && (
            <Button
              size="small"
              type="text"
              icon={<DownOutlined />}
              onClick={handleDeepAnalysis}
              style={{ fontSize: 12, color: '#0D9488' }}
            >
              展开深度分析
            </Button>
          )}
          {error && (
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={handleDeepAnalysis}
              style={{ fontSize: 12, color: '#EF4444' }}
            >
              重试
            </Button>
          )}
        </div>
      </div>

      {/* 内容区 */}
      {error ? (
        <div style={{ padding: '8px 0' }}>
          {isRateLimitError({ message: error }) ? (
            <Alert
              type="warning"
              showIcon
              icon={<InfoCircleOutlined />}
              message="AI 服务暂时不可用"
              description={errorHint || '当前 API 调用配额已用尽，请稍后重试。您仍可查看下方的搜索结果和 FAQ 文档。'}
              style={{ borderRadius: 8 }}
            />
          ) : (
            <div style={{ padding: '8px 0', color: '#EF4444', fontSize: 13 }}>
              ⚠️ 总结生成失败：{error}
            </div>
          )}
        </div>
      ) : summary ? (
        <div style={{
          fontSize: 14, lineHeight: 1.9, color: '#334155',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {summary}
          {streaming && <span style={{
            display: 'inline-block', width: 2, height: 16,
            background: '#0D9488', verticalAlign: 'text-bottom',
            marginLeft: 2, animation: 'blink 1s step-end infinite',
          }} />}
        </div>
      ) : streaming ? (
        <div style={{ padding: '12px 0' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 20 }} spin />} />
          <Text type="secondary" style={{ marginLeft: 10, fontSize: 13 }}>正在生成总结...</Text>
        </div>
      ) : null}

      {BLINK_KEYFRAMES}
    </Card>
  );
}

export default AISummaryPanel;