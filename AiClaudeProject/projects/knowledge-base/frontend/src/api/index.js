/**
 * API 接口层 - 对接 Python 搜索服务后端
 *
 * 一体化部署: 前端构建到 static/，Python 同时 serve 静态文件 + API
 * 分离部署: 设置环境变量 VITE_API_BASE=http://backend:8765/api
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

/**
 * 通用请求函数
 */
async function apiFetch(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  const url = `${API_BASE}${path}${query ? '?' + query : ''}`;
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    console.error(`API Error [${path}]:`, e);
    return null;
  }
}

/**
 * 智能搜索
 * @param {string} query - 搜索关键词
 * @param {string} scope - 搜索范围: all | doc | faq | ticket | dept
 * @returns {Promise<{results, answer, faqs, tickets, claude_stream_url}>}
 */
export async function searchKnowledge(query, scope = 'all', page = 1) {
  const data = await apiFetch('/search', { q: query, top: 10, page, page_size: 10 });
  if (!data) return { results: [], answer: null, faqs: [], tickets: [] };

  return {
    results: data.results || [],
    answer: data.answer || null,
    tokens: data.tokens || [],
    expanded_terms: data.expanded_terms || [],
    total: data.total || 0,
    process: data.process || null,
    claude_stream_url: data.claude_stream_url || null,
    has_more: data.has_more || false,
  };
}

/**
 * 获取知识总览仪表盘数据
 */
export async function getDashboardStats() {
  const data = await apiFetch('/dashboard');
  if (data) return data;
  // fallback mock
  return {
    totalDocs: 3256, faqCount: 842, weekQuestions: 618,
    weekNew: 966, weekNewGrowth: 12.5, aiMatchConfidence: 92,
  };
}

/**
 * 获取文档列表
 * @param {string} module - 可选，按产品模块筛选
 */
export async function getDocuments(module = '') {
  const params = {};
  if (module) params.module = module;
  const data = await apiFetch('/documents', params);
  if (data) return data.documents || [];
  return [];
}

/**
 * 获取 FAQ 列表
 */
export async function getFAQs() {
  const data = await apiFetch('/faq');
  if (data) return data.faqs || [];
  return [];
}

/**
 * 获取 FAQ 详情
 * @param {string} faqId
 */
export async function getFAQDetail(faqId) {
  return await apiFetch('/faq', { id: faqId });
}

/**
 * 获取文档详情
 * @param {string} path - 文档路径
 */
export async function getDocumentDetail(path) {
  return await apiFetch('/document', { path });
}

/**
 * 获取系统统计
 */
export async function getStats() {
  return await apiFetch('/stats');
}

/**
 * 重建索引
 */
export async function rebuildIndex() {
  return await apiFetch('/rebuild');
}

/**
 * SSE 流式调用 Claude 总结
 * @param {string} url - SSE endpoint，完整路径如 /api/claude-stream?sid=xxx
 * @param {object} callbacks - { onToken, onComplete, onError }
 * @returns {function} abort - 调用以取消请求
 */
export function streamClaudeSummary(url, callbacks = {}) {
  const { onToken, onComplete, onError } = callbacks;
  const controller = new AbortController();

  fetch(url, { signal: controller.signal })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) throw new Error('Response body is not readable');
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
              if (onComplete) onComplete();
              return;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) {
                if (onError) onError(new Error(parsed.error));
                return;
              }
              if (parsed.text && onToken) {
                onToken(parsed.text);
              }
              if (parsed.type === 'complete' && onComplete) {
                onComplete(parsed);
                return;
              }
            } catch (e) {
              // 跳过解析失败的行
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError' && onError) {
        onError(err);
      }
    });

  return () => controller.abort();
}

/**
 * 保存 FAQ
 */
export async function saveFAQ(data) {
  return await apiFetch('/faq/save', data);
}

/**
 * 删除 FAQ
 */
export async function deleteFAQ(path) {
  return await apiFetch('/faq/delete', { path });
}

/**
 * 获取搜索趋势
 */
export async function getTrends() {
  return await apiFetch('/trends');
}

/**
 * 获取搜索热词
 */
export async function getHotwords() {
  return await apiFetch('/hotwords');
}

/**
 * 获取最近更新
 */
export async function getRecent() {
  return await apiFetch('/recent');
}

/**
 * 获取报表列表
 */
export async function getReports(page = 1) {
  return await apiFetch('/reports', { page, page_size: 20 });
}