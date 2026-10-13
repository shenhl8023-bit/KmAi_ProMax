// workflow.js —— 固定工作流 dock + 5 步状态机。

import {
  state, dom, escapeHtml, setStatus, addUserMsg, addBotMsg, addErrorMsg,
  requestJson, isToolSuccess, getToolErrorMessage, resetSession, clearLog,
} from './shared.js';

const PROCESS_WORKFLOW_SIZE_STORAGE_KEY = 'km-mps-process-workflow-size';
const FEATURE_REASONING_SETTLE_MS = 5000;

const DEFAULT_ASSISTANT_CAPABILITIES = [
  { title: '检查服务状态', desc: '确认 3DMPS、MCP 后端和本地管道是否连通。' },
  { title: '读取模型信息', desc: '获取 BOF / 特征树、特征列表等当前可用数据。' },
  { title: '说明 MCP 工具', desc: '总结哪些工具可用、需要弹窗、暂未实现以及如何调用。' },
  { title: '辅助排查问题', desc: '分析报错原因、定位代码位置，并给出修复建议。' }
];

const PROCESS_GROUP_TEMPLATE_DEFAULT_TEXT = '衬套类回转体零件，A侧B侧，包含端面、外圆、孔';
const PROCESS_TEMPLATE_TYPES = [
  {
    id: 'bushing',
    title: '衬套',
    icon: '套',
    desc: '回转体零件，A侧/B侧，端面、外圆、孔等特征。',
    text: PROCESS_GROUP_TEMPLATE_DEFAULT_TEXT,
    tags: ['回转体', 'A/B侧', '端面', '外圆', '孔']
  },
  {
    id: 'housing',
    title: '壳体',
    icon: '壳',
    desc: '壳体/箱体类多面加工零件，孔系、平面、槽等特征。',
    text: '壳体类多面加工零件，包含孔系、平面和通槽',
    tags: ['多面', '孔系', '平面', '槽']
  },
  {
    id: 'small-part',
    title: '小件',
    icon: '小',
    desc: '小件/简单件通用零件，适合特征较少的快速分组。',
    text: '小件简单零件，通用件，特征较少，需快速分组',
    tags: ['小件', '简单件', '通用']
  },
  {
    id: 'valve',
    title: '活门',
    icon: '阀',
    desc: '活门/阀类零件，适合阀体、放油活门等结构。',
    text: '活门阀类零件，包含阀体、放油活门、孔和密封面',
    tags: ['活门', '阀类', '密封面']
  }
];

const PROCESS_AUTO_WORKFLOW_STEPS = [
  { id: 'select_group_template', title: '匹配分组模板', desc: '从固定目录读取当前零件 XML，查看 Top 3 相似模型并应用当前候选的分组模板。', prompt: '只执行第1步：查询相似零件并应用当前候选的分组模板，不补跑后续步骤。' },
  { id: 'auto_identify_template', title: '自动特征识别', desc: '点击自动识别并确认 3DMPS 自动识别加工特征对话框。', prompt: '只执行第2步：点击自动识别按钮，等待 3DMPS 弹出“自动识别加工特征”对话框后自动点击确定，然后标记工作流卡片完成，不获取组合列表，不弹出选择卡，不等待几何识别完成。' },
  { id: 'feature_reasoning', title: '加工方法推理', desc: '触发 3DMPS 特征推理按钮。', prompt: '只执行第3步：特征推理。直接触发特征推理，不补跑分组模板、自动识别或AI工艺输入。' },
  { id: 'ai_process_input', title: '工艺路线生成', desc: '触发 3DMPS 推送 AI 工艺输入；一键执行时收到 manual_defaults 后等待用户点击生成路线，路线完成后自动生成技术要求，提交由用户确认。', prompt: '进行AI工艺推理。若是一键执行流程，收到 manual_defaults/input_json 后只填充参数并等待用户点击生成工艺路线；路线完成后自动生成技术要求；提交工艺数据由用户确认。' },
  { id: 'generate_all_model', title: '工序模型生成', desc: '在 output JSON 已提交后执行最终生成。', prompt: '执行最终生成：全部生成。仅在 output JSON 已提交后点击生成全部按钮；如果还没有提交 output JSON，请提示用户先提交，不要直接生成。' }
];

export function resetProcessWorkflowState() {
  state.processWorkflowState = {
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
    continueFromStepId: ''
  };
  // 同步清掉聊天日志里残留的「待处理工艺输入」卡片 + 工艺路线面板状态
  Promise.all([
    import('./tool_call.js'),
    import('./process_route.js')
  ]).then(function(mods) {
    if (mods[0] && typeof mods[0].clearProcessRouteInboxCard === 'function') {
      mods[0].clearProcessRouteInboxCard();
    }
    if (mods[1] && typeof mods[1].resetProcessRoutePanelFlowState === 'function') {
      mods[1].resetProcessRoutePanelFlowState();
    }
  }).catch(function() {});
}

export function getProcessWorkflowStep(stepId) {
  for (const step of PROCESS_AUTO_WORKFLOW_STEPS) {
    if (step.id === stepId) return step;
  }
  return null;
}

function getProcessWorkflowAutoStartIndex() {
  const doneStepIds = state.processWorkflowState.doneStepIds || {};
  for (let i = 0; i < PROCESS_AUTO_WORKFLOW_STEPS.length; i += 1) {
    if (!doneStepIds[PROCESS_AUTO_WORKFLOW_STEPS[i].id]) return i;
  }
  return PROCESS_AUTO_WORKFLOW_STEPS.length;
}

function getProcessWorkflowRunAllLabel() {
  const startIndex = getProcessWorkflowAutoStartIndex();
  if (startIndex >= PROCESS_AUTO_WORKFLOW_STEPS.length) return '已完成';
  return '一键执行' + (startIndex + 1) + '-5步';
}

function clearProcessWorkflowDoneStepsFromIndex(startIndex) {
  const doneStepIds = state.processWorkflowState.doneStepIds || {};
  const nextDoneStepIds = {};
  const endIndex = Math.max(0, Math.min(startIndex, PROCESS_AUTO_WORKFLOW_STEPS.length));
  // 只保留从第 1 步开始连续完成的前缀,避免跳过未完成的前置步骤。
  for (let i = 0; i < endIndex; i += 1) {
    const stepId = PROCESS_AUTO_WORKFLOW_STEPS[i].id;
    if (doneStepIds[stepId]) nextDoneStepIds[stepId] = true;
  }
  state.processWorkflowState.doneStepIds = nextDoneStepIds;
}

export function getProcessWorkflowStepMeta(step) {
  if (!step) return '';
  const workflowState = state.processWorkflowState;
  if (workflowState.doneStepIds && workflowState.doneStepIds[step.id]) return '已完成';
  if (workflowState.runningStepId === step.id) return '进行中';
  if (workflowState.awaitingStepId === step.id || workflowState.waitingUserStepId === step.id) return '等待输入';
  if (workflowState.activeStepId === step.id) return '当前步骤';
  return '';
}

export function updateProcessWorkflowCards() {
  if (!dom.workflowDock) return;
  const cards = dom.workflowDock.querySelectorAll('.process-workflow-msg');
  cards.forEach(function(card) {
    const activeStep = getProcessWorkflowStep(state.processWorkflowState.activeStepId) || PROCESS_AUTO_WORKFLOW_STEPS[0];
    const isBusy = Boolean(
      state.processWorkflowState.runningStepId ||
      state.processWorkflowState.awaitingStepId ||
      state.processWorkflowState.runningAll
    );
    const subtitle = card.querySelector('.process-workflow-subtitle');
    if (subtitle) {
      subtitle.textContent = '当前步骤：第 ' + (PROCESS_AUTO_WORKFLOW_STEPS.indexOf(activeStep) + 1) + ' 步 ' + activeStep.title;
    }
    const runAllBtn = card.querySelector('.process-workflow-run-all');
    if (runAllBtn) {
      const startIndex = getProcessWorkflowAutoStartIndex();
      const isAllDone = startIndex >= PROCESS_AUTO_WORKFLOW_STEPS.length;
      runAllBtn.disabled = isBusy || isAllDone;
      runAllBtn.textContent = state.processWorkflowState.runningAll
        ? '正在执行...'
        : getProcessWorkflowRunAllLabel();
    }
    const stepEls = card.querySelectorAll('.process-workflow-step');
    stepEls.forEach(function(btn) {
      const step = getProcessWorkflowStep(btn.getAttribute('data-step-id'));
      if (!step) return;
      const meta = getProcessWorkflowStepMeta(step);
      btn.className = 'process-workflow-step';
      if (state.processWorkflowState.activeStepId === step.id) btn.classList.add('is-active');
      if (state.processWorkflowState.doneStepIds[step.id]) btn.classList.add('is-done');
      if (meta === '进行中' || meta === '等待输入') btn.classList.add('is-running');
      btn.disabled = isBusy;
      const icon = btn.querySelector('.process-workflow-step-icon');
      if (icon) icon.textContent = state.processWorkflowState.doneStepIds[step.id] ? '✓' : String(PROCESS_AUTO_WORKFLOW_STEPS.indexOf(step) + 1);
      const metaEl = btn.querySelector('.process-workflow-step-meta');
      if (metaEl) metaEl.textContent = meta;
    });
  });
}

export function markProcessWorkflowStepDone(stepId) {
  const step = getProcessWorkflowStep(stepId);
  if (!step) return;
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = '';
  if (state.processWorkflowState.continueFromStepId === step.id) {
    state.processWorkflowState.continueFromStepId = '';
  }
  state.processWorkflowState.doneStepIds[step.id] = true;
  const idx = PROCESS_AUTO_WORKFLOW_STEPS.indexOf(step);
  const nextStep = PROCESS_AUTO_WORKFLOW_STEPS[idx + 1] || step;
  state.processWorkflowState.activeStepId = nextStep.id;
  updateProcessWorkflowCards();
}

export function markProcessWorkflowStepIdle(stepId) {
  const step = getProcessWorkflowStep(stepId);
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = '';
  if (step) state.processWorkflowState.activeStepId = step.id;
  updateProcessWorkflowCards();
}

function markAutoIdentifyRetryState() {
  // 第 2 步前置校验失败时保留第 1 步完成状态，让顶部按钮从第 2 步继续。
  state.processWorkflowState.doneStepIds = { select_group_template: true };
  state.processWorkflowState.activeStepId = 'auto_identify_template';
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = '';
  state.processWorkflowState.runningAll = false;
  state.processWorkflowState.continueFromStepId = 'auto_identify_template';
  updateProcessWorkflowCards();
}

function normalizeProcessWorkflowSize(width, height) {
  return {
    width: Math.max(540, Math.min(1600, Math.round(width || 0))),
    height: Math.max(120, Math.min(720, Math.round(height || 0)))
  };
}

function readStoredProcessWorkflowSize() {
  try {
    const raw = window.localStorage.getItem(PROCESS_WORKFLOW_SIZE_STORAGE_KEY);
    if (!raw) return null;
    const size = JSON.parse(raw);
    if (!size || !size.width || !size.height) return null;
    return normalizeProcessWorkflowSize(size.width, size.height);
  } catch (err) {
    return null;
  }
}

function applyProcessWorkflowSize(card, size) {
  if (!card) return;
  const normalized = normalizeProcessWorkflowSize(size.width, size.height);
  card.style.width = normalized.width + 'px';
  card.style.height = normalized.height + 'px';
}

function saveProcessWorkflowSize(card) {
  try {
    const rect = card.getBoundingClientRect();
    const size = normalizeProcessWorkflowSize(rect.width, rect.height);
    window.localStorage.setItem(PROCESS_WORKFLOW_SIZE_STORAGE_KEY, JSON.stringify(size));
  } catch (err) {
    // ignore
  }
}

function installProcessWorkflowResize(card) {
  const handle = document.createElement('span');
  handle.className = 'process-workflow-resize-handle';
  handle.title = '拖拽缩放，双击恢复默认大小';
  card.appendChild(handle);

  handle.addEventListener('dblclick', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    try { window.localStorage.removeItem(PROCESS_WORKFLOW_SIZE_STORAGE_KEY); } catch (err) { /* ignore */ }
    card.style.width = '';
    card.style.height = '';
  });

  handle.addEventListener('pointerdown', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const startX = ev.clientX;
    const startY = ev.clientY;
    const startRect = card.getBoundingClientRect();
    document.body.style.userSelect = 'none';

    function onPointerMove(moveEv) {
      applyProcessWorkflowSize(card, {
        width: startRect.width + moveEv.clientX - startX,
        height: startRect.height + moveEv.clientY - startY
      });
    }

    function stopResize() {
      document.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerup', stopResize);
      document.removeEventListener('pointercancel', stopResize);
      document.body.style.userSelect = '';
      saveProcessWorkflowSize(card);
    }

    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', stopResize);
    document.addEventListener('pointercancel', stopResize);
  });
}

export function addProcessWorkflowCard() {
  if (!dom.workflowDock) return null;
  if (!state.processWorkflowState) resetProcessWorkflowState();
  dom.workflowDock.innerHTML = '';

  const container = document.createElement('div');
  container.className = 'process-workflow-msg';

  const header = document.createElement('div');
  header.className = 'process-workflow-header';
  header.innerHTML =
    '<div class="process-workflow-title-wrap">' +
      '<div class="process-workflow-title"></div>' +
      '<div class="process-workflow-subtitle"></div>' +
    '</div>' +
    '<div class="process-workflow-actions">' +
      '<button type="button" class="process-workflow-open-route" title="打开或关闭工艺路线面板">工艺面板</button>' +
      '<button type="button" class="process-workflow-run-all" title="按顺序自动执行第 1-5 步，当前步完成后才开始下一步">一键执行1-5步</button>' +
      '<button type="button" class="process-workflow-reset" title="重置卡片状态和工作流，从第 1 步重新开始">重置</button>' +
    '</div>';
  container.appendChild(header);

  const title = header.querySelector('.process-workflow-title');
  if (title) title.textContent = 'AI 工艺自动生成工作流';

  const openRouteBtn = header.querySelector('.process-workflow-open-route');
  if (openRouteBtn) {
    openRouteBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      import('./process_route.js').then(function(m) {
        if (typeof m.openProcessRoutePanel === 'function') m.openProcessRoutePanel();
      });
    });
  }

  const runAllBtn = header.querySelector('.process-workflow-run-all');
  if (runAllBtn) {
    runAllBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      runProcessWorkflowAllSteps();
    });
  }

  const resetWorkflowBtn = header.querySelector('.process-workflow-reset');
  if (resetWorkflowBtn) {
    resetWorkflowBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      resetProcessWorkflowState();
      resetSession();
      clearLog();
      updateProcessWorkflowCards();
      setStatus('ok', '工作流已重置');
    });
  }

  const list = document.createElement('div');
  list.className = 'process-workflow-list';
  PROCESS_AUTO_WORKFLOW_STEPS.forEach(function(step, index) {
    const btn = document.createElement('button');
    btn.className = 'process-workflow-step';
    btn.type = 'button';
    btn.setAttribute('data-step-id', step.id);
    btn.innerHTML =
      '<span class="process-workflow-step-icon">' + (index + 1) + '</span>' +
      '<span class="process-workflow-step-body">' +
        '<span class="process-workflow-step-title">' + escapeHtml(step.title) + '</span>' +
        '<span class="process-workflow-step-desc">' + escapeHtml(step.desc) + '</span>' +
      '</span>' +
      '<span class="process-workflow-step-meta"></span>';
    btn.addEventListener('click', function(ev) {
      ev.preventDefault();
      // Step 1 is an explicit user-facing panel. Re-enter it directly even
      // when a previous auto-run left an awaiting marker behind.
      if (step.id === 'select_group_template' && !state.processWorkflowState.runningAll) {
        runProcessGroupTemplateSelection();
        return;
      }
      runProcessWorkflowStep(step.id);
    });
    list.appendChild(btn);
  });
  container.appendChild(list);

  const hint = document.createElement('div');
  hint.className = 'process-workflow-hint';
  hint.textContent = '可点击任一步骤执行；一键执行时收到 manual_defaults 后等待用户点击生成路线，路线完成后自动生成技术要求，提交由用户确认，提交后再继续第 5 步。';
  container.appendChild(hint);

  const storedSize = readStoredProcessWorkflowSize();
  if (storedSize) applyProcessWorkflowSize(container, storedSize);
  installProcessWorkflowResize(container);

  dom.workflowDock.appendChild(container);
  updateProcessWorkflowCards();
  return container;
}

export function showDefaultAssistantIntro() {
  if (!dom.workflowDock) return null;
  dom.workflowDock.innerHTML = '';
  dom.workflowDock.style.display = '';

  const container = document.createElement('div');
  container.className = 'default-assistant-intro';

  const capabilityItems = DEFAULT_ASSISTANT_CAPABILITIES.map(function(item) {
    return '<li><strong>' + escapeHtml(item.title) + '</strong><span>' + escapeHtml(item.desc) + '</span></li>';
  }).join('');

  container.innerHTML =
    '<div class="default-assistant-intro-header">' +
      '<div>' +
        '<div class="default-assistant-intro-title">默认助手</div>' +
        '<div class="default-assistant-intro-subtitle">我可以帮你理解和使用 3DMPS MCP 工具，也可以协助排查问题。</div>' +
      '</div>' +
      '<span class="default-assistant-intro-badge">通用问答 / 工具协助</span>' +
    '</div>' +
    '<ul class="default-assistant-intro-list">' + capabilityItems + '</ul>' +
    '<div class="default-assistant-intro-note">如需执行 AI 工艺自动生成 1-5 步流程，请切换到工艺自动生成智能体。</div>';

  dom.workflowDock.appendChild(container);
  return container;
}

export function showProcessAutoWorkflow() {
  if (!dom.workflowDock) return;
  dom.workflowDock.style.display = '';
  if (!dom.workflowDock.querySelector('.process-workflow-msg')) {
    addProcessWorkflowCard();
  } else {
    updateProcessWorkflowCards();
  }
}

function addProcessTemplateTypeCards() {
  const container = document.createElement('div');
  container.className = 'template-type-msg';
  container.innerHTML =
    '<div class="template-type-header"><span>▣</span><span>请先选择模板类型</span></div>' +
    '<div class="template-type-grid"></div>';
  const grid = container.querySelector('.template-type-grid');
  PROCESS_TEMPLATE_TYPES.forEach(function(type) {
    grid.appendChild(buildTemplateTypeCardEl(type));
  });
  dom.log.appendChild(container);
  dom.log.scrollTop = dom.log.scrollHeight;
}

function buildTemplateTypeCardEl(type) {
  const card = document.createElement('button');
  card.className = 'template-type-card';
  card.type = 'button';
  card.setAttribute('data-template-type', type.id || '');

  const tags = (type.tags || []).slice(0, 5)
    .map(function(tag) { return '<span class="template-type-tag">' + escapeHtml(tag) + '</span>'; }).join('');
  card.innerHTML =
    '<div class="template-type-title">' +
      '<span class="template-type-icon">' + escapeHtml(type.icon || type.title || '') + '</span>' +
      '<span>' + escapeHtml(type.title || '') + '</span>' +
    '</div>' +
    '<div class="template-type-desc">' + escapeHtml(type.desc || '') + '</div>' +
    (tags ? '<div class="template-type-tags">' + tags + '</div>' : '');

  card.addEventListener('click', function(ev) {
    ev.preventDefault();
    if (state.processWorkflowState.runningStepId || card.disabled) return;
    const cards = dom.log.querySelectorAll('.template-type-card');
    cards.forEach(function(item) { item.classList.remove('is-selected'); });
    card.classList.add('is-selected');
    runProcessGroupTemplateWithType(type);
  });

  return card;
}

function runProcessGroupTemplateSelection() {
  const stepId = 'select_group_template';
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = stepId;
  updateProcessWorkflowCards();
  addUserMsg('匹配分组模板');
  addBotMsg('当前零件将从固定目录读取 XML 和 stepModel.stp；点击查询相似零件后确认右侧候选并应用其分组模板。');
  setStatus('warn', '从固定目录读取当前零件 XML 并查询相似零件');
  import('./similar_parts.js').then(function(module) {
    module.openSimilarPartsPanel({ autoContinue: !!state.processWorkflowState.runningAll });
  }).catch(function(error) {
    markProcessWorkflowStepIdle(stepId);
    addErrorMsg('相似零件面板加载失败：' + error.message);
    setStatus('err', '相似零件面板加载失败');
  });
}

function runProcessGroupTemplateWithType(type) {
  const stepId = 'select_group_template';
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = stepId;
  state.processWorkflowState.awaitingStepId = '';
  updateProcessWorkflowCards();
  addUserMsg('选择分组模板类型：' + type.title);
  setStatus('warn', '正在获取分组模板候选...');
  requestJson('POST', '/api/tool', JSON.stringify({
    function: 'kmsoft_group_template_propose',
    params: { text: type.text, limit: 3 }
  }), function(data) {
    const result = data && data.result ? data.result : data;
    state.processWorkflowState.runningStepId = '';
    state.processWorkflowState.activeStepId = stepId;
    updateProcessWorkflowCards();
    if (isToolSuccess(result) && Array.isArray(result.candidates) && result.candidates.length > 0) {
      result.__processAutoSelectGroupTemplateOnly = true;
      import('./tool_call.js').then(function(m) {
        m.addToolCall('kmsoft_group_template_propose', { text: type.text, limit: 3 }, result);
      });
      addBotMsg('已按“' + (type.title || '') + '”推荐候选模板。请选择一个分组模板，点击卡片按钮后将执行写入模板库并加载。');
      setStatus('ok', '等待选择分组模板');
    } else {
      markProcessWorkflowStepIdle(stepId);
      addErrorMsg((result && (result.reply || result.message)) || '未找到可选分组模板，请换一个模板类型或补充零件描述后重试。');
      setStatus('err', '未找到分组模板');
    }
  }, function(err) {
    markProcessWorkflowStepIdle(stepId);
    addErrorMsg('获取分组模板候选失败：' + err.message);
    setStatus('err', '获取分组模板候选失败');
  }, 30000);
}

function runProcessAutoIdentifySelection() {
  const stepId = 'auto_identify_template';
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = stepId;
  state.processWorkflowState.awaitingStepId = '';
  updateProcessWorkflowCards();
  addUserMsg('点击自动识别并确认自动识别加工特征对话框');
  setStatus('warn', '正在打开自动识别加工特征对话框并点击确定...');
  return new Promise(function(resolve, reject) {
    requestJson('POST', '/api/tool', JSON.stringify({
      function: 'open_and_confirm_autoidentify_dialog',
      params: {},
      timeout: 120
    }), function(data) {
      const result = data && data.result ? data.result : data;
      import('./tool_call.js').then(function(m) {
        m.addToolCall('open_and_confirm_autoidentify_dialog', {}, result);
      });
      state.processWorkflowState.runningStepId = '';
      if (isToolSuccess(result)) {
        markProcessWorkflowStepDone(stepId);
        addBotMsg((result && result.message) || '已打开自动识别加工特征对话框并点击确定。');
        setStatus('ok', '自动识别步骤已完成');
        resolve(result);
        return;
      }

      const message = getToolErrorMessage(result, '自动识别对话框确认失败');
      markAutoIdentifyRetryState();
      addErrorMsg(message);
      setStatus('err', '自动识别确认失败');
      reject(new Error(message));
    }, function(err) {
      const message = '自动识别对话框确认失败：' + err.message;
      markAutoIdentifyRetryState();
      addErrorMsg(message);
      setStatus('err', '自动识别确认失败');
      reject(new Error(message));
    }, 125000);
  });
}

async function runProcessFeatureReasoningAutoStep() {
  const stepId = 'feature_reasoning';
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = stepId;
  state.processWorkflowState.awaitingStepId = '';
  updateProcessWorkflowCards();
  addUserMsg('执行第3步：特征推理');
  setStatus('warn', '正在触发特征推理...');
  const { callTool } = await import('./shared.js');
  const result = await callTool('ai_feature_inference', {}, 120, 125000);
  import('./tool_call.js').then(function(m) {
    m.addToolCall('ai_feature_inference', {}, result);
  });
  state.processWorkflowState.runningStepId = '';
  if (isToolSuccess(result)) {
    markProcessWorkflowStepDone(stepId);
    addBotMsg((result && result.message) || '已触发 3DMPS 特征推理。');
    setStatus('ok', '特征推理已触发');
    await waitForFeatureReasoningSettle();
    return result;
  }
  markProcessWorkflowStepIdle(stepId);
  throw new Error(getToolErrorMessage(result, '特征推理失败'));
}

function getFeatureReasoningSettleMs() {
  try {
    if (typeof window !== 'undefined' && Number.isFinite(window.__KM_FEATURE_SETTLE_MS__)) {
      return Math.max(0, window.__KM_FEATURE_SETTLE_MS__ | 0);
    }
  } catch (err) {
    // ignore
  }
  return FEATURE_REASONING_SETTLE_MS;
}

async function waitForFeatureReasoningSettle() {
  const settleMs = getFeatureReasoningSettleMs();
  if (!settleMs) return;
  const startedAt = Date.now();
  while (Date.now() - startedAt < settleMs) {
    const remaining = Math.max(0, Math.ceil((settleMs - (Date.now() - startedAt)) / 1000));
    setStatus('warn', '等待特征推理后台完成...' + remaining + 's');
    await new Promise(function(resolve) { window.setTimeout(resolve, Math.min(1000, settleMs)); });
  }
}

async function runProcessAiProcessInputAutoStep() {
  const stepId = 'ai_process_input';
  const step = getProcessWorkflowStep(stepId);
  const pr = await import('./process_route.js');
  pr.runProcessAiProcessInputStep(step);
  await waitForProcessWorkflowStepDone(stepId, 900000);
  return true;
}

async function runProcessGenerateAllModelAutoStep() {
  const stepId = 'generate_all_model';
  const step = getProcessWorkflowStep(stepId);
  const result = await runProcessGenerateAllModelStep(step);
  setStatus('ok', '1-5步流程已全部完成');
  return result;
}

export async function runProcessGenerateAllModelStep(step) {
  const stepId = step.id;
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = stepId;
  state.processWorkflowState.awaitingStepId = '';
  updateProcessWorkflowCards();
  addUserMsg('执行第5步：生成全部工序模型');
  setStatus('warn', '正在生成全部工序模型...');
  const { callTool } = await import('./shared.js');
  const result = await callTool('click_generate_all_button', {}, 120, 125000);
  import('./tool_call.js').then(function(m) {
    m.addToolCall('click_generate_all_button', {}, result);
  });
  state.processWorkflowState.runningStepId = '';
  if (isToolSuccess(result)) {
    markProcessWorkflowStepDone(stepId);
    addBotMsg((result && result.message) || '已请求 3DMPS 生成全部工序模型。');
    setStatus('ok', '生成全部工序模型已完成');
    return result;
  }
  markProcessWorkflowStepIdle(stepId);
  throw new Error(getToolErrorMessage(result, '生成全部工序模型失败'));
}

export async function runProcessWorkflowStep(stepId) {
  if (state.processWorkflowState.runningStepId || state.processWorkflowState.awaitingStepId || state.processWorkflowState.runningAll) return;
  const step = getProcessWorkflowStep(stepId);
  if (!step) return;
  // 离开第 4 步(ai_process_input)时,把上一次的「待处理工艺输入」卡片清掉,
  // 并复位工艺路线面板的状态机,避免新 polling 在用户还没点第 4 步时把卡片加回来。
  if (step.id !== 'ai_process_input') {
    Promise.all([
      import('./tool_call.js'),
      import('./process_route.js')
    ]).then(function(mods) {
      if (mods[0] && typeof mods[0].clearProcessRouteInboxCard === 'function') {
        mods[0].clearProcessRouteInboxCard();
      }
      if (mods[1] && typeof mods[1].resetProcessRoutePanelFlowState === 'function') {
        mods[1].resetProcessRoutePanelFlowState();
      }
    }).catch(function() {});
  }
  if (step.id === 'select_group_template') {
    runProcessGroupTemplateSelection();
    return;
  }
  if (step.id === 'auto_identify_template') {
    runProcessAutoIdentifySelection().catch(function() {});
    return;
  }
  if (step.id === 'feature_reasoning') {
    runProcessFeatureReasoningAutoStep();
    return;
  }
  if (step.id === 'ai_process_input') {
    const pr = await import('./process_route.js');
    pr.runProcessAiProcessInputStep(step);
    return;
  }
  if (step.id === 'generate_all_model') {
    runProcessGenerateAllModelStep(step);
    return;
  }
  state.processWorkflowState.activeStepId = step.id;
  state.processWorkflowState.runningStepId = step.id;
  state.processWorkflowState.awaitingStepId = '';
  updateProcessWorkflowCards();
  const { sendProcessWorkflowPrompt } = await import('./chat.js');
  const ok = await sendProcessWorkflowPrompt(step.prompt);
  state.processWorkflowState.runningStepId = '';
  if (ok) {
    markProcessWorkflowStepDone(step.id);
  } else {
    markProcessWorkflowStepIdle(step.id);
  }
}

async function runProcessWorkflowAutoStepByIndex(index) {
  const step = PROCESS_AUTO_WORKFLOW_STEPS[index];
  if (!step) return;
  if (step.id === 'select_group_template') {
    await runProcessGroupTemplateAutoStep();
    return;
  }
  if (step.id === 'auto_identify_template') {
    await runProcessAutoIdentifyAutoStep();
    return;
  }
  if (step.id === 'feature_reasoning') {
    await runProcessFeatureReasoningAutoStep();
    return;
  }
  if (step.id === 'ai_process_input') {
    await runProcessAiProcessInputAutoStep();
    return;
  }
  if (step.id === 'generate_all_model') {
    await runProcessGenerateAllModelAutoStep();
  }
}

export async function runProcessWorkflowAllSteps() {
  if (state.processWorkflowState.runningStepId || state.processWorkflowState.awaitingStepId || state.processWorkflowState.runningAll) return;
  const startIndex = getProcessWorkflowAutoStartIndex();
  if (startIndex >= PROCESS_AUTO_WORKFLOW_STEPS.length) {
    updateProcessWorkflowCards();
    return;
  }
  state.processWorkflowState.runningAll = false;
  state.processWorkflowState.autoSubmittedRoute = false;
  state.processWorkflowState.autoSubmittingRouteKey = '';
  state.processWorkflowState.autoRouteError = '';
  state.processWorkflowState.autoGeneratingTechnical = false;
  state.processWorkflowState.continueFromStepId = '';
  clearProcessWorkflowDoneStepsFromIndex(startIndex);
  state.processWorkflowState.activeStepId = PROCESS_AUTO_WORKFLOW_STEPS[startIndex].id;
  try {
    updateProcessWorkflowCards();
    if (startIndex > 0) {
      addBotMsg('继续自动执行第 ' + (startIndex + 1) + '-5 步。');
    }
    for (let i = startIndex; i < PROCESS_AUTO_WORKFLOW_STEPS.length; i += 1) {
      if (i > 0 && !state.processWorkflowState.runningAll) {
        state.processWorkflowState.runningAll = true;
        updateProcessWorkflowCards();
      }
      await runProcessWorkflowAutoStepByIndex(i);
    }
  } catch (err) {
    const message = err && err.message ? err.message : String(err || '未知错误');
    addErrorMsg('一键执行已停止：' + message);
    setStatus('err', '一键执行失败：' + message);
  } finally {
    state.processWorkflowState.runningAll = false;
    state.processWorkflowState.runningStepId = '';
    state.processWorkflowState.awaitingStepId = '';
    state.processWorkflowState.waitingUserStepId = '';
    updateProcessWorkflowCards();
  }
}

export async function runProcessGroupTemplateAutoStep() {
  const stepId = 'select_group_template';
  state.processWorkflowState.waitingUserStepId = stepId;
  runProcessGroupTemplateSelection();
  setStatus('warn', '从固定目录读取 XML、查询相似零件并应用模板；完成后将自动继续第2步。');
  try {
    await waitForProcessWorkflowStepDone(stepId, 300000);
    return true;
  } finally {
    state.processWorkflowState.waitingUserStepId = '';
  }
}

export async function runProcessAutoIdentifyAutoStep() {
  // 前置检查失败时让 reject 直接向上抛，使一键执行循环立即停止；
  // 避免旧循环仍挂在 waitForProcessWorkflowStepDone 上，重跑时与新循环并发触发第 3 步。
  await runProcessAutoIdentifySelection();
  return true;
}

function waitForProcessWorkflowStepDone(stepId, timeoutMs) {
  const step = getProcessWorkflowStep(stepId);
  const stepTitle = step ? step.title : stepId;
  const startedAt = Date.now();
  const intervalMs = 500;
  return new Promise(function(resolve, reject) {
    function check() {
      if (state.processWorkflowState.doneStepIds && state.processWorkflowState.doneStepIds[stepId]) {
        resolve(true);
        return;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        reject(new Error('等待' + stepTitle + '完成超时'));
        return;
      }
      window.setTimeout(check, intervalMs);
    }
    check();
  });
}

export const workflowActions = {
  onAddProcessWorkflowCard: addProcessWorkflowCard,
  onShowProcessAutoWorkflow: showProcessAutoWorkflow,
};
