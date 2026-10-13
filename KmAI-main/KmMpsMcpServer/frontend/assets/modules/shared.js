// shared.js —— 整个前端的依赖根。
// 这里集中放:
//   1. 共享 state 对象 —— 把以前 IIFE 顶层散落的 `let` 变量全部收进一个对象里,
//      模块之间通过 `state.xxx` 访问,避免「谁偷偷改了谁」找不到。
//   2. 共享 dom 引用 —— 所有 getElementById 的结果只查一次,放在 `dom` 对象里
//      供各模块按名取用。
//   3. 跨模块的工具函数:escapeHtml、requestJson、callTool、addMsg 等。

// ============================================================
// 常量
// ============================================================

// 工艺路线自动生成智能体的固定 ID,后端识别后才会把工作流 dock 显示出来。
export const PROCESS_AUTO_AGENT_ID = 'process-auto-generate-agent';
export const KMRAG_AGENT_ID = 'kmrag-knowledge-agent';

// localStorage 里存的智能体选择,浏览器关掉再开还能记得上次的智能体。
const AGENT_STORAGE_KEY = 'km-mps-agent-id';

// ============================================================
// 共享 state
// ============================================================
//
// 把以前 IIFE 里散落的 `let` 变量统一收进这里。模块间共享读写都走 `state.xxx`,
// 谁读谁写、什么时候改,看 import 关系一目了然。
//
// ⚠️ 不要在这个对象里放 DOM 引用 —— DOM 引用走 `dom` 对象,因为它们在 DOMContentLoaded
// 之前是 null,放在 state 里会让状态语义变模糊。
export const state = {
  // 会话标识,每次切换智能体会 reset。
  sessionId: createSessionId(),

  // 当前选中的智能体 ID,'default' 表示默认助手。
  currentAgentId: 'default',

  // 每个智能体自己的聊天窗口快照,只在当前页面生命周期内保留。
  agentLogSnapshots: {},

  // /api/agents 加载出的名称映射,切换提示不要依赖 select 的当前文本推断。
  agentNamesById: {},

  // 工艺输入 inbox 的去重 key,见 process_route.js 里 `pollLatestProcessRouteInput`。
  latestProcessRouteInboxKey: '',

  // 当前激活的工艺输入 key(用于判断是否「同一份」输入,触发时记录、收到时清空)。
  currentProcessRouteInputKey: '',

  // 最新的工艺输入 payload(3DMPS 推过来的 JSON 包),面板里所有「CAD 分组数」都从这里读。
  latestProcessRouteInputPayload: null,

  // 最新的工艺路线生成结果,面板右侧时间线渲染这个。
  latestProcessRouteResult: null,

  // 技术要求是否已经生成(影响「提交工艺路线」按钮是否可点)。
  latestProcessRouteTechnicalReady: false,

  // 工艺数据提交按钮状态: idle / submitting / submitted / error。
  processRouteSubmitState: 'idle',
  processRouteSubmitMessage: '',

  // inbox 轮询的 setInterval 句柄,只在第一次启动时设置,后续刷新不会重复启。
  processRouteInboxPollTimer: null,

  // 工艺路线面板是否被工作流第 4 步「解锁」过;解锁后才允许被打开。
  processRoutePanelUnlocked: false,

  // 用户手动关过面板的标记,避免后台 inbox 推送又把它弹出来。
  processRoutePanelManuallyClosed: false,

  // 标记是否在等待 3DMPS 推新的工艺输入 JSON(轮询用)。
  processRouteAwaitingInput: false,

  // 触发工艺推理时的 inbox key 基线,新推送必须 != 这个才算「新的」。
  processRouteAwaitingBaseKey: '',

  // 工作流 5 步状态机的当前状态,见 workflow.js 里 resetProcessWorkflowState()。
  processWorkflowState: createInitialProcessWorkflowState(),

  // 是否显示调试信息(true=显示工具调用 + JSON 预览;false=隐藏)。默认关闭,降低普通用户的视觉噪音。
  debugMode: false,

  // Km3dmps.exe exit monitor state.
  km3dmpsExitMonitorTimer: null,
  km3dmpsExitMonitorSeenRunning: false,
  km3dmpsExitMonitorMisses: 0,
  km3dmpsExitMonitorClosing: false,
};

function createInitialProcessWorkflowState() {
  return {
    activeStepId: 'select_group_template',
    runningStepId: '',
    awaitingStepId: '',
    runningAll: false,
    waitingUserStepId: '',
    autoSubmittedRoute: false,
    autoSubmittingRouteKey: '',
    autoRouteError: '',
    autoGeneratingTechnical: false,
    doneStepIds: {},
    continueFromStepId: '',
  };
}

function createSessionId() {
  return 'web-' + Date.now() + '-' + Math.random().toString(36).slice(2);
}

// ============================================================
// DOM 引用
// ============================================================
//
// 全部 getElementById 集中在这里,每个模块要拿元素都通过 `dom.xxx` 取。
// `initDomRefs()` 必须在 DOMContentLoaded 之后(entry.js 在模块底部调用)执行一次,
// 后续 `dom.xxx` 才有值。
export const dom = {
  log: null,
  input: null,
  sendBtn: null,
  testBtn: null,
  configBtn: null,
  agentSelect: null,
  status: null,
  processRouteStatus: null,
  processRouteResults: null,
  processRouteTechnicalView: null,
  processRouteResultSwitch: null,
  processRouteRouteTab: null,
  processRouteTechnicalTab: null,
  prSummary: null,
  prHeadStatusText: null,
  prMetaInfo: null,
  processRoutePanelBackdrop: null,
  similarPartsPanel: null,
  similarPartsPanelBackdrop: null,
  prMoreBtn: null,
  prCloseBtn: null,
  prParamsBlock: null,
  prParamsDetail: null,
  prChipMaterial: null,
  prChipPartType: null,
  prChipHeat: null,
  prChipSurface: null,
  prStatGroup: null,
  prStatFeature: null,
  prStatProcess: null,
  prStatStep: null,
  prSummaryOk: null,
  workflowDock: null,
  processRoutePanel: null,
  processRouteGenerateBtn: null,
  processRouteTechnicalBtn: null,
  processRouteSubmitBtn: null,
  processRouteTechnicalRow: null,
  processRouteSubmitRow: null,
  processRouteMaterialGrade: null,
  processRoutePartType: null,
  processRouteHeatTreatment: null,
  processRouteInspectionItems: null,
  processRouteMarkingMethods: null,
  processRouteFlagShapedHole: null,
  processRouteFlagPostStageHole: null,
  processRouteAdvancedToggle: null,
  processRouteAdvancedPanel: null,
};

function $(id) {
  return document.getElementById(id);
}

export function initDomRefs() {
  dom.log = $('log');
  dom.input = $('input');
  dom.sendBtn = $('sendBtn');
  dom.testBtn = $('testBtn');
  dom.configBtn = $('configBtn');
  dom.agentSelect = $('agentSelect');
  dom.status = $('status');
  dom.processRouteStatus = $('processRouteStatus');
  dom.processRouteResults = $('processRouteResults');
  dom.processRouteTechnicalView = $('processRouteTechnicalView');
  dom.processRouteResultSwitch = $('processRouteResultSwitch');
  dom.processRouteRouteTab = $('processRouteRouteTab');
  dom.processRouteTechnicalTab = $('processRouteTechnicalTab');
  dom.prSummary = $('prSummary');
  dom.prHeadStatusText = $('prHeadStatusText');
  dom.prMetaInfo = $('prMetaInfo');
  dom.processRoutePanelBackdrop = $('processRoutePanelBackdrop');
  dom.similarPartsPanel = $('similarPartsPanel');
  dom.similarPartsPanelBackdrop = $('similarPartsPanelBackdrop');
  dom.prMoreBtn = $('prMoreBtn');
  dom.prCloseBtn = $('prCloseBtn');
  dom.prParamsBlock = $('prParamsBlock');
  dom.prParamsDetail = $('prParamsDetail');
  dom.prChipMaterial = $('prChipMaterial');
  dom.prChipPartType = $('prChipPartType');
  dom.prChipHeat = $('prChipHeat');
  dom.prChipSurface = $('prChipSurface');
  dom.prStatGroup = $('prStatGroup');
  dom.prStatFeature = $('prStatFeature');
  dom.prStatProcess = $('prStatProcess');
  dom.prStatStep = $('prStatStep');
  dom.prSummaryOk = $('prSummaryOk');
  dom.workflowDock = $('workflowDock');
  dom.processRoutePanel = $('processRoutePanel');
  dom.processRouteGenerateBtn = $('processRouteGenerateBtn');
  dom.processRouteTechnicalBtn = $('processRouteTechnicalBtn');
  dom.processRouteSubmitBtn = $('processRouteSubmitBtn');
  dom.processRouteTechnicalRow = $('processRouteTechnicalRow');
  dom.processRouteSubmitRow = $('processRouteSubmitRow');
  dom.processRouteMaterialGrade = $('processRouteMaterialGrade');
  dom.processRoutePartType = $('processRoutePartType');
  dom.processRouteHeatTreatment = $('processRouteHeatTreatment');
  dom.processRouteInspectionItems = $('processRouteInspectionItems');
  dom.processRouteMarkingMethods = $('processRouteMarkingMethods');
  dom.processRouteFlagShapedHole = $('processRouteFlagShapedHole');
  dom.processRouteFlagPostStageHole = $('processRouteFlagPostStageHole');
  dom.processRouteAdvancedToggle = $('processRouteAdvancedToggle');
  dom.processRouteAdvancedPanel = $('processRouteAdvancedPanel');
}

// ============================================================
// 通用工具
// ============================================================

/** HTML 转义,所有用户/服务端返回的字符串拼到 innerHTML 之前必须先过这层。 */
export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 顶栏状态指示,kind 是 'ok' / 'warn' / 'err' 之一。 */
export function setStatus(kind, text) {
  if (!dom.status) return;
  dom.status.innerHTML = '<span class="dot ' + kind + '"></span>' + escapeHtml(text);
}

/** 获取当前时间字符串，格式 HH:MM */
export function getTimeStr() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  return h + ':' + m;
}

/**
 * 在 #log 里追加一条消息，cls 决定气泡样式(user / bot / bot error)。
 * 使用方案 B 商务卡片风格：带头像、时间戳、尖角气泡
 */
export function addMsg(cls, html) {
  if (!dom.log) return null;
  const div = document.createElement('div');
  div.className = 'msg ' + cls;

  if (cls === 'user') {
    div.innerHTML =
      '<div class="avatar user">我</div>' +
      '<div class="bubble-wrap">' +
        '<div class="msg-meta">我 · ' + getTimeStr() + '</div>' +
        '<div class="bubble">' + html + '</div>' +
      '</div>';
  } else if (cls === 'bot') {
    div.innerHTML =
      '<div class="avatar bot">沐</div>' +
      '<div class="bubble-wrap">' +
        '<div class="msg-meta">AI 助手 · ' + getTimeStr() + '</div>' +
        '<div class="bubble">' + html + '</div>' +
      '</div>';
  } else {
    // error 等其他情况，保持兼容
    div.innerHTML = '<div class="bubble error">' + html + '</div>';
  }

  dom.log.appendChild(div);
  dom.log.scrollTop = dom.log.scrollHeight;
  return div;
}

export function addUserMsg(text) {
  addMsg('user', escapeHtml(text));
}

export function addBotMsg(text) {
  return addMsg('bot', escapeHtml(text));
}

export function addErrorMsg(text) {
  addMsg('bot error', escapeHtml(text));
}

/** 清空聊天区。workflow 切智能体时会调。 */
export function clearLog() {
  if (dom.log) dom.log.innerHTML = '';
}

// ============================================================
// HTTP 请求
// ============================================================

export function getApiToken() {
  return window.__KMAI_API_TOKEN__ || '';
}

/** XHR 包装,带超时,统一 JSON 解析。 */
export function requestJson(method, url, body, onSuccess, onError, timeoutMs) {
  const xhr = new XMLHttpRequest();
  xhr.open(method, url, true);
  xhr.timeout = timeoutMs || 30000;
  xhr.setRequestHeader('Accept', 'application/json');
  const token = getApiToken();
  if (token) xhr.setRequestHeader('X-KmAI-Token', token);
  if (body !== null && body !== undefined) {
    xhr.setRequestHeader('Content-Type', 'application/json');
  }
  xhr.onload = function() {
    let data = null;
    try {
      data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
    } catch (parseErr) {
      onError(new Error('JSON解析失败: ' + parseErr.message));
      return;
    }
    if (xhr.status >= 200 && xhr.status < 300) {
      onSuccess(data);
    } else {
      const msg = data && data.message ? data.message : ('HTTP ' + xhr.status);
      const error = new Error(msg);
      error.httpStatus = xhr.status;
      error.errorCode = data && data.error_code ? data.error_code : '';
      error.payload = data;
      onError(error);
    }
  };
  xhr.onerror = function() { onError(new Error('网络请求失败')); };
  xhr.ontimeout = function() { onError(new Error('请求超时')); };
  xhr.send(body !== null && body !== undefined ? body : null);
}

export function requestJsonPromise(method, url, body, timeoutMs) {
  return new Promise(function(resolve, reject) {
    requestJson(method, url, body, resolve, reject, timeoutMs);
  });
}

/** 调 3DMPS 工具的统一入口,所有 skill 调用都走这个。 */
export async function callTool(functionName, params, timeoutSeconds, requestTimeoutMs) {
  const payload = { function: functionName, params: params || {} };
  if (timeoutSeconds) payload.timeout = timeoutSeconds;
  try {
    const data = await requestJsonPromise('POST', '/api/tool', JSON.stringify(payload), requestTimeoutMs || 30000);
    return data && data.result ? data.result : data;
  } catch (error) {
    // 仅还原确实携带原始 result 的工具执行错误；API/网络/解析错误继续抛出。
    const data = error && error.payload;
    if (
      data &&
      data.status === 'error' &&
      Object.prototype.hasOwnProperty.call(data, 'result')
    ) {
      return data.result;
    }
    throw error;
  }
}

/** 明确失败标志优先于历史 success/ok 标志，并兼容嵌套 result。 */
function hasToolFailure(result) {
  if (!result || typeof result !== 'object') return false;
  const status = String(result.status || '').trim().toLowerCase();
  if (result.ok === false || status === 'error' || status === 'failed' || status === 'failure' || result.error_code) {
    return true;
  }
  const nested = result.result;
  return !!(nested && nested !== result && typeof nested === 'object' && hasToolFailure(nested));
}

/** 工具返回结果里,后端在不同地方塞过 'success' / 'ok' / 'accepted',统一判定。 */
export function isToolSuccess(result) {
  if (!result || typeof result !== 'object' || hasToolFailure(result)) return false;
  const status = String(result.status || '').trim().toLowerCase();
  return status === 'success' || status === 'ok' || status === 'accepted' || result.ok === true;
}

export function getToolErrorMessage(result, fallbackText) {
  if (!result || typeof result !== 'object') return fallbackText || '工具执行失败';
  const nested = result.result;
  if (nested && nested !== result && typeof nested === 'object' && hasToolFailure(nested)) {
    return getToolErrorMessage(nested, fallbackText);
  }
  const message = result.message || result.reply || result.error || '';
  if (message) return String(message);
  return fallbackText || '工具执行失败';
}

// ============================================================
// 工艺输入 inbox 工具(被 process_route 和 tool_call 共用)
// ============================================================

/**
 * 从工艺输入 payload 算一个稳定的去重 key,顺序拼接 input_file / trace_id /
 * created_at / input_json(JSON 序列化),任一字段变了就视为「新的」。
 */
export function getProcessRouteInboxKey(payload) {
  if (!payload || typeof payload !== 'object') return '';
  const inputFile = payload.input_file || '';
  const traceId = payload.trace_id || '';
  const createdAt = payload.created_at || '';
  const inputJson = payload.input_json !== undefined ? JSON.stringify(payload.input_json) : (payload.input_text || '');
  return [inputFile, traceId, createdAt, inputJson].join('|');
}

export function buildProcessRouteInboxText(payload) {
  if (!payload || typeof payload !== 'object') return '';
  if (payload.input_json !== undefined) {
    try {
      return JSON.stringify(payload.input_json, null, 2);
    } catch (err) {
      /* ignore */
    }
  }
  if (payload.input_text) return String(payload.input_text);
  return JSON.stringify(payload, null, 2);
}

// ============================================================
// 字符串/列表小工具
// ============================================================

/** 把全角逗号 / 换行 / 顿号 都规范成半角逗号再 split,用于人工补充参数里的检测项/标识方式。 */
export function splitCommaList(text) {
  if (!text) return [];
  let normalized = String(text);
  const cr = String.fromCharCode(13);
  const lf = String.fromCharCode(10);
  normalized = normalized.split(cr + lf).join(',');
  normalized = normalized.split(lf).join(',');
  normalized = normalized.split(String.fromCharCode(65292)).join(',');  // 全角逗号
  normalized = normalized.split(String.fromCharCode(12289)).join(',');  // 顿号
  return normalized.split(',').map(function(item) {
    return String(item || '').trim();
  }).filter(function(item) {
    return !!item;
  });
}

// ============================================================
// 智能体存储
// ============================================================

export function getStoredAgentId() {
  try {
    return localStorage.getItem(AGENT_STORAGE_KEY) || 'default';
  } catch (err) {
    return 'default';
  }
}

export function setStoredAgentId(agentId) {
  try {
    localStorage.setItem(AGENT_STORAGE_KEY, agentId || 'default');
  } catch (err) {
    /* ignore */
  }
}

export function resetSession() {
  state.sessionId = createSessionId();
}

// ============================================================
// 服务健康检查
// ============================================================

// 3DMPS exit monitor: close KMAI only after Km3dmps.exe was seen running and then disappears.
function showKm3dmpsClosedFallback() {
  if (typeof document === 'undefined' || !document.body) return;
  if (document.getElementById('km3dmpsClosedFallback')) return;
  document.body.innerHTML = [
    '<main id="km3dmpsClosedFallback" style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f6f8fb;color:#1f2937;font-family:Microsoft YaHei,Segoe UI,sans-serif;">',
    '<section style="max-width:520px;padding:32px 36px;border-radius:18px;background:#fff;box-shadow:0 18px 50px rgba(15,23,42,.14);text-align:center;">',
    '<h1 style="margin:0 0 12px;font-size:22px;">3DMPS 已关闭</h1>',
    '<p style="margin:0;color:#64748b;line-height:1.8;">KMAI 已检测到 3DMPS 主程序退出，正在尝试自动关闭此页面。如果浏览器拦截了自动关闭，请手动关闭该页面。</p>',
    '</section>',
    '</main>'
  ].join('');
}

function closeKmaiAfterKm3dmpsExit() {
  if (state.km3dmpsExitMonitorClosing) return;
  state.km3dmpsExitMonitorClosing = true;
  if (state.km3dmpsExitMonitorTimer) {
    clearInterval(state.km3dmpsExitMonitorTimer);
    state.km3dmpsExitMonitorTimer = null;
  }
  setStatus('warn', '3DMPS 已关闭，正在关闭 KMAI...');
  try {
    window.close();
  } catch (err) {
    console.warn('[km3dmps-exit-monitor] window.close failed', err);
  }
  setTimeout(showKm3dmpsClosedFallback, 1500);
}

async function checkKm3dmpsStillRunningForExitMonitor() {
  if (state.km3dmpsExitMonitorClosing) return;
  const controller = new AbortController();
  const timeoutId = setTimeout(function() { controller.abort(); }, 3000);
  try {
    const response = await fetch('/api/health', {
      cache: 'no-store',
      signal: controller.signal,
      headers: { 'X-KmAI-Token': getApiToken() }
    });
    clearTimeout(timeoutId);
    const data = await response.json();
    const km3dmps = data && data.km3dmps;
    if (km3dmps && km3dmps.running === true) {
      state.km3dmpsExitMonitorSeenRunning = true;
      state.km3dmpsExitMonitorMisses = 0;
      return;
    }
    if (!state.km3dmpsExitMonitorSeenRunning) return;
    state.km3dmpsExitMonitorMisses += 1;
  } catch (err) {
    clearTimeout(timeoutId);
    if (!state.km3dmpsExitMonitorSeenRunning) return;
    state.km3dmpsExitMonitorMisses += 1;
    console.warn('[km3dmps-exit-monitor] health check failed', err);
  }
  if (state.km3dmpsExitMonitorMisses >= 2) {
    closeKmaiAfterKm3dmpsExit();
  }
}

export function startKm3dmpsExitMonitor() {
  if (state.km3dmpsExitMonitorTimer) return;
  state.km3dmpsExitMonitorTimer = setInterval(checkKm3dmpsStillRunningForExitMonitor, 3000);
  setTimeout(checkKm3dmpsStillRunningForExitMonitor, 1000);
}

/** 顶栏 LLM 状态检查,被 send() 成功回调、testBtn 点击和 init 调用。 */
export async function ping() {
  setStatus('warn', '检查中...');
  const controller = new AbortController();
  const timeoutId = setTimeout(function() { controller.abort(); }, 8000);
  try {
    console.log('[ping] GET /api/health');
    const r = await fetch('/api/health', {
      cache: 'no-store',
      signal: controller.signal,
      headers: { 'X-KmAI-Token': getApiToken() }
    });
    clearTimeout(timeoutId);
    const data = await r.json();
    console.log('[ping] response', data);
    if (data && data.status === 'ok') {
      const modelName = data.llm && data.llm.model ? data.llm.model : '';
      const llm = data.llm_enabled ? ('已启用' + (modelName ? ' · ' + modelName : '')) : '仅关键词';
      setStatus('ok', '服务正常 · LLM ' + llm);
      return true;
    }
    setStatus('err', '服务异常');
    return false;
  } catch (err) {
    clearTimeout(timeoutId);
    console.error('[ping] failed', err);
    const isAbort = err.name === 'AbortError' || err.name === 'TypeError';
    setStatus('err', isAbort ? '连接超时(8s)' : ('连接失败: ' + err.message));
    return false;
  }
}
