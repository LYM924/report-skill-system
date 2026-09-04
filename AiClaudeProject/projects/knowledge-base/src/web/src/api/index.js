/**
 * API 接口层 - 对接 Python 搜索服务后端
 *
 * 一体化部署: 前端构建到 static/，Python 同时 serve 静态文件 + API
 * 分离部署: 设置环境变量 VITE_API_BASE=http://backend:8000/api
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

const TOKEN_KEY = 'kb_token';

/** 获取当前登录 token */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

/** 保存 token */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除 token（登出/401 时） */
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** 是否已登录 */
export function isAuthed() {
  return !!getToken();
}

/** 构建带鉴权的请求头 */
function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/** 401 全局通知（App/TopNav 监听后弹出登录框） */
function notifyAuthRequired() {
  clearToken();
  window.dispatchEvent(new Event('kb-auth-required'));
}

/** 登录状态变化通知（App 监听后刷新 userRole 等全局状态） */
export function notifyAuthChanged() {
  window.dispatchEvent(new Event('kb-auth-changed'));
}

/**
 * 带鉴权的通用 fetch（供组件裸调用与封装层共用）
 * - 自动附加 Authorization 头
 * - 401 时清除 token 并广播 kb-auth-required 事件
 * - 403 时广播 kb-auth-forbidden 事件（权限不足）
 */
export async function authFetch(url, options = {}) {
  const resp = await fetch(url, { ...options, headers: authHeaders(options.headers || {}) });
  if (resp.status === 401) notifyAuthRequired();
  if (resp.status === 403) {
    try { window.dispatchEvent(new CustomEvent('kb-auth-forbidden', { detail: await resp.json().catch(() => ({})) })); } catch {}
    // 重新构造一个同态 response，使调用方 resp.ok === false / resp.status === 403
    return new Response(JSON.stringify({ error: '权限不足，仅管理员可执行此操作' }), {
      status: 403, headers: { 'Content-Type': 'application/json' },
    });
  }
  return resp;
}

/**
 * 登录：POST /auth/login（JSON body）
 * @returns {Promise<{ok: boolean, error?: string}>}
 */
export async function login(username, password) {
  try {
    const resp = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) return { ok: false, error: data.error || data.detail || '登录失败' };
    setToken(data.token);
    return { ok: true, role: data.role };
  } catch (e) {
    return { ok: false, error: '网络错误，请稍后重试' };
  }
}

/**
 * Confluence SSO 登录：POST /auth/sso/confluence
 * @param {{ username, display_name, email }} userInfo - Confluence 返回的用户信息
 * @returns {Promise<{ok: boolean, error?: string, sso?: boolean}>}
 */
export async function ssoConfluenceLogin(userInfo) {
  try {
    const resp = await fetch(`${API_BASE}/auth/sso/confluence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userInfo),
    });
    const data = await resp.json();
    if (!resp.ok) return { ok: false, error: data.error || data.detail || 'SSO 登录失败' };
    setToken(data.token);
    return { ok: true, role: data.role, sso: data.sso };
  } catch (e) {
    return { ok: false, error: '网络错误，请稍后重试' };
  }
}

/**
 * 获取 SSO 配置状态
 * @returns {Promise<{enabled: boolean, confluence_url: string}>}
 */
export async function getSSOStatus() {
  try {
    const resp = await fetch(`${API_BASE}/auth/sso/status`);
    return await resp.json();
  } catch (e) {
    return { enabled: false, confluence_url: '' };
  }
}

/**
 * 通过后端代理检测 Confluence 登录状态（无 CORS 问题）
 * 后端转发浏览器 Cookie 到 Confluence /rest/api/user/current
 * @returns {Promise<{ok: boolean, username?, display_name?, email?}|{ok: false, error: string}>}
 */
export async function checkConfluenceSession() {
  try {
    const resp = await fetch(`${API_BASE}/auth/sso/confluence-proxy`, {
      credentials: 'include',
    });
    if (!resp.ok) return { ok: false, error: `代理返回 ${resp.status}` };
    const data = await resp.json();
    if (data.type === 'known' && data.username) {
      return {
        ok: true,
        username: data.username,
        display_name: data.display_name || data.username,
        email: data.email || `${data.username}@cai-inc.com`,
      };
    }
    if (data.type === 'error') return { ok: false, error: data.error || 'Confluence 不可达' };
    // type=anonymous → Confluence 未登录
    return { ok: false, error: 'Confluence 未登录' };
  } catch (e) {
    return { ok: false, error: e.message || '网络错误' };
  }
}

/**
 * 通用请求函数
 */
async function apiFetch(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  const url = `${API_BASE}${path}${query ? '?' + query : ''}`;
  try {
    const resp = await authFetch(url);
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
  const data = await apiFetch('/search', { q: query, scope, top: 10, page, page_size: 10 });
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

  authFetch(url, { signal: controller.signal })
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
                if (onError) onError(new Error(parsed.message || parsed.error), parsed);
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

/**
 * 搜索反馈：记录用户对搜索结果的评价
 * @param {string} query - 搜索关键词
 * @param {string} resultId - 结果ID
 * @param {string} resultPath - 结果路径
 * @param {string} type - 'useful' | 'not_useful'
 */
export async function sendFeedback(query, resultId, resultPath, type) {
  return await apiFetch('/feedback', {
    q: query,
    result_id: resultId || '',
    result_path: resultPath || '',
    type,
  });
}

/**
 * RAG 智能问答：搜索 + AI 回答
 * @param {string} message - 用户问题
 * @param {object} callbacks - { onToken, onComplete, onError }
 * @returns {function} abort
 */

/**
 * 更新文档元数据（部门、模块、关键词、文件名）
 */
export async function updateDocument(path, { dept, deptIds, product, module, moduleId, keywords, newFilename } = {}) {
  const params = new URLSearchParams({ path, dept: dept || '', product: product || '', keywords: keywords || '' });
  if (module) params.set('module', module);
  if (moduleId) params.set('module_id', String(moduleId));
  if (deptIds && deptIds.length > 0) params.set('dept_ids', deptIds.join(','));
  if (newFilename) params.set('new_filename', newFilename);
  const resp = await authFetch(`${API_BASE}/document/update?${params.toString()}`);
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error || '更新失败');
  return data;
}

/**
 * 获取文档关联的部门 ID 列表
 */
export async function getDocumentDeptIds(path) {
  const resp = await authFetch(`${API_BASE}/document/dept-ids?path=${encodeURIComponent(path)}`);
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error || '获取部门ID失败');
  return data.dept_ids || [];
}

/**
 * 删除文档
 */
export async function deleteDocument(path, id = 0) {
  const params = new URLSearchParams({ path, ...(id && { id: String(id) }) });
  const resp = await authFetch(`${API_BASE}/document/delete?${params.toString()}`);
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error || '删除失败');
  return data;
}

/**
 * 上传文档
 */
export async function uploadDocument({ filename, content, dept, module }) {
  const resp = await authFetch(`${API_BASE}/document/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content, dept, module }),
  });
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error || '上传失败');
  return data;
}

/**
 * 获取菜单
 */
export async function getMenu() {
  return await apiFetch('/menu');
}

/**
 * 获取关键词列表
 */
export async function getKeywords(q = '', page = 1) {
  return await apiFetch('/keywords', { q, page, page_size: 100 });
}

/**
 * 添加关键词映射
 * @param {{keyword, module_id, dept_id, dept, module}} params
 */
export async function addKeyword({ keyword, module_id, dept_id, dept, module }) {
  const resp = await authFetch(`${API_BASE}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, module_id, dept_id, dept, module }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || data.detail || '添加失败');
  }
  return await resp.json();
}

/**
 * 更新关键词映射（通过 mapping_id 定位）
 * @param {{mapping_id, keyword?, module_id?, dept_id?, dept?}} params
 */
export async function updateKeyword({ mapping_id, keyword, module_id, dept_id, dept }) {
  const resp = await authFetch(`${API_BASE}/keywords`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mapping_id, keyword, module_id, dept_id, dept }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || data.detail || '更新失败');
  }
  return await resp.json();
}

/**
 * 删除关键词映射
 * @param {{mapping_id?, keyword_id?}} params
 */
export async function deleteKeyword({ mapping_id, keyword_id } = {}) {
  const resp = await authFetch(`${API_BASE}/keywords`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mapping_id, keyword_id }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || data.detail || '删除失败');
  }
  return await resp.json();
}

/**
 * 获取日志
 */
export async function getLogs() {
  return await apiFetch('/logs');
}

/**
 * 获取部门选项
 */
export async function getDepartmentOptions() {
  return await apiFetch('/departments/options');
}
export function ragQuery(message, callbacks = {}) {
  const { onToken, onComplete, onError } = callbacks;
  const controller = new AbortController();

  authFetch('/api/rag', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
              if (onComplete) onComplete({});
              return;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) { if (onError) onError(new Error(parsed.error)); return; }
              if (parsed.text && onToken) onToken(parsed.text);
              if (parsed.type === 'complete' && onComplete) onComplete(parsed);
            } catch (e) { /* skip */ }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError' && onError) onError(err);
    });

  return () => controller.abort();
}

// ============================================================================
// 学习中心 API
// ============================================================================

/**
 * 获取学习候选列表
 * @param {number|null} status - 0待审核/1已通过/2已拒绝/3已过期，不传=全部
 * @param {number} page
 * @param {number} pageSize
 */
export async function getLearningCandidates(status = null, page = 1, pageSize = 20) {
  const params = { page, page_size: pageSize };
  if (status !== null && status !== undefined) params.status = String(status);
  return await apiFetch('/learning/candidates', params);
}

/**
 * 获取学习中心统计
 */
export async function getLearningStats() {
  return await apiFetch('/learning/stats');
}

/**
 * AI 提取知识（SSE 流式返回）
 * @param {string} query - 用户问题
 * @param {string} answer - AI 回答
 * @param {object} callbacks - { onToken, onComplete, onError }
 * @returns {function} abort
 */
export function extractKnowledge(query, answer, callbacks = {}) {
  const { onToken, onComplete, onError } = callbacks;
  const controller = new AbortController();

  authFetch(`${API_BASE}/learning/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, answer, session_id: '' }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
              if (onComplete) onComplete({});
              return;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) { if (onError) onError(new Error(parsed.message || parsed.error)); return; }
              if (parsed.text && onToken) onToken(parsed.text);
              if (parsed.type === 'complete' && onComplete) onComplete(parsed);
            } catch (e) { /* skip */ }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError' && onError) onError(err);
    });

  return () => controller.abort();
}

/**
 * 提交学习候选（JSON body）
 * @param {{ query, answer, summary, dept, module, keywords, source, session_id }} data
 */
export async function submitLearningCandidate(data) {
  const resp = await authFetch(`${API_BASE}/learning/submit-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return await resp.json();
}

/**
 * 用户反馈自动学习（👍触发）
 * @param {{ query, answer, feedback_id, session_id }} data
 */
export async function autoLearnFromFeedback(data) {
  const resp = await authFetch(`${API_BASE}/learning/auto`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return await resp.json();
}

/**
 * 审核通过学习候选 → 创建FAQ
 * @param {number} candidateId
 * @param {{ title?, summary?, dept?, module?, keywords? }} edits
 */
export async function approveLearningCandidate(candidateId, edits = {}) {
  const resp = await authFetch(`${API_BASE}/learning/approve/${candidateId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edits),
  });
  return await resp.json();
}

/**
 * 审核拒绝学习候选
 * @param {number} candidateId
 * @param {string} note - 拒绝原因
 */
export async function rejectLearningCandidate(candidateId, note = '') {
  const resp = await authFetch(`${API_BASE}/learning/reject/${candidateId}?note=${encodeURIComponent(note)}`, {
    method: 'POST',
  });
  return await resp.json();
}

/**
 * 清理过期学习候选
 * @param {number} days - 超过多少天未审核
 */
export async function expireLearningCandidates(days = 30) {
  const resp = await authFetch(`${API_BASE}/learning/expire?days=${days}`, {
    method: 'POST',
  });
  return await resp.json();
}