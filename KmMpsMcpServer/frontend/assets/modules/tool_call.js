// tool_call.js —— 工具调用结果渲染。
//
// 负责把 LLM 在 SSE 流里推过来的 `tool_call` 事件渲染成可视化卡片:
//   - 简单的 <details> 折叠 JSON(无 UI 字段时)
//   - option_cards 候选卡片(由 kmsoft_group_template_propose 等返回)
//   - 写入 3DMPS 安装目录后的保存状态横幅
//   - XML 编辑器(模板编辑场景,弹一个 textarea 让用户改完保存)
//   - 工艺输入 inbox 卡片(3DMPS 推过来的 process route input JSON 预览)
//
// 与 workflow.js 的边界:卡片的「点选后做什么」(applyGroupTemplate* 等)由本模块发起,
// 但状态机的变更(标记步骤 done / idle)通过 setter 注入进来,避免循环 import。

import {
  state, dom, escapeHtml, setStatus, addErrorMsg, addMsg,
  requestJson, isToolSuccess, getToolErrorMessage,
  buildProcessRouteInboxText,
  PROCESS_AUTO_AGENT_ID,
} from './shared.js';

// workflow 模块注入进来的 setter(标记步骤 done / idle)
let _markProcessWorkflowStepDone = null;
let _markProcessWorkflowStepIdle = null;

export function setToolCallDeps(deps) {
  _markProcessWorkflowStepDone = deps.markProcessWorkflowStepDone;
  _markProcessWorkflowStepIdle = deps.markProcessWorkflowStepIdle;
}

// ============================================================
// 入口:根据 result.ui 自动选渲染路径
// ============================================================

/**
 * 工具结果渲染入口。
 *   - result.ui 存在 → 走可视化卡片(option_cards)
 *   - 否则 → 简单 <details> 折叠 JSON
 */
export function addToolCall(toolName, args, result) {
  if (result && Array.isArray(result.ui) && result.ui.length > 0) {
    addOptionCards(toolName, args, result);
    return;
  }
  const html = '<details class="tool-call">' +
    '<summary><span class="tool-call-label">调用工具</span> <code class="tool-call-name">' + escapeHtml(toolName) + '</code></summary>' +
    '<div class="tool-call-body">' +
      '<div class="tool-call-row"><b>参数</b><pre>' + escapeHtml(JSON.stringify(args, null, 2)) + '</pre></div>' +
      '<div class="tool-call-row"><b>结果</b><pre>' + escapeHtml(JSON.stringify(result, null, 2)) + '</pre></div>' +
    '</div>' +
    '</details>';
  if (typeof state !== 'undefined' && state && state.debugMode === false) {
    return; // 调试模式关闭时不渲染 tool-call,只保留可视化卡片
  }
  addMsg('bot', html);
}

// ============================================================
// 渲染:option_cards 候选卡片
// ============================================================

function addOptionCards(toolName, args, result) {
  const container = document.createElement('div');
  container.className = 'cards-msg';

  const candidates = Array.isArray(result.candidates) ? result.candidates : [];
  const candidateCount = candidates.length;
  const stage = result.stage || '';
  const stageText = stage === 'select_group_template' ? '分组模板' :
                    stage === 'select_template' ? '模板' :
                    (stage || '');

  const saveResult = result.save_result;
  const selectedTemplate = result.selectedTemplate || {};
  const isConfirm = result.mode === 'completed';

  let headerHtml;
  if (isConfirm) {
    // confirm 模式: 用「已确认」措辞更自然
    const tmplName = (saveResult && saveResult.filename) ||
                     selectedTemplate.filename || selectedTemplate.displayName || selectedTemplate.title ||
                     (candidates[0] && (candidates[0].filename || candidates[0].displayName)) || '';
    headerHtml = '<div class="cards-header">' +
      '<span class="cards-icon">✓</span>' +
      '<span>已确认分组模板：<b>' + escapeHtml(tmplName) + '</b></span>' +
      '</div>';
  } else {
    headerHtml = '<div class="cards-header">' +
      '<span class="cards-icon">📋</span>' +
      '<span>共找到 <b>' + candidateCount + '</b> 个候选：' + escapeHtml(stageText) +
      (candidateCount > 0 ? '请选择：' : '</span></div>') +
      '</div>';
  }
  container.innerHTML = headerHtml;

  if (candidateCount === 0) {
    // 候选为空(needs_input 场景),给用户提示
    const empty = document.createElement('div');
    empty.className = 'cards-empty';
    empty.textContent = result.reply || '未找到匹配的候选，请补充描述。';
    container.appendChild(empty);
    if (saveResult) container.appendChild(buildSaveStatusEl(saveResult));
    dom.log.appendChild(container);
    dom.log.scrollTop = dom.log.scrollHeight;
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'cards-grid';

  for (const ui of result.ui) {
    if (ui.type !== 'option_cards' || !Array.isArray(ui.options)) continue;
    if (result.__processAutoSelectGroupTemplateOnly) ui.groupTemplateOnly = true;
    for (const opt of ui.options) {
      grid.appendChild(buildOptionCardEl(opt, ui));
    }
  }
  container.appendChild(grid);

  const browseButton = buildBrowseMoreGroupTemplatesButton(toolName, args, result, candidates);
  if (browseButton) container.appendChild(browseButton);

  // 只有显式保存 XML 时,才在卡片下方追加保存状态横幅
  if (saveResult) container.appendChild(buildSaveStatusEl(saveResult));

  dom.log.appendChild(container);
  dom.log.scrollTop = dom.log.scrollHeight;
}

function shouldShowBrowseMoreGroupTemplates(result) {
  if (!result || result.stage !== 'select_group_template' || result.mode === 'completed') return false;
  const browse = result.browse || {};
  return Boolean(browse.available && browse.mode !== 'all');
}

function collectTemplateIdsFromResult(result, candidates) {
  const ids = new Set();
  (candidates || []).forEach(function(item) {
    const id = item && (item.templateId || item.id || item.choiceId);
    if (id) ids.add(String(id));
  });
  (result.ui || []).forEach(function(ui) {
    (ui.options || []).forEach(function(opt) {
      const id = opt && (opt.templateId || opt.id || opt.choiceId);
      if (id) ids.add(String(id));
    });
  });
  return Array.from(ids);
}

function buildBrowseMoreGroupTemplatesButton(toolName, args, result, candidates) {
  if (toolName !== 'kmsoft_group_template_propose' || !shouldShowBrowseMoreGroupTemplates(result)) return null;
  const queryText = String((args && args.text) || result.queryText || '').trim();
  if (!queryText) return null;

  const row = document.createElement('div');
  row.className = 'cards-browse-row';
  const button = document.createElement('button');
  button.className = 'cards-browse-button';
  button.type = 'button';
  button.textContent = '浏览其它模板';
  const meta = document.createElement('span');
  meta.className = 'cards-browse-meta';
  const total = result.browse && Number(result.browse.total || 0);
  const shown = result.browse && Number(result.browse.shown || 0);
  meta.textContent = total > shown ? '模板库共 ' + total + ' 个，已显示 ' + shown + ' 个' : '';

  button.addEventListener('click', function(ev) {
    ev.preventDefault();
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = '正在加载...';
    setStatus('warn', '正在浏览其它分组模板...');

    const params = {
      text: queryText,
      limit: 100,
      browseAll: true,
      excludeTemplateIds: collectTemplateIdsFromResult(result, candidates)
    };
    requestJson('POST', '/api/tool', JSON.stringify({
      function: 'kmsoft_group_template_propose',
      params: params
    }), function(data) {
      const browseResult = data && data.result ? data.result : data;
      if (browseResult && (result.__processAutoSelectGroupTemplateOnly || state.currentAgentId === PROCESS_AUTO_AGENT_ID)) {
        browseResult.__processAutoSelectGroupTemplateOnly = true;
      }
      if (isToolSuccess(browseResult) && Array.isArray(browseResult.candidates) && browseResult.candidates.length > 0) {
        addToolCall('kmsoft_group_template_propose', params, browseResult);
        button.textContent = '已展开其它模板';
        setStatus('ok', '已展开其它分组模板');
      } else {
        addErrorMsg(getToolErrorMessage(browseResult, '没有其它可浏览的分组模板。'));
        button.disabled = false;
        button.textContent = '浏览其它模板';
        setStatus('warn', '没有其它分组模板');
      }
    }, function(err) {
      addErrorMsg('浏览其它分组模板失败：' + err.message);
      button.disabled = false;
      button.textContent = '浏览其它模板';
      setStatus('err', '浏览其它分组模板失败');
    }, 30000);
  });

  row.appendChild(button);
  if (meta.textContent) row.appendChild(meta);
  return row;
}

// 统一生成结构摘要；不能用简单真值判断，否则合法的 0 会被当成缺失。
function formatOptionCardMeta(meta) {
  const source = meta || {};
  const parts = [];
  if (source.groupCount !== undefined && source.groupCount !== null && source.groupCount !== '') {
    parts.push(String(source.groupCount) + ' 组');
  }
  if (source.depth !== undefined && source.depth !== null && source.depth !== '') {
    parts.push(String(source.depth) + ' 层');
  }
  return parts.length ? '结构：' + parts.join(' / ') : '';
}

// 单张候选卡,DOM
function buildOptionCardEl(opt, ui) {
  const card = document.createElement('div');
  card.className = 'option-card';
  if (ui && ui.groupTemplateOnly) card.setAttribute('data-group-template-only', '1');
  if (opt.selected) card.classList.add('is-selected');
  card.setAttribute('data-template-id', opt.templateId || opt.id || '');

  const conf = Number(opt.confidence || 0);
  const confPct = (conf * 100).toFixed(1);
  const confCls = conf >= 0.7 ? 'high' : (conf >= 0.4 ? 'mid' : 'low');
  const fullStars = Math.round(conf * 5);
  const stars = '★'.repeat(fullStars) + '☆'.repeat(5 - fullStars);

  const rawFilename = opt.filename || opt.subtitle || '';
  const rawTitle = rawFilename ? deriveDisplayNameFromFilename(rawFilename) : (opt.title || opt.templateId || '(未命名)');
  const title = escapeHtml(rawTitle);
  const subtitle = escapeHtml(rawFilename);
  const reasons = (opt.reasons || []).slice(0, 3)
    .map(r => '<span class="card-reason">' + escapeHtml(r) + '</span>').join('');
  const tags = (opt.tags || []).slice(0, 6)
    .map(t => '<span class="card-tag">' + escapeHtml(t) + '</span>').join('');
  const metaText = formatOptionCardMeta(opt.meta);

  card.innerHTML =
    '<div class="option-card-head">' +
      '<span class="option-card-title" title="' + title + '">' + title + '</span>' +
      '<span class="option-card-confidence ' + confCls + '">' + confPct + '%</span>' +
    '</div>' +
    '<button class="option-card-icon-btn" type="button" data-action="edit-card" title="编辑该模板卡片">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>' +
    '</button>' +
    (subtitle ? '<div class="option-card-subtitle" title="' + subtitle + '">' + subtitle + '</div>' : '') +
    '<div class="option-card-stars">' + stars + '</div>' +
    (reasons ? '<div class="option-card-reasons">' + reasons + '</div>' : '') +
    (tags ? '<div class="option-card-tags">' + tags + '</div>' : '') +
    '<div class="option-card-footer">' +
      (metaText ? '<div class="option-card-meta" title="' + escapeHtml(metaText) + '">' + escapeHtml(metaText) + '</div>' : '') +
      '<div class="option-card-actions">' +
        '<button class="option-card-button" type="button" data-action="apply-card">' + getOptionCardActionText(false, ui && ui.groupTemplateOnly) + '</button>' +
      '</div>' +
    '</div>';

  // 绑定点击:当前智能体第一步只写入/应用分组模板;其它场景保留原串联流程。
  const btn = card.querySelector('[data-action="apply-card"]');
  btn.addEventListener('click', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    if (btn.disabled) return;
    applyGroupTemplateFromCard(card, btn, opt);
  });

  // 右上角小编辑按钮 -> 打开卡片编辑弹窗
  const editBtn = card.querySelector('[data-action="edit-card"]');
  if (editBtn) {
    editBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      openOptionCardEditor(opt, card);
    });
  }

  return card;
}

function getOptionCardActionText(applied, groupTemplateOnly) {
  if (groupTemplateOnly || state.currentAgentId === PROCESS_AUTO_AGENT_ID) {
    return applied ? '已完成加载' : '写入模板库并加载';
  }
  return applied ? '已完成串联' : '写入应用并识别推理';
}

function resetOptionCardButtons(activeCard, applied) {
  const allCards = dom.log.querySelectorAll('.option-card');
  allCards.forEach(function(c) {
    const b = c.querySelector('[data-action="apply-card"]');
    if (!b) return;
    const isActive = c === activeCard;
    b.disabled = Boolean(applied && isActive);
    setOptionCardEditLocked(c, false);
    b.textContent = getOptionCardActionText(Boolean(applied && isActive), c.getAttribute('data-group-template-only') === '1');
    if (applied && isActive) {
      c.classList.add('is-selected');
    } else if (!isActive) {
      c.classList.remove('is-selected');
    }
  });
}

function setOptionCardEditLocked(card, locked) {
  if (!card) return;
  const editBtn = card.querySelector('[data-action="edit-card"]');
  if (!editBtn) return;
  editBtn.disabled = false;
  editBtn.classList.toggle('is-disabled', Boolean(locked));
  editBtn.title = '编辑该模板卡片';
}

function resetOptionCardForTemplateEdit(card) {
  if (!card) return;
  card.classList.remove('is-selected');
  const button = card.querySelector('[data-action="apply-card"]');
  if (button) {
    button.disabled = false;
    button.textContent = getOptionCardActionText(false, card.getAttribute('data-group-template-only') === '1');
  }
  setOptionCardEditLocked(card, false);
}

function setOptionCardBusy(activeCard, text) {
  const allCards = dom.log.querySelectorAll('.option-card');
  allCards.forEach(function(c) {
    const b = c.querySelector('[data-action="apply-card"]');
    if (b) b.disabled = true;
    c.classList.remove('is-selected');
  });
  activeCard.classList.add('is-selected');
  const activeButton = activeCard.querySelector('[data-action="apply-card"]');
  if (activeButton) activeButton.textContent = text || '串联执行中...';
}

// ============================================================
// 候选卡点击行为(分组模板)
// ============================================================

function applyGroupTemplateFromCard(card, btn, opt) {
  if (state.currentAgentId === PROCESS_AUTO_AGENT_ID || card.getAttribute('data-group-template-only') === '1') {
    applyGroupTemplateOnlyFromCard(card, btn, opt);
    return;
  }
  applyGroupTemplateFullFlowFromCard(card, btn, opt);
}

function applyGroupTemplateOnlyFromCard(card, btn, opt) {
  const rawName = getTemplateCardRawName(opt, card);
  const templateName = normalizeTemplateNameForApply(rawName);
  if (!templateName) {
    addErrorMsg('未找到模板名称，无法写入模板库并加载。');
    resetOptionCardButtons(card, false);
    return;
  }

  const applyParams = buildApplyGroupTemplateParams(opt, templateName, card);
  addUserMsgCompat('写入模板库，并加载到当前 BOF 根节点：' + templateName);
  setStatus('warn', '正在写入模板库并加载分组模板...');
  state.processWorkflowState.activeStepId = 'select_group_template';
  state.processWorkflowState.runningStepId = 'select_group_template';
  // 触发 workflow 模块的 UI 更新
  import('./workflow.js').then(m => m.updateProcessWorkflowCards());
  setOptionCardBusy(card, '加载中...');
  requestJson('POST', '/api/tool', JSON.stringify({
    function: 'apply_group_template',
    params: applyParams,
    timeout: 120
  }), function(data) {
    const result = data && data.result ? data.result : data;
    addToolCall('apply_group_template', applyParams, result);
    if (isToolSuccess(result)) {
      resetOptionCardButtons(card, true);
      if (_markProcessWorkflowStepDone) _markProcessWorkflowStepDone('select_group_template');
      addBotMsgCompat(result.message || ('已完成写入模板库并加载分组模板：' + templateName));
      setStatus('ok', '分组模板加载完成');
    } else {
      const msg = getToolErrorMessage(result, '加载失败');
      if (_markProcessWorkflowStepIdle) _markProcessWorkflowStepIdle('select_group_template');
      resetOptionCardButtons(card, false);
      addErrorMsg('分组模板加载失败：' + msg);
      setStatus('err', '分组模板加载失败');
    }
  }, function(err) {
    if (_markProcessWorkflowStepIdle) _markProcessWorkflowStepIdle('select_group_template');
    resetOptionCardButtons(card, false);
    addErrorMsg('分组模板加载失败：' + err.message);
    setStatus('err', '分组模板加载失败');
  }, 120000);
}

function applyGroupTemplateFullFlowFromCard(card, btn, opt) {
  const rawName = getTemplateCardRawName(opt, card);
  const templateName = normalizeTemplateNameForApply(rawName);
  if (!templateName) {
    addErrorMsg('未找到模板名称，无法应用到当前零件。');
    resetOptionCardButtons(card, false);
    return;
  }

  const applyParams = buildApplyGroupTemplateParams(opt, templateName, card);
  addUserMsgCompat('写入模板库、应用到当前零件，并继续自动识别和特征推理：' + templateName);
  setStatus('warn', '正在执行模板应用、自动识别和特征推理...');
  setOptionCardBusy(card, '串联执行中...');
  requestJson('POST', '/api/tool', JSON.stringify({
    function: 'apply_group_template_full_flow',
    params: applyParams
  }), function(data) {
    const result = data && data.result ? data.result : data;
    addToolCall('apply_group_template_full_flow', applyParams, result);
    if (isToolSuccess(result)) {
      resetOptionCardButtons(card, true);
      addBotMsgCompat(result.message || ('已完成分组模板应用和自动识别，并已触发特征推理：' + templateName));
      setStatus('ok', '串联执行完成');
    } else {
      const msg = getToolErrorMessage(result, '应用失败');
      resetOptionCardButtons(card, false);
      addErrorMsg('串联执行失败：' + msg);
      setStatus('err', '串联执行失败');
    }
  }, function(err) {
    resetOptionCardButtons(card, false);
    addErrorMsg('串联执行失败：' + err.message);
    setStatus('err', '串联执行失败');
  }, 300000);
}

function normalizeTemplateNameForApply(value) {
  let name = String(value || '').trim();
  if (!name) return '';
  name = name.replace(/\\\\/g, '/').split('/').pop();
  name = name.replace(/\.xml$/i, '').trim();
  return name;
}

function normalizeTemplateFilenameInput(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) return '';
  if (trimmed.toLowerCase().endsWith('.xml')) return trimmed;
  return trimmed + '.xml';
}

function deriveDisplayNameFromFilename(filename) {
  const normalized = String(filename || '').trim();
  if (!normalized) return '';
  return normalized.replace(/\.xml$/i, '');
}

function getEditedTemplatePayload(opt, card) {
  const edited = (card && card.__kmaiEditedTemplate) || (opt && opt.__kmaiEditedTemplate);
  if (!edited) return null;
  if (!edited.filename || !edited.xml) return null;
  return edited;
}

function getTemplateCardRawName(opt, card) {
  const edited = getEditedTemplatePayload(opt, card);
  if (edited && edited.filename) return edited.filename;
  return opt.templateName || opt.filename || opt.subtitle || opt.title || opt.templateId || opt.id || '';
}

function buildApplyGroupTemplateParams(opt, templateName, card) {
  const params = { template_name: templateName };
  const templateId = opt.templateId || opt.template_id || opt.choiceId || opt.id || '';
  const filename = opt.filename || opt.subtitle || '';
  if (templateId) params.templateId = templateId;
  if (filename) params.filename = filename;
  const edited = getEditedTemplatePayload(opt, card);
  if (edited) {
    params.filename = edited.filename;
    params.xml = edited.xml;
  }
  return params;
}

// 因为 chat.js 里的 addUserMsg/addBotMsg 也会用,这里再 export 一下方便不绕弯
function addUserMsgCompat(text) {
  addMsg('user', escapeHtml(text));
}

function addBotMsgCompat(text) {
  addMsg('bot', escapeHtml(text));
}

// ============================================================
// 保存状态横幅
// ============================================================

/** 渲染保存状态横幅(仅 XML 编辑器显式保存时使用) */
export function buildSaveStatusEl(saveResult) {
  const el = document.createElement('div');
  if (saveResult && saveResult.status === 'success') {
    el.className = 'save-status save-status-ok';
    el.innerHTML =
      '<span class="save-icon">✓</span> 已写入 3DMPS 安装目录<br>' +
      '<code class="save-path">' + escapeHtml(saveResult.saved_path || '') + '</code>' +
      '<span class="save-meta">• ' + (saveResult.bytes || 0) + ' 字节</span>';
  } else {
    el.className = 'save-status save-status-err';
    const msg = (saveResult && saveResult.message) || '未知错误';
    el.innerHTML =
      '<span class="save-icon">✗</span> 写入 3DMPS 安装目录失败: ' + escapeHtml(msg);
  }
  return el;
}

// ============================================================
// 卡片编辑弹窗 —— 美观的可视化编辑页
// ============================================================
//
// 候选卡片右上角的小编辑按钮会调到这里。弹窗里:
//   - 顶部展示当前卡片摘要(标题 / 文件名 / 置信度 / 匹配理由)
//   - 表单只改 filename,标题从最终文件名自动派生
//   - 从 /api/template/xml 加载真实 XML,展示分组结构预览(可视化树)
//   - 分组树支持:点击节点改名 / 点击参数值改值 / +子分组 / +参数 / 删除
//   - 保存时只把当前树状态暂存到卡片内存;真正写入模板库发生在外层“写入模板库并加载”。

// 已知枚举字段(从 template_core.js 同步过来),key 一致就用 <select> 编辑
const ENUM_FIELDS = {
  '依赖方向': ['任意方向', '从父', '主方向1', '主方向2', '主方向3', '主方向4', '主方向5', '主方向6', '外圆加工方向', '多外圆加工方向', '六面方向', '无可行方向', '无可行加工方向', '未配置'],
  '依赖方式': ['无', '相同', '相反', '平行', '平行且在同侧', '平行且在反侧', '垂直', '不平行', '接近', '接近反向', '相同或接近', '相反或接近反向', '与坐标轴方向不平行'],
  '主轴线上特征': ['无关', '是', '不是'],
  '一般轴线上特征': ['无关', '是', '不是'],
  '是否按用户规则排工序': ['是', '否', '不是']
};

// 添加参数时推荐的 key 列表
const FEATURE_PARAM_KEY = '特征选择';
const SUGGESTED_PARAM_KEYS = ['依赖方向', '依赖方式', FEATURE_PARAM_KEY, '主轴线上特征', '一般轴线上特征', '是否按用户规则排工序', '工序说明'];
let _featureTemplateCatalogPromise = null;
let _featureTemplateCatalog = null;

// 树节点 id 自增计数
let _editTreeNodeIdCounter = 0;
function nextEditTreeNodeId() { return 'tn-' + (++_editTreeNodeIdCounter); }

/** XML 文本属性转义 */
function xmlAttrEscape(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * 把 XML 解析成可变的树结构。
 * 节点结构: { id, name, isRoot, params: [{k, v}], children: [...] }
 */
function buildEditTreeFromXml(xml) {
  if (!xml) return makeDefaultRootTree();
  let doc;
  try {
    doc = new DOMParser().parseFromString(xml, 'text/xml');
  } catch (err) {
    return makeDefaultRootTree();
  }
  if (doc.querySelector('parsererror')) return makeDefaultRootTree();

  const partItem = doc.querySelector('Item[type="Part"]') || doc.querySelector('Item[type="part"]');
  if (!partItem) return makeDefaultRootTree();

  return readEditTreeNode(partItem, true);
}

function makeDefaultRootTree() {
  return { id: nextEditTreeNodeId(), name: 'Part', isRoot: true, params: [], children: [] };
}

function readEditTreeNode(item, isRoot) {
  const paramsEl = item.querySelector(':scope > Params');
  const params = [];
  let name;
  if (isRoot) {
    name = 'Part';
  } else {
    const nameField = paramsEl ? paramsEl.querySelector('param[name="名称"]') : null;
    name = (nameField ? nameField.getAttribute('value') : item.getAttribute('name')) || '未命名';
    name = String(name).trim() || '未命名';
  }
  if (paramsEl) {
    Array.from(paramsEl.querySelectorAll(':scope > param')).forEach((p) => {
      const k = (p.getAttribute('name') || '').trim();
      if (!k) return;
      // 名称 在 root 时跳过,在子节点时跳过(它已经被存到 node.name)
      if (k === '名称') return;
      params.push({ k, v: p.getAttribute('value') || '' });
    });
  }
  const children = [];
  Array.from(item.children).forEach((child) => {
    if (child.tagName === 'Item' && child.getAttribute('type') === 'Group') {
      children.push(readEditTreeNode(child, false));
    }
  });
  return { id: nextEditTreeNodeId(), name, isRoot, params, children };
}

/** 根据 path 数组取节点(path 里的数字是逐级 children 下标) */
function findEditNode(tree, path) {
  let node = tree;
  for (const idx of path) {
    if (!node || !node.children || !node.children[idx]) return null;
    node = node.children[idx];
  }
  return node;
}

/** 树操作:加子分组 */
function editTreeAddChild(tree, path) {
  const parent = findEditNode(tree, path);
  if (!parent) return null;
  const child = {
    id: nextEditTreeNodeId(),
    name: '新分组',
    isRoot: false,
    params: [
      { k: '依赖方向', v: '从父' },
      { k: '依赖方式', v: '无' }
    ],
    children: []
  };
  parent.children.push(child);
  return child;
}

/** 树操作:删除节点(根不可删) */
function editTreeDeleteNode(tree, path) {
  if (!path.length) return false;
  const parent = findEditNode(tree, path.slice(0, -1));
  if (!parent) return false;
  parent.children.splice(path[path.length - 1], 1);
  return true;
}

/** 树操作:加/更新参数 */
function editTreeSetParam(tree, path, key, value) {
  const node = findEditNode(tree, path);
  if (!node) return;
  const exist = node.params.find((p) => p.k === key);
  if (exist) exist.v = value;
  else node.params.push({ k: key, v: value || '' });
}

/** 树操作:删除参数 */
function editTreeDeleteParam(tree, path, key) {
  const node = findEditNode(tree, path);
  if (!node) return;
  const idx = node.params.findIndex((p) => p.k === key);
  if (idx >= 0) node.params.splice(idx, 1);
}

/** 树操作:重命名 */
function editTreeRenameNode(tree, path, newName) {
  const node = findEditNode(tree, path);
  if (!node) return;
  node.name = String(newName || '').trim() || '未命名';
}

/** 树操作:改参数值 */
function editTreeSetParamValue(tree, path, key, newValue) {
  const node = findEditNode(tree, path);
  if (!node) return;
  const p = node.params.find((p) => p.k === key);
  if (p) p.v = newValue;
}

/**
 * 树操作:把 sourcePath 指向的节点挪到 targetParentPath 的 children 里 targetIndex 位置。
 *   - 根节点不让挪(不能让 Part 跑到别人下面去)
 *   - 同 parent 时调整 targetIndex,避免索引错位
 *   - 成功返回 true,失败返回 false
 */
function editTreeMoveNode(tree, sourcePath, targetParentPath, targetIndex) {
  if (!Array.isArray(sourcePath) || sourcePath.length === 0) return false;
  const sourceParent = findEditNode(tree, sourcePath.slice(0, -1));
  if (!sourceParent) return false;
  const targetParent = findEditNode(tree, targetParentPath);
  if (!targetParent) return false;
  const sourceIdx = sourcePath[sourcePath.length - 1];
  if (sourceIdx < 0 || sourceIdx >= sourceParent.children.length) return false;
  const [moved] = sourceParent.children.splice(sourceIdx, 1);
  // 同 parent 内挪动时,删除会让后面的索引前移
  let insertAt = targetIndex;
  if (sourceParent === targetParent && sourceIdx < targetIndex) insertAt -= 1;
  if (insertAt < 0) insertAt = 0;
  if (insertAt > targetParent.children.length) insertAt = targetParent.children.length;
  targetParent.children.splice(insertAt, 0, moved);
  return true;
}

/** 树操作:统计节点总数(用于 badge 显示) */
function countEditTreeDescendants(node) {
  let n = 0;
  for (const c of node.children || []) n += 1 + countEditTreeDescendants(c);
  return n;
}

function editTreeCollapsedStore(ctx) {
  if (!ctx) return null;
  if (!ctx._collapsedNodes) ctx._collapsedNodes = new Map();
  return ctx._collapsedNodes;
}

function editTreeDefaultNodeCollapsed(node, depth, ctx) {
  const defaultDepth = (ctx && typeof ctx.defaultCollapsedDepth === 'number') ? ctx.defaultCollapsedDepth : 99;
  return Boolean(node && !node.isRoot && defaultDepth < 99 && depth >= defaultDepth);
}

function editTreeResolveNodeCollapsed(node, depth, ctx) {
  const store = ctx && ctx._collapsedNodes;
  const key = node && node.id ? String(node.id) : '';
  if (store && key && store.has(key)) return Boolean(store.get(key));
  return editTreeDefaultNodeCollapsed(node, depth, ctx);
}

function editTreeSetNodeCollapsed(ctx, node, collapsed) {
  if (!node || !node.id || node.isRoot) return;
  if (!editTreeCollapsedStore(ctx)) return;
  ctx._collapsedNodes.set(String(node.id), Boolean(collapsed));
}

function editTreeSetAllNodeCollapsed(ctx, node, collapsed) {
  if (!node) return;
  editTreeSetNodeCollapsed(ctx, node, collapsed);
  (node.children || []).forEach((child) => editTreeSetAllNodeCollapsed(ctx, child, collapsed));
}

function editTreeSetRootChildrenCollapsed(ctx, tree, collapsed) {
  if (!tree || !tree.children) return;
  tree.children.forEach((child) => editTreeSetNodeCollapsed(ctx, child, collapsed));
}

/**
 * 把树重新生成为 Part/Group 区块的 XML 字符串。
 * 缩进按 4 空格,跟 3DMPS 的常见风格保持一致。
 */
function buildEditTreeXml(tree, rootOpenTag) {
  const lines = [];
  function emitNode(node, indent) {
    if (node.isRoot) {
      lines.push(indent + (rootOpenTag || '<Item type="Part" filename="" >'));
    } else {
      lines.push(indent + '<Item type="Group" stageOrders="" sourceIds="">');
    }
    lines.push(indent + '    <Params>');
    if (!node.isRoot) {
      lines.push(indent + '        <param name="名称" value="' + xmlAttrEscape(node.name) + '" />');
    }
    for (const p of node.params) {
      lines.push(indent + '        <param name="' + xmlAttrEscape(p.k) + '" value="' + xmlAttrEscape(p.v) + '" />');
    }
    lines.push(indent + '    </Params>');
    for (const c of node.children) {
      emitNode(c, indent + '    ');
    }
    lines.push(indent + '</Item>');
  }
  emitNode(tree, '');
  return lines.join('\n');
}

/**
 * 找到原 XML 里 <Item type="Part" ...>...</Item> 的范围,替换成新树生成的 XML。
 * 用括号深度匹配,保证替换的边界正确。
 */
function spliceEditTreeIntoXml(originalXml, tree) {
  if (!originalXml) return buildEditTreeXml(tree);
  const startRe = /<Item\b(?=[^>]*\btype\s*=\s*["']Part["'])[^>]*>/;
  const m = startRe.exec(originalXml);
  if (!m) return buildEditTreeXml(tree);
  const startIdx = m.index;
  let depth = 1;
  const tokenRe = /<Item\b[^>]*>|<\/Item>/g;
  tokenRe.lastIndex = startIdx + m[0].length;
  let mm;
  while ((mm = tokenRe.exec(originalXml))) {
    if (mm[0].startsWith('</Item')) {
      depth -= 1;
      if (depth === 0) {
        const endIdx = tokenRe.lastIndex;
        return originalXml.slice(0, startIdx) + buildEditTreeXml(tree, m[0]) + originalXml.slice(endIdx);
      }
    } else if (!mm[0].endsWith('/>')) {
      depth += 1;
    }
  }
  return originalXml;
}

/**
 * 把后端返回的候选对象 (option) 拍平成编辑弹窗用的初始数据。
 */
function normalizeOptForEditor(opt) {
  const filename = String(opt.filename || opt.subtitle || '').trim();
  const title = filename
    ? deriveDisplayNameFromFilename(filename)
    : (opt.title || opt.displayName || opt.templateName || opt.templateId || '(未命名)');
  const templateId = opt.templateId || opt.id || '';
  const meta = opt.meta || {};
  return {
    title: String(title),
    filename: String(filename),
    templateId: String(templateId),
    templateXml: String(opt.templateXml || ''),
    onSave: typeof opt.onSave === 'function' ? opt.onSave : null,
    hideConfidence: Boolean(opt.hideConfidence),
    compactStructureOnly: Boolean(opt.compactStructureOnly),
    groupCount: meta.groupCount || 0,
    depth: meta.depth || 0,
    confidence: Number(opt.confidence || 0)
  };
}

/**
 * 把可变的树状态渲染到容器里。
 *   - 每次 treeState 变化时调用 ctx.onChange(),它应当 rerender 整个 tree
 *   - 行内交互(改名 / 改参数值 / 加子分组 / 加参数 / 删除)都直接修改 treeState,
 *     然后触发 rerender,无需重新解析 XML。
 *
 * @param {HTMLElement} container 渲染目标容器
 * @param {object} tree           树状态根节点
 * @param {object} ctx            { onChange, defaultCollapsedDepth }
 */
function renderEditTree(container, tree, ctx) {
  if (!container) return;
  ctx = ctx || {};
  container.innerHTML = '';
  if (!tree) {
    container.innerHTML = '<div class="edit-tree-empty">没有可编辑的分组结构。</div>';
    return;
  }
  // 把当前 container 和 tree 挂到 ctx 上,方便拖拽辅助函数定位清理范围 + 调用 moveNode
  ctx._ownerContainer = container;
  ctx._treeRef = tree;
  container.appendChild(buildEditNodeEl(tree, 0, [], tree, ctx));
}

function buildEditChipRow(params, node, path, tree, ctx) {
  const row = document.createElement('div');
  row.className = 'edit-tree-chip-row';
  const chips = document.createElement('span');
  chips.className = 'edit-tree-chips';
  params.forEach((p) => {
    chips.appendChild(buildEditChipEl(p, node, path, tree, ctx));
  });
  row.appendChild(chips);
  return row;
}

function appendChipRow(head, params, node, path, tree, ctx) {
  const existing = head.querySelector('.edit-tree-chip-row');
  if (existing) existing.remove();
  head.appendChild(buildEditChipRow(params, node, path, tree, ctx));
}

/** 把单个节点(连同子节点)渲染成 DOM,递归挂子节点。 */
function buildEditNodeEl(node, depth, path, tree, ctx) {
  const wrap = document.createElement('div');
  wrap.className = 'edit-tree-node' + (node.isRoot ? ' is-root' : '');
  wrap.setAttribute('data-node-id', node.id || '');
  wrap.setAttribute('data-depth', String(depth));

  const hasChildren = node.children && node.children.length > 0;
  if (hasChildren && editTreeResolveNodeCollapsed(node, depth, ctx)) {
    wrap.classList.add('is-collapsed');
  }

  // header 行
  const head = document.createElement('div');
  head.className = 'edit-tree-row';
  head.style.setProperty('--tree-depth', String(depth));
  const mainRow = document.createElement('div');
  mainRow.className = 'edit-tree-row-main';

  // 折叠箭头(无子节点就放一个占位空白)
  const toggle = document.createElement('span');
  toggle.className = 'edit-tree-toggle' + (hasChildren ? '' : ' is-leaf');
  toggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>';
  if (hasChildren) {
    toggle.setAttribute('role', 'button');
    toggle.setAttribute('aria-label', '展开/折叠');
    toggle.tabIndex = 0;
    toggle.addEventListener('click', function(ev) {
      ev.stopPropagation();
      const collapsed = !wrap.classList.contains('is-collapsed');
      editTreeSetNodeCollapsed(ctx, node, collapsed);
      wrap.classList.toggle('is-collapsed', collapsed);
    });
    toggle.addEventListener('keydown', function(ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle.click(); }
    });
  }
  mainRow.appendChild(toggle);

  // 节点图标
  const icon = document.createElement('span');
  icon.className = 'edit-tree-icon' + (node.isRoot ? ' is-root' : '');
  icon.innerHTML = node.isRoot
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="3" y1="9" x2="21" y2="9"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h18M3 12h18M3 17h18"/></svg>';
  mainRow.appendChild(icon);

  // 节点名 —— 根节点不让改名,其它点击进入改名模式
  const name = document.createElement('span');
  name.className = 'edit-tree-name' + (node.isRoot ? ' is-root-name' : ' is-editable');
  name.textContent = node.name;
  if (!node.isRoot) {
    name.title = '点击修改名称';
    name.addEventListener('click', function(ev) {
      ev.stopPropagation();
      enterEditNameMode(name, node, path, tree, ctx);
    });
  }
  mainRow.appendChild(name);

  // 后代计数 badge(包含直接子节点和所有后代)
  const descCount = countEditTreeDescendants(node);
  if (descCount > 0) {
    const count = document.createElement('span');
    count.className = 'edit-tree-count';
    count.textContent = descCount + ' 项';
    count.title = '子节点 + 后代总数';
    mainRow.appendChild(count);
  }

  // 参数区:默认折叠,只露一个「▸ N 属性」按钮,点击后再展开所有 chips。
  // 折叠状态记在 ctx._expandedParams 上,跨 rerender 保留用户的选择。
  if (node.params && node.params.length) {
    const expanded = ctx._expandedParams && ctx._expandedParams.has(node.id);
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'edit-tree-params-toggle' + (expanded ? ' is-expanded' : '');
    toggleBtn.setAttribute('data-params-toggle-for', node.id || '');
    toggleBtn.innerHTML = '<span class="edit-tree-params-toggle-arrow">' + (expanded ? '▾' : '▸') + '</span>' +
      '<span class="edit-tree-params-toggle-text">' + node.params.length + ' 属性</span>';
    toggleBtn.title = expanded ? '收起属性' : '展开属性';
    toggleBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!ctx._expandedParams) ctx._expandedParams = new Set();
      const wasExpanded = ctx._expandedParams.has(node.id);
      if (wasExpanded) {
        ctx._expandedParams.delete(node.id);
      } else {
        ctx._expandedParams.add(node.id);
      }
      // 行内更新 chips 可见性,避免全树重渲丢失用户的折叠状态
      const existingChipRow = head.querySelector('.edit-tree-chip-row');
      const arrow = toggleBtn.querySelector('.edit-tree-params-toggle-arrow');
      if (wasExpanded) {
        if (existingChipRow) existingChipRow.remove();
        toggleBtn.classList.remove('is-expanded');
        if (arrow) arrow.textContent = '▸';
        toggleBtn.title = '展开属性';
      } else {
        appendChipRow(head, node.params, node, path, tree, ctx);
        // 插在 toggleBtn 之后(视觉上 chips 在 toggle 右侧);如果没有 tools,直接 append
        toggleBtn.classList.add('is-expanded');
        if (arrow) arrow.textContent = '▾';
        toggleBtn.title = '收起属性';
      }
      // 不调 onChange,form.xml 等用户点保存时再生成(节省一次序列化和重渲)
    });
    mainRow.appendChild(toggleBtn);

    // 默认折叠:不渲染 chips;只有显式展开时才渲染
  }

  // 行内 hover 工具按钮
  const tools = document.createElement('span');
  tools.className = 'edit-tree-row-tools';
  const addChildBtn = makeEditToolBtn('add-child', '+ 子分组', function(ev) {
    ev.stopPropagation();
    editTreeAddChild(tree, path);
    ctx.onChange && ctx.onChange();
  });
  tools.appendChild(addChildBtn);
  if (!node.isRoot) {
    const addParamBtn = makeEditToolBtn('add-param', '+ 参数', function(ev) {
      ev.stopPropagation();
      openAddParamPopover(addParamBtn, node, path, tree, ctx);
    });
    tools.appendChild(addParamBtn);
    const delBtn = makeEditToolBtn('delete', '删除', function(ev) {
      ev.stopPropagation();
      editTreeDeleteNode(tree, path);
      ctx.onChange && ctx.onChange();
    });
    tools.appendChild(delBtn);
  }
  mainRow.appendChild(tools);
  head.appendChild(mainRow);
  if (node.params && node.params.length && ctx._expandedParams && ctx._expandedParams.has(node.id)) {
    appendChipRow(head, node.params, node, path, tree, ctx);
  }

  // 拖拽支持:纯鼠标事件 + 自定义拖拽图像(避免 HTML5 native drag 在 CEF 里水土不服)。
  //   - mousedown 在 icon 上启动「潜在拖拽」(还没真正开始,等鼠标移动超过阈值才进入拖拽态)
  //   - 进入拖拽态后:克隆整行作为跟随鼠标的浮动预览 + 在目标 row 上显示 drop 指示
  //   - mouseup 时如果拖拽已开始且落在合法目标上,执行 moveNode + 重渲
  //   - 跨 row 的拖拽状态共享在 ctx._drag 上,避免每个 row 各自闭包浪费
  if (!node.isRoot) {
    icon.classList.add('is-drag-handle');
    icon.title = '按住拖动可调整同级顺序';

    // 把 path / depth 写到 head 上,方便后续用 elementsFromPoint 找到目标时直接读到 path
    head.setAttribute('data-drag-path', JSON.stringify(path));
    head.setAttribute('data-drag-depth', String(depth));

    icon.addEventListener('mousedown', function(ev) {
      if (ev.button !== 0) return; // 只响应左键
      ev.preventDefault();
      ev.stopPropagation();

      // 启动「潜在拖拽」:记录起始状态,挂全局监听
      const state = {
        started: false,
        threshold: 4,
        startX: ev.clientX,
        startY: ev.clientY,
        path: path,
        depth: depth,
        sourceHead: head,
        clone: null,
        target: null
      };
      ctx._drag = state;

      const onMove = function(e) { handleDragMove(e, state, ctx); };
      const onUp = function(e) { handleDragUp(e, state, ctx, onMove, onUp); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      state._onMove = onMove;
      state._onUp = onUp;
    });
  }

  wrap.appendChild(head);

  // 子节点
  if (hasChildren) {
    const kids = document.createElement('div');
    kids.className = 'edit-tree-children';
    node.children.forEach((c, i) => {
      const childEl = buildEditNodeEl(c, depth + 1, path.concat(i), tree, ctx);
      if (i === node.children.length - 1) childEl.classList.add('is-last');
      kids.appendChild(childEl);
    });
    wrap.appendChild(kids);
  }

  return wrap;
}

function makeEditToolBtn(kind, label, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'edit-tree-row-tool edit-tree-row-tool-' + kind;
  b.textContent = label;
  b.title = label;
  b.addEventListener('click', function(ev) {
    ev.preventDefault();
    onClick(ev);
  });
  return b;
}

function buildEditChipEl(param, node, path, tree, ctx) {
  const c = document.createElement('span');
  c.className = 'edit-tree-chip' + paramChipClass(param.k);
  c.setAttribute('data-param-key', param.k);

  const k = document.createElement('span');
  k.className = 'edit-tree-chip-k';
  k.textContent = param.k;
  c.appendChild(k);

  const v = document.createElement('span');
  v.className = 'edit-tree-chip-v is-editable';
  v.textContent = param.v || '—';
  v.title = '点击修改值';
  v.addEventListener('click', function(ev) {
    ev.stopPropagation();
    enterEditChipValueMode(v, param, node, path, tree, ctx);
  });
  c.appendChild(v);

  // 删除按钮(右侧 ×,hover 出现)
  const x = document.createElement('button');
  x.type = 'button';
  x.className = 'edit-tree-chip-x';
  x.textContent = '×';
  x.title = '删除该参数';
  x.addEventListener('click', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    editTreeDeleteParam(tree, path, param.k);
    ctx.onChange && ctx.onChange();
  });
  c.appendChild(x);

  return c;
}

/** 点击名字 → 把它替换成 input,Enter 提交 / Esc 取消 / blur 也提交 */
function enterEditNameMode(nameEl, node, path, tree, ctx) {
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'edit-tree-name-input';
  input.value = node.name || '';
  input.maxLength = 40;
  syncInlineEditInputSize(nameEl, input);
  nameEl.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = function(commit) {
    if (done) return;
    done = true;
    if (commit) {
      editTreeRenameNode(tree, path, input.value);
    }
    ctx.onChange && ctx.onChange();
  };
  input.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', function() { finish(true); });
}


function syncInlineEditInputSize(sourceEl, input) {
  if (!sourceEl || !input) return;
  const rect = sourceEl.getBoundingClientRect();
  const computed = window.getComputedStyle ? window.getComputedStyle(sourceEl) : null;
  const width = Math.max(1, Math.ceil(rect.width || sourceEl.offsetWidth || 1));
  const height = Math.max(1, Math.ceil(rect.height || sourceEl.offsetHeight || 1));
  input.style.setProperty('--inline-editor-width', width + 'px');
  input.style.height = height + 'px';
  if (computed) {
    input.style.lineHeight = computed.lineHeight;
    input.style.fontFamily = computed.fontFamily;
    input.style.fontSize = computed.fontSize;
    input.style.fontWeight = computed.fontWeight;
    input.style.paddingTop = computed.paddingTop;
    input.style.paddingRight = computed.paddingRight;
    input.style.paddingBottom = computed.paddingBottom;
    input.style.paddingLeft = computed.paddingLeft;
  }
}

function splitFeatureSelectionValue(value) {
  return String(value || '')
    .split(/[,，]/)
    .map(function(item) { return item.trim(); })
    .filter(Boolean);
}

function collectFeatureLeafNames(nodeOrNodes) {
  const leaves = [];
  const nodes = Array.isArray(nodeOrNodes) ? nodeOrNodes : [nodeOrNodes];
  function walk(item) {
    if (!item || !item.name) return;
    const children = Array.isArray(item.children) ? item.children : [];
    if (!children.length) {
      if (!leaves.includes(item.name)) leaves.push(item.name);
      return;
    }
    children.forEach(walk);
  }
  nodes.forEach(walk);
  return leaves;
}

function buildFeatureCatalogMaps(catalog) {
  const nodeByName = new Map();
  const tree = Array.isArray(catalog && catalog.tree) ? catalog.tree : [];
  function walk(item) {
    if (!item || !item.name) return;
    if (!nodeByName.has(item.name)) nodeByName.set(item.name, item);
    (item.children || []).forEach(walk);
  }
  tree.forEach(walk);
  const leafOrder = Array.isArray(catalog && catalog.leafNames) && catalog.leafNames.length
    ? catalog.leafNames.slice()
    : collectFeatureLeafNames(tree);
  return { nodeByName: nodeByName, leafSet: new Set(leafOrder), leafOrder: leafOrder };
}

function normalizeFeatureSelectionValue(value, catalog) {
  const maps = buildFeatureCatalogMaps(catalog);
  const selected = new Set();
  const unknownValues = [];
  splitFeatureSelectionValue(value).forEach(function(token) {
    if (maps.leafSet.has(token)) {
      selected.add(token);
      return;
    }
    const featureNode = maps.nodeByName.get(token);
    if (featureNode) {
      collectFeatureLeafNames(featureNode).forEach(function(leafName) {
        selected.add(leafName);
      });
      return;
    }
    if (!unknownValues.includes(token)) unknownValues.push(token);
  });
  return { selected: selected, unknownValues: unknownValues };
}

function serializeFeatureSelection(selectedLeafNames, unknownValues, catalog) {
  const selected = selectedLeafNames instanceof Set ? selectedLeafNames : new Set(selectedLeafNames || []);
  const maps = buildFeatureCatalogMaps(catalog);
  const values = [];
  maps.leafOrder.forEach(function(featureName) {
    if (selected.has(featureName) && !values.includes(featureName)) values.push(featureName);
  });
  (unknownValues || []).forEach(function(featureName) {
    if (featureName && !values.includes(featureName)) values.push(featureName);
  });
  return values.join(',');
}

function loadFeatureTemplateCatalog() {
  if (_featureTemplateCatalog) return Promise.resolve(_featureTemplateCatalog);
  if (_featureTemplateCatalogPromise) return _featureTemplateCatalogPromise;
  _featureTemplateCatalogPromise = new Promise(function(resolve, reject) {
    const fail = function(err) {
      _featureTemplateCatalogPromise = null;
      reject(err);
    };
    requestJson('GET', '/api/feature-template', null, function(data) {
      const result = data && data.result ? data.result : null;
      if (data && data.status === 'success' && result && Array.isArray(result.tree)) {
        _featureTemplateCatalog = result;
        resolve(result);
      } else {
        fail(new Error((data && data.message) || 'FeatureTemplate.xml 加载失败'));
      }
    }, function(err) {
      fail(err);
    }, 30000);
  });
  return _featureTemplateCatalogPromise;
}

function positionFeatureSelectPopover(pop, anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const popW = Math.min(360, Math.max(300, window.innerWidth - 16));
  pop.style.position = 'fixed';
  pop.style.width = popW + 'px';
  let left = rect.left;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - 8 - popW;
  if (left < 8) left = 8;
  let top = rect.bottom + 6;
  const expectedH = 360;
  if (top + expectedH > window.innerHeight - 8 && rect.top > expectedH) {
    top = rect.top - expectedH - 6;
  }
  pop.style.left = left + 'px';
  pop.style.top = Math.max(8, top) + 'px';
}

function buildFeatureSelectNode(featureNode, state, depth, rerender) {
  const wrap = document.createElement('div');
  wrap.className = 'feature-select-node';
  wrap.style.setProperty('--feature-depth', String(depth || 0));

  const row = document.createElement('label');
  row.className = 'feature-select-row';

  const input = document.createElement('input');
  input.type = 'checkbox';
  const leafNames = collectFeatureLeafNames(featureNode);
  const selectedCount = leafNames.filter(function(name) { return state.selected.has(name); }).length;
  input.checked = leafNames.length > 0 && selectedCount === leafNames.length;
  input.indeterminate = selectedCount > 0 && selectedCount < leafNames.length;
  input.addEventListener('change', function(ev) {
    ev.stopPropagation();
    const checked = input.checked;
    leafNames.forEach(function(leafName) {
      if (checked) state.selected.add(leafName);
      else state.selected.delete(leafName);
    });
    rerender();
  });
  row.appendChild(input);

  const name = document.createElement('span');
  name.className = 'feature-select-name';
  name.textContent = featureNode.name;
  row.appendChild(name);

  const children = Array.isArray(featureNode.children) ? featureNode.children : [];
  if (children.length) {
    const count = document.createElement('span');
    count.className = 'feature-select-count';
    count.textContent = leafNames.length + ' 项';
    row.appendChild(count);
  }

  wrap.appendChild(row);
  if (children.length) {
    const kids = document.createElement('div');
    kids.className = 'feature-select-children';
    children.forEach(function(child) {
      kids.appendChild(buildFeatureSelectNode(child, state, depth + 1, rerender));
    });
    wrap.appendChild(kids);
  }
  return wrap;
}

function getFeatureSelectScrollTop(pop) {
  const treeEl = pop && pop.querySelector ? pop.querySelector('.feature-select-tree') : null;
  return treeEl ? treeEl.scrollTop : 0;
}

function restoreFeatureSelectScrollTop(treeEl, scrollTop) {
  if (!treeEl || !scrollTop) return;
  treeEl.scrollTop = scrollTop;
  // 勾选会重绘整棵树，CEF 有时会在布局后一帧再次修正滚动位置。
  if (typeof window !== 'undefined' && window.requestAnimationFrame) {
    window.requestAnimationFrame(function() {
      treeEl.scrollTop = scrollTop;
    });
  }
}

function renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close) {
  const previousTreeScrollTop = getFeatureSelectScrollTop(pop);
  pop.innerHTML = '';

  const head = document.createElement('div');
  head.className = 'feature-select-head';
  head.textContent = '特征选择';
  pop.appendChild(head);

  if (!state.catalog) {
    const loading = document.createElement('div');
    loading.className = 'feature-select-loading';
    loading.textContent = state.error || '正在加载 FeatureTemplate.xml...';
    pop.appendChild(loading);
    return;
  }

  if (state.unknownValues.length) {
    const unknown = document.createElement('div');
    unknown.className = 'feature-select-unknown';
    unknown.textContent = '保留未识别项: ' + state.unknownValues.join(', ');
    pop.appendChild(unknown);
  }

  const treeEl = document.createElement('div');
  treeEl.className = 'feature-select-tree';
  (state.catalog.tree || []).forEach(function(featureNode) {
    treeEl.appendChild(buildFeatureSelectNode(featureNode, state, 0, function() {
      renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close);
    }));
  });
  pop.appendChild(treeEl);
  restoreFeatureSelectScrollTop(treeEl, previousTreeScrollTop);

  const actions = document.createElement('div');
  actions.className = 'feature-select-actions';

  const summary = document.createElement('span');
  summary.className = 'feature-select-summary';
  summary.textContent = '已选 ' + state.selected.size + ' 项';
  actions.appendChild(summary);

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'feature-select-clear';
  clearBtn.textContent = '清空';
  clearBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    state.selected.clear();
    renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close);
  });
  actions.appendChild(clearBtn);

  const okBtn = document.createElement('button');
  okBtn.type = 'button';
  okBtn.className = 'feature-select-confirm';
  okBtn.textContent = '确定';
  okBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    editTreeSetParamValue(
      tree,
      path,
      param.k,
      serializeFeatureSelection(state.selected, state.unknownValues, state.catalog)
    );
    ctx.onChange && ctx.onChange();
    close();
  });
  actions.appendChild(okBtn);

  pop.appendChild(actions);
}

function openFeatureSelectDropdown(vEl, param, node, path, tree, ctx) {
  document.querySelectorAll('.feature-select-popover').forEach(function(el) { el.remove(); });

  const pop = document.createElement('div');
  pop.className = 'feature-select-popover';
  const state = {
    catalog: null,
    selected: new Set(),
    unknownValues: [],
    error: ''
  };

  function cleanup() {
    document.removeEventListener('click', onDocClick, true);
    document.removeEventListener('keydown', onDocKey, true);
  }
  function close() {
    cleanup();
    pop.remove();
  }
  const onDocClick = function(ev) {
    if (!pop.contains(ev.target) && ev.target !== vEl) close();
  };
  const onDocKey = function(ev) {
    if (ev.key === 'Escape') close();
  };

  document.body.appendChild(pop);
  positionFeatureSelectPopover(pop, vEl);
  renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close);

  loadFeatureTemplateCatalog().then(function(catalog) {
    state.catalog = catalog;
    const normalized = normalizeFeatureSelectionValue(param.v, catalog);
    state.selected = normalized.selected;
    state.unknownValues = normalized.unknownValues;
    renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close);
  }).catch(function(err) {
    state.error = '特征目录加载失败: ' + (err && err.message ? err.message : String(err));
    renderFeatureSelectDropdown(pop, state, param, node, path, tree, ctx, close);
  });

  setTimeout(function() {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onDocKey, true);
  }, 0);
}

/** 点击 chip 的 value → 改成 input 或 select(枚举字段),Enter / blur 提交 */
function enterEditChipValueMode(vEl, param, node, path, tree, ctx) {
  if (param.k === FEATURE_PARAM_KEY) {
    openFeatureSelectDropdown(vEl, param, node, path, tree, ctx);
    return;
  }
  const enumValues = ENUM_FIELDS[param.k];
  let input;
  let isSelect = false;
  if (enumValues) {
    isSelect = true;
    input = document.createElement('select');
    input.className = 'edit-tree-chip-v-input';
    enumValues.forEach((opt) => {
      const o = document.createElement('option');
      o.value = opt;
      o.textContent = opt;
      if (opt === param.v) o.selected = true;
      input.appendChild(o);
    });
  } else {
    input = document.createElement('input');
    input.type = 'text';
    input.className = 'edit-tree-chip-v-input';
    input.value = param.v || '';
  }
  syncInlineEditInputSize(vEl, input);
  vEl.replaceWith(input);
  input.focus();
  if (!isSelect) input.select();
  let done = false;
  const finish = function(commit) {
    if (done) return;
    done = true;
    if (commit) {
      editTreeSetParamValue(tree, path, param.k, input.value);
    }
    ctx.onChange && ctx.onChange();
  };
  input.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', function() { finish(true); });
}

/**
 * 弹出「新增参数」的浮层:
 *   - 推荐列表:从 SUGGESTED_PARAM_KEYS 里挑出当前节点还没有的 key
 *   - 自定义 key:输入框 + 「添加」按钮
 * 浮层定位到触发按钮下方,点外部 / Esc 关闭。
 */
function openAddParamPopover(anchorBtn, node, path, tree, ctx) {
  document.querySelectorAll('.edit-param-popover').forEach((el) => el.remove());

  const pop = document.createElement('div');
  pop.className = 'edit-param-popover';

  const title = document.createElement('div');
  title.className = 'edit-param-popover-title';
  title.textContent = '新增参数到「' + (node.name || '未命名') + '」';
  pop.appendChild(title);

  const existingKeys = new Set((node.params || []).map((p) => p.k));
  const suggested = SUGGESTED_PARAM_KEYS.filter((k) => !existingKeys.has(k));

  if (suggested.length) {
    const list = document.createElement('div');
    list.className = 'edit-param-popover-list';
    suggested.forEach((k) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'edit-param-popover-item';
      const def = k === FEATURE_PARAM_KEY ? '' : (ENUM_FIELDS[k] ? ENUM_FIELDS[k][0] : '');
      btn.innerHTML = '<span class="edit-param-popover-k">' + escapeHtml(k) + '</span>' +
        (def ? '<span class="edit-param-popover-d">→ ' + escapeHtml(def) + '</span>' : '<span class="edit-param-popover-d edit-param-popover-d-empty">(空)</span>');
      btn.title = '添加「' + k + '」参数' + (def ? ',默认 ' + def : '');
      btn.addEventListener('click', function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        editTreeSetParam(tree, path, k, def);
        pop.remove();
        ctx.onChange && ctx.onChange();
      });
      list.appendChild(btn);
    });
    pop.appendChild(list);
  } else {
    const empty = document.createElement('div');
    empty.className = 'edit-param-popover-empty';
    empty.textContent = '常用参数已全部添加,可直接在下方输入自定义 key';
    pop.appendChild(empty);
  }

  const custom = document.createElement('div');
  custom.className = 'edit-param-popover-custom';
  const customInput = document.createElement('input');
  customInput.type = 'text';
  customInput.placeholder = '或输入自定义参数名...';
  custom.appendChild(customInput);
  const customBtn = document.createElement('button');
  customBtn.type = 'button';
  customBtn.textContent = '添加';
  customBtn.className = 'edit-param-popover-add';
  custom.appendChild(customBtn);
  pop.appendChild(custom);

  const submitCustom = function() {
    const k = customInput.value.trim();
    if (!k) return;
    if (existingKeys.has(k)) {
      customInput.value = '';
      customInput.placeholder = '参数名已存在,请换一个';
      return;
    }
    editTreeSetParam(tree, path, k, '');
    pop.remove();
    ctx.onChange && ctx.onChange();
  };
  customBtn.addEventListener('click', function(ev) { ev.preventDefault(); submitCustom(); });
  customInput.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); submitCustom(); }
    else if (ev.key === 'Escape') { ev.preventDefault(); pop.remove(); }
  });

  document.body.appendChild(pop);
  // 定位:按钮下方,贴近右对齐,避免溢出视口
  const rect = anchorBtn.getBoundingClientRect();
  pop.style.position = 'fixed';
  const popW = 240;
  let left = rect.right - popW;
  if (left < 8) left = 8;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - 8 - popW;
  pop.style.left = left + 'px';
  pop.style.top = (rect.bottom + 6) + 'px';
  setTimeout(function() { customInput.focus(); }, 30);

  // 点击外部 / Esc 关闭
  const onDocClick = function(ev) {
    if (!pop.contains(ev.target) && ev.target !== anchorBtn) {
      pop.remove();
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onDocKey, true);
    }
  };
  const onDocKey = function(ev) {
    if (ev.key === 'Escape') {
      pop.remove();
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onDocKey, true);
    }
  };
  setTimeout(function() {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onDocKey, true);
  }, 0);
}

function paramChipClass(fieldName) {
  if (fieldName === '依赖方向') return ' chip-dir';
  if (fieldName === '依赖方式') return ' chip-mode';
  if (fieldName === FEATURE_PARAM_KEY) return ' chip-feat';
  return '';
}

/** 比较两条 path 数组是否完全相等 */
function arraysEqualPath(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

/** 拖拽时清理所有 row 上的 drop 指示状态 */
function clearAllDropIndicators(ctx) {
  const root = (ctx && ctx._ownerContainer) || document;
  root.querySelectorAll('.edit-tree-row.drop-before, .edit-tree-row.drop-after').forEach((el) => {
    el.classList.remove('drop-before', 'drop-after');
  });
}

/**
 * 自定义拖拽的 mousemove 处理。鼠标超过阈值时进入拖拽态,创建浮动克隆 + 更新目标 row 的指示。
 */
function handleDragMove(ev, state, ctx) {
  if (!state) return;
  const dx = ev.clientX - state.startX;
  const dy = ev.clientY - state.startY;
  if (!state.started) {
    if (Math.abs(dx) < state.threshold && Math.abs(dy) < state.threshold) return;
    state.started = true;
    state.sourceHead.classList.add('is-dragging');
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
    // 创建浮动克隆(克隆整行,去掉工具按钮和 ×,让它看起来更干净)
    const rect = state.sourceHead.getBoundingClientRect();
    const clone = state.sourceHead.cloneNode(true);
    clone.classList.add('edit-tree-drag-clone');
    clone.style.position = 'fixed';
    clone.style.left = (rect.left) + 'px';
    clone.style.top = (rect.top) + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.maxWidth = rect.width + 'px';
    clone.style.background = 'var(--color-surface)';
    clone.style.boxShadow = '0 12px 32px rgba(15, 23, 42, 0.25)';
    clone.style.borderRadius = '10px';
    clone.style.opacity = '0.95';
    clone.style.padding = '6px 10px';
    clone.style.zIndex = '10002';
    clone.style.pointerEvents = 'none';
    clone.querySelectorAll('.edit-tree-row-tools, .edit-tree-chip-x').forEach((el) => el.remove());
    document.body.appendChild(clone);
    state.clone = clone;
    state.offsetX = ev.clientX - rect.left;
    state.offsetY = ev.clientY - rect.top;
  }
  // 更新浮动克隆位置
  if (state.clone) {
    state.clone.style.left = (ev.clientX - state.offsetX) + 'px';
    state.clone.style.top = (ev.clientY - state.offsetY) + 'px';
  }
  // 找到鼠标下的目标 row:必须同 depth + 不是源 row 自己
  const targetRow = findDropTargetRow(ev.clientX, ev.clientY, state);
  clearAllDropIndicators(ctx);
  if (targetRow) {
    const rect = targetRow.getBoundingClientRect();
    const before = (ev.clientY - rect.top) < rect.height / 2;
    targetRow.classList.add(before ? 'drop-before' : 'drop-after');
    try {
      const targetPath = JSON.parse(targetRow.getAttribute('data-drag-path') || '[]');
      state.target = {
        parentPath: targetPath.slice(0, -1),
        index: before ? targetPath[targetPath.length - 1] : targetPath[targetPath.length - 1] + 1
      };
    } catch (e) { state.target = null; }
  } else {
    state.target = null;
  }
}

/**
 * 找到鼠标坐标下方的合法目标 row。同 depth + 不是源 row 自身 + 不能是源 row 的祖先(避免形成环)。
 */
function findDropTargetRow(clientX, clientY, state) {
  // 先把克隆隐藏掉,免得挡在 elementFromPoint 上
  const cloneEl = state.clone;
  let prevPointer = null;
  if (cloneEl) {
    prevPointer = cloneEl.style.pointerEvents;
    cloneEl.style.pointerEvents = 'none';
  }
  const elements = document.elementsFromPoint(clientX, clientY);
  if (cloneEl) cloneEl.style.pointerEvents = prevPointer || 'none';
  for (const el of elements) {
    if (cloneEl && (el === cloneEl || cloneEl.contains(el))) continue;
    const row = el.closest && el.closest('.edit-tree-row[data-drag-depth]');
    if (!row) continue;
    const rowDepth = Number(row.getAttribute('data-drag-depth'));
    if (rowDepth !== state.depth) continue;
    if (row === state.sourceHead) continue;
    if (state.sourceHead.contains(row)) continue;
    return row;
  }
  return null;
}

/**
 * mouseup 收尾:执行 moveNode + 清理
 */
function handleDragUp(ev, state, ctx, onMove, onUp) {
  if (!state) return;
  document.removeEventListener('mousemove', onMove);
  document.removeEventListener('mouseup', onUp);
  document.body.style.userSelect = '';
  document.body.style.cursor = '';
  if (state.clone) state.clone.remove();
  state.sourceHead.classList.remove('is-dragging');
  clearAllDropIndicators(ctx);
  let moved = false;
  if (state.started && state.target) {
    const ok = editTreeMoveNode(ctx && ctx._treeRef, state.path, state.target.parentPath, state.target.index);
    if (ok) {
      moved = true;
      if (ctx && ctx.onChange) ctx.onChange();
    }
  }
  // 清掉 ctx 上的引用,避免下一次拖拽状态泄漏
  if (ctx) {
    if (ctx._drag === state) ctx._drag = null;
  }
  // 阻止 mouseup 继续触发其他点击事件
  if (moved && ev && ev.preventDefault) ev.preventDefault();
}

/**
 * 打开「分组结构 — 放大编辑视图」的全屏弹窗。
 *   - 跟主弹窗里的树共享同一个 form.treeState,所以两边编辑实时同步
 *   - 大图树有更大字号 / 更宽间距 / hover 工具条一直可见,方便在结构很深的模板上操作
 *   - onTreeChange 是大图树里的 onChange 回调(改名 / 改值 / 加删等),它应当同时刷主弹窗小图和 form.xml
 *
 * 返回值:把 renderFullscreenTree 挂到 window.__kmai_fsRender,方便主弹窗在外部触发大图重绘
 */
function openEditTreeFullscreen(form, onTreeChange) {
  // 如果已经存在,先关掉旧的(防止重入)
  document.querySelectorAll('.edit-tree-fullscreen').forEach((el) => el.remove());

  const fs = document.createElement('div');
  fs.className = 'edit-tree-fullscreen';
  fs.innerHTML =
    '<div class="edit-tree-fullscreen-head">' +
      '<div class="edit-tree-fullscreen-title">' +
        '<span class="edit-tree-fullscreen-icon">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>' +
          '</svg>' +
        '</span>' +
        '<div class="edit-tree-fullscreen-title-text">' +
          '<div class="edit-tree-fullscreen-title-main">分组结构 — 放大编辑视图</div>' +
        '</div>' +
      '</div>' +
      '<div class="edit-tree-fullscreen-actions">' +
        '<button type="button" class="edit-tree-tool" data-role="fs-expand">全部展开</button>' +
        '<button type="button" class="edit-tree-tool" data-role="fs-collapse">全部折叠</button>' +
        '<button type="button" class="edit-tree-fullscreen-close" aria-label="关闭全屏" title="关闭全屏">×</button>' +
      '</div>' +
    '</div>' +
    '<div class="edit-tree-fullscreen-body">' +
      '<div class="edit-tree edit-tree-large" data-role="fs-tree"></div>' +
    '</div>';

  document.body.appendChild(fs);
  const fsTreeEl = fs.querySelector('[data-role="fs-tree"]');
  const fsTreeCtx = {
    onChange: onTreeChange,
    defaultCollapsedDepth: 99,
    _collapsedNodes: form.treeCollapsedNodes || new Map(),
    _expandedParams: form.expandedParams || new Set()
  };

  function renderFullscreenTree() {
    renderEditTree(fsTreeEl, form.treeState, fsTreeCtx);
  }
  renderFullscreenTree();

  // 大图里的工具按钮
  fs.querySelector('[data-role="fs-expand"]').addEventListener('click', function() {
    editTreeSetAllNodeCollapsed(fsTreeCtx, form.treeState, false);
    fsTreeEl.querySelectorAll('.edit-tree-node.is-collapsed').forEach((n) => n.classList.toggle('is-collapsed', false));
  });
  fs.querySelector('[data-role="fs-collapse"]').addEventListener('click', function() {
    editTreeSetRootChildrenCollapsed(fsTreeCtx, form.treeState, true);
    fsTreeEl.querySelectorAll(':scope > .edit-tree-node > .edit-tree-children > .edit-tree-node').forEach((n) => n.classList.toggle('is-collapsed', true));
  });

  const onKey = function(ev) {
    if (ev.key === 'Escape') { ev.stopPropagation(); close(); }
  };
  function close() {
    document.removeEventListener('keydown', onKey, true);
    fs.remove();
    if (window.__kmai_fsRender === renderFullscreenTree) window.__kmai_fsRender = null;
  }
  document.addEventListener('keydown', onKey, true);
  fs.addEventListener('click', function(ev) {
    if (ev.target === fs) close();
  });
  fs.querySelector('.edit-tree-fullscreen-close').addEventListener('click', close);

  // 把渲染函数挂到 window,方便 onTreeChange 回调(在另一个闭包里)调用
  window.__kmai_fsRender = renderFullscreenTree;

  return renderFullscreenTree;
}

/**
 * 把编辑弹窗里的基础信息同步回卡片 DOM。
 * 在保存后调用,让用户看到卡片本身立即刷新。
 */
function syncOptionCardFromEditor(card, edited) {
  if (!card) return;
  const titleEl = card.querySelector('.option-card-title');
  if (titleEl) {
    titleEl.textContent = edited.title;
    titleEl.setAttribute('title', edited.title);
  }
  const subtitleEl = card.querySelector('.option-card-subtitle');
  if (subtitleEl) {
    subtitleEl.textContent = edited.filename;
    subtitleEl.setAttribute('title', edited.filename);
  }
}

/**
 * 打开卡片编辑弹窗。点击右上角小笔图标时调用。
 */
export function openOptionCardEditor(opt, sourceCard) {
  const data = normalizeOptForEditor(opt);
  const backdrop = document.createElement('div');
  backdrop.className = 'edit-backdrop';

  const confPct = (data.confidence * 100).toFixed(1);
  const fullStars = Math.round(data.confidence * 5);
  const stars = '★'.repeat(fullStars) + '☆'.repeat(5 - fullStars);
  const confidenceMarkup = data.hideConfidence ? '' :
    '<div class="edit-conf-row">' +
      '<span class="edit-conf-label">匹配置信度</span>' +
      '<span class="edit-conf-value">' + confPct + '%</span>' +
      '<span class="edit-stars">' + stars + '</span>' +
      '<span style="margin-left:auto;font-size:12px;color:#1e40af">';
  const metadataMarkup = data.compactStructureOnly ? '' :
    confidenceMarkup +
    (data.hideConfidence ? '<div class="edit-conf-row edit-conf-row-meta">' : '') +
      (data.hideConfidence ? '<span style="margin-left:auto;font-size:12px;color:#1e40af">' : '') +
        '分组: <b>' + (data.groupCount || 0) + '</b> · 深度: <b>' + (data.depth || 0) + '</b>' +
      '</span></div>';
  const basicInfoMarkup = data.compactStructureOnly
    ? '<input class="edit-input" id="ed-filename" type="hidden" />'
    : '<div class="edit-section">' +
        '<div class="edit-section-label">基础信息</div>' +
        '<div class="edit-field">' +
          '<label for="ed-filename">文件名</label>' +
          '<input class="edit-input" id="ed-filename" type="text" maxlength="120" />' +
        '</div>' +
      '</div>';

  // 弹窗基本结构
  backdrop.innerHTML =
    '<div class="edit-dialog" role="dialog" aria-label="编辑模板卡片">' +
      '<div class="edit-dialog-head">' +
        '<div class="edit-dialog-title-wrap">' +
          '<span class="edit-dialog-icon">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>' +
          '</span>' +
          '<div class="edit-dialog-title-text">' +
            '<div class="edit-dialog-title">编辑模板卡片</div>' +
            '<div class="edit-dialog-subtitle" data-role="filename-head"></div>' +
          '</div>' +
        '</div>' +
        '<button class="edit-dialog-close" type="button" aria-label="关闭" data-role="close">×</button>' +
      '</div>' +
      '<div class="edit-dialog-body">' +
        metadataMarkup +
        basicInfoMarkup +
        '<div class="edit-divider"></div>' +
        '<div class="edit-section">' +
          '<div class="edit-section-label-row">' +
            '<div class="edit-section-label">分组结构预览</div>' +
            '<div class="edit-tree-tools">' +
              '<button type="button" class="edit-tree-tool edit-tree-tool-primary" data-role="tree-fullscreen" title="放大到全屏编辑">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                  '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>' +
                '</svg>' +
                '放大编辑' +
              '</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-expand" title="展开所有分组">全部展开</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-collapse" title="折叠到根节点">全部折叠</button>' +
              '<span class="edit-tree-tool-sep"></span>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-params-expand" title="展开所有分组的属性">属性全开</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-params-collapse" title="收起所有分组的属性">属性全收</button>' +
            '</div>' +
          '</div>' +
          '<div class="edit-tree" id="ed-struct" data-role="tree">' +
            '<div class="edit-tree-empty">加载中...</div>' +
          '</div>' +
        '</div>' +
        '<div class="edit-status" data-role="status"></div>' +
      '</div>' +
      '<div class="edit-actions">' +
        '<div class="edit-status" data-role="status-side" style="font-size:12px;color:#64748b"></div>' +
        '<div class="edit-actions-right">' +
          '<button class="edit-cancel" type="button" data-role="cancel">取消</button>' +
          '<button class="edit-save" type="button" data-role="save">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>' +
            '保存' +
          '</button>' +
        '</div>' +
      '</div>' +
    '</div>';

  document.body.appendChild(backdrop);

  // 缓存编辑状态 (避免与 module 顶部 import 的 `state` 冲突,这里改名 form)
  const form = {
    title: data.title,
    filename: data.filename,
    templateId: data.templateId,
    templateXml: data.templateXml,
    onSave: data.onSave,
    originalXml: '',   // 加载到的原始 XML(包含 Part_Template / Group_Template 字段定义)
    xml: '',           // 当前用于保存的 XML(由 treeState 重新生成)
    treeState: null,   // 可变的分组结构树
    treeCollapsedNodes: new Map(), // 分组展开/折叠 UI 状态,按 node.id 保留
    expandedParams: new Set(),     // 属性 chips 展开状态,按 node.id 保留
    closed: false
  };

  const filenameInput = backdrop.querySelector('#ed-filename');
  const statusEl = backdrop.querySelector('[data-role="status"]');
  const statusSide = backdrop.querySelector('[data-role="status-side"]');
  const saveBtn = backdrop.querySelector('[data-role="save"]');
  const cancelBtn = backdrop.querySelector('[data-role="cancel"]');
  const closeBtn = backdrop.querySelector('[data-role="close"]');
  const filenameHead = backdrop.querySelector('[data-role="filename-head"]');

  filenameInput.value = deriveDisplayNameFromFilename(form.filename) || form.filename;
  filenameHead.textContent = form.filename || form.title;

  function setStatus(text, kind) {
    statusEl.textContent = text || '';
    statusEl.className = 'edit-status' + (kind ? ' ' + kind : '');
  }
  function setStatusSide(text) { statusSide.textContent = text || ''; }

  function close() {
    if (form.closed) return;
    form.closed = true;
    document.removeEventListener('keydown', onKeydown, true);
    backdrop.remove();
  }
  function onKeydown(ev) {
    if (ev.key === 'Escape') {
      // 如果当前有放大编辑视图打开,Escape 由它处理,主弹窗不关
      if (document.querySelector('.edit-tree-fullscreen')) return;
      ev.stopPropagation();
      close();
    }
  }
  document.addEventListener('keydown', onKeydown, true);
  backdrop.addEventListener('click', function(ev) {
    // 同样,放大视图打开时点击主弹窗背景也不关
    if (ev.target === backdrop && !document.querySelector('.edit-tree-fullscreen')) close();
  });
  closeBtn.addEventListener('click', close);
  cancelBtn.addEventListener('click', close);

  filenameInput.addEventListener('input', function() {
    form.filename = filenameInput.value;
    const normalizedFilename = normalizeTemplateFilenameInput(form.filename);
    form.title = deriveDisplayNameFromFilename(normalizedFilename);
    filenameHead.textContent = normalizedFilename || form.title;
  });

  // 分组树工具按钮:全部展开 / 全部折叠 / 放大编辑
  const treeEl = backdrop.querySelector('[data-role="tree"]');
  const expandBtn = backdrop.querySelector('[data-role="tree-expand"]');
  const collapseBtn = backdrop.querySelector('[data-role="tree-collapse"]');
  const fullscreenBtn = backdrop.querySelector('[data-role="tree-fullscreen"]');
  const paramsExpandBtn = backdrop.querySelector('[data-role="tree-params-expand"]');
  const paramsCollapseBtn = backdrop.querySelector('[data-role="tree-params-collapse"]');
  const mainTreeCtx = {
    onChange: rerenderTree,
    defaultCollapsedDepth: 3,
    _collapsedNodes: form.treeCollapsedNodes,
    _expandedParams: form.expandedParams
  };
  expandBtn.addEventListener('click', function() {
    if (!treeEl) return;
    editTreeSetAllNodeCollapsed(mainTreeCtx, form.treeState, false);
    treeEl.querySelectorAll('.edit-tree-node.is-collapsed').forEach((n) => n.classList.toggle('is-collapsed', false));
  });
  collapseBtn.addEventListener('click', function() {
    if (!treeEl) return;
    // 只折叠一层:让第一层(根之外)的子节点全部合上,根保持展开
    editTreeSetRootChildrenCollapsed(mainTreeCtx, form.treeState, true);
    treeEl.querySelectorAll(':scope > .edit-tree-node > .edit-tree-children > .edit-tree-node').forEach((n) => n.classList.toggle('is-collapsed', true));
  });
  // 「属性全开 / 属性全收」:遍历所有有参数的 row,逐个触发 toggle 按钮的点击
  function bulkToggleParams(expand) {
    if (!treeEl) return;
    treeEl.querySelectorAll('.edit-tree-params-toggle').forEach((btn) => {
      const isExpanded = btn.classList.contains('is-expanded');
      if ((expand && !isExpanded) || (!expand && isExpanded)) btn.click();
    });
  }
  if (paramsExpandBtn) paramsExpandBtn.addEventListener('click', function() { bulkToggleParams(true); });
  if (paramsCollapseBtn) paramsCollapseBtn.addEventListener('click', function() { bulkToggleParams(false); });
  fullscreenBtn.addEventListener('click', function() {
    if (!form.treeState) {
      setStatus('XML 尚未加载完成,请稍候再试', 'err');
      return;
    }
    // 打开全屏编辑视图;返回 renderFullscreenTree 函数供每次状态变更时调用
    openEditTreeFullscreen(form, function onTreeChange() {
      // 大图里改了东西:重渲小图 + 重渲大图 + 更新 form.xml
      rerenderTree();
      if (window.__kmai_fsRender) window.__kmai_fsRender();
    });
  });

  // 加载真实 XML (相似件页面可直接传入已由零件映射解析的 XML)
  if (form.templateXml) {
    form.originalXml = form.templateXml;
    form.treeState = buildEditTreeFromXml(form.originalXml);
    renderEditTree(treeEl, form.treeState, mainTreeCtx);
    form.xml = spliceEditTreeIntoXml(form.originalXml, form.treeState);
    setStatus('XML 已加载,可直接在树上增删改后保存', 'ok');
  } else if (!form.templateId) {
    renderEmptyTree(treeEl);
    setStatus('当前卡片没有 templateId,无法加载真实 XML 结构。', 'err');
  } else {
    setStatus('正在加载 XML...', 'loading');
    const xmlUrl = '/api/template/xml?templateId=' + encodeURIComponent(form.templateId) +
      '&filename=' + encodeURIComponent(form.filename) + '&_=' + Date.now();
    requestJson('GET', xmlUrl, null, function(data) {
      if (data && data.status === 'success' && data.result) {
        const xml = extractTemplateXml(data);
        if (xml) {
          form.originalXml = xml;
          form.treeState = buildEditTreeFromXml(xml);
          renderEditTree(treeEl, form.treeState, mainTreeCtx);
          form.xml = spliceEditTreeIntoXml(form.originalXml, form.treeState);
          setStatus('XML 已加载,可直接在树上增删改后保存', 'ok');
        } else {
          renderEmptyTree(treeEl);
          setStatus('XML 加载失败: 接口未返回内容', 'err');
        }
      } else {
        renderEmptyTree(treeEl);
        setStatus('XML 加载失败: ' + (data && data.message ? data.message : 'unknown error'), 'err');
      }
    }, function(err) {
      renderEmptyTree(treeEl);
      setStatus('XML 加载失败: ' + err.message, 'err');
    }, 30000);
  }

  // 每次树状态变化后:重新渲染 + 把树序列化成新 XML(用于保存)
  function rerenderTree() {
    renderEditTree(treeEl, form.treeState, mainTreeCtx);
    form.xml = spliceEditTreeIntoXml(form.originalXml, form.treeState);
  }

  function renderEmptyTree(container) {
    if (!container) return;
    container.innerHTML = '<div class="edit-tree-empty">没有可编辑的分组结构。</div>';
  }

  // 保存:仅暂存到卡片对象。真正写入模板库由外层“写入模板库并加载”触发。
  saveBtn.addEventListener('click', function() {
    if (saveBtn.disabled) return;
    if (!form.xml) { setStatus('XML 尚未加载完成,请稍候再试', 'err'); return; }
    const savedFilename = normalizeTemplateFilenameInput(form.filename);
    if (!savedFilename) { setStatus('文件名不能为空', 'err'); return; }
    form.filename = savedFilename;
    form.title = deriveDisplayNameFromFilename(savedFilename);
    filenameInput.value = form.title;
    filenameHead.textContent = savedFilename;
    const editedTemplate = { filename: savedFilename, xml: form.xml };
    if (sourceCard) {
      sourceCard.__kmaiEditedTemplate = { filename: savedFilename, xml: form.xml };
      opt.__kmaiEditedTemplate = sourceCard.__kmaiEditedTemplate;
    } else {
      opt.__kmaiEditedTemplate = editedTemplate;
    }
    opt.filename = savedFilename;
    opt.subtitle = savedFilename;
    opt.title = form.title;
    if (sourceCard) {
      syncOptionCardFromEditor(sourceCard, {
        title: deriveDisplayNameFromFilename(savedFilename),
        filename: savedFilename
      });
      resetOptionCardForTemplateEdit(sourceCard);
    }
    if (form.onSave) form.onSave(editedTemplate);
    setStatus(
      form.onSave ? '已暂存修改，点击“应用当前分组模板”后生效。' : '已临时保存，点击外层“写入模板库并加载”后才会写入本地模板库。',
      'ok'
    );
    setStatusSide('✓ 临时保存');
    if (!form.onSave) {
      addMsg('bot', '<div class="save-status save-status-ok">' +
        '<span class="save-icon">✓</span> 模板已临时保存' +
        '<code class="save-path">' + escapeHtml(savedFilename) + '</code>' +
        '<span class="save-meta">· 待写入模板库</span></div>');
    }
    setTimeout(close, 600);
  });

  // 自动 focus 文件名输入框,默认让用户直接编辑基础名。
  setTimeout(function() { filenameInput.focus(); filenameInput.select(); }, 30);
}

/** 从模板接口响应里把 XML 内容抽出来,几个位置都放过,handoff / artifacts 都得看。 */
export function extractTemplateXml(data) {
  const result = data && data.result ? data.result : null;
  if (!result) return '';
  if (result.xml) return result.xml;
  if (result.content) return result.content;
  if (result.handoff && result.handoff.xml) return result.handoff.xml;
  if (result.artifacts && result.artifacts.xml && result.artifacts.xml.content) return result.artifacts.xml.content;
  return '';
}

/** XML 编辑器:点模板卡 → 弹 textarea → 用户改完 → 保存到文件。 */
export function openXmlEditor(templateId, filename, displayName) {
  if (!templateId) { addErrorMsg("template id is empty"); return; }
  const editor = document.createElement("div");
  editor.className = "xml-editor-msg";
  editor.innerHTML =
    '<div class="xml-editor-header">✍️ <span>编辑分组模板</span> ' +
    '<span class="xml-editor-filename">' + escapeHtml(filename || templateId) + '</span></div>' +
    '<textarea class="xml-editor-textarea" spellcheck="false" placeholder="正在加载 XML..."></textarea>' +
    '<div class="xml-editor-actions">' +
      '<button class="xml-editor-save" type="button" disabled>确定保存</button>' +
      '<button class="xml-editor-cancel" type="button">取消</button>' +
      '<span class="xml-editor-status loading">正在加载 XML...</span>' +
    '</div>';
  dom.log.appendChild(editor);
  dom.log.scrollTop = dom.log.scrollHeight;
  const textarea = editor.querySelector("textarea");
  const saveBtn = editor.querySelector(".xml-editor-save");
  const cancelBtn = editor.querySelector(".xml-editor-cancel");
  const statusEl = editor.querySelector(".xml-editor-status");
  let saved = false;
  cancelBtn.addEventListener("click", function() {
    if (!saved) {
      // 用户取消选择:重置所有卡片为可选状态
      const allCards = dom.log.querySelectorAll('.option-card');
      allCards.forEach(function(c) {
        const b = c.querySelector('button');
        if (b) { b.disabled = false; b.textContent = '写入应用并识别推理'; }
        c.classList.remove('is-selected');
      });
    }
    editor.remove();
  });
  // load XML content
  const xmlUrl = "/api/template/xml?templateId=" + encodeURIComponent(templateId) +
    "&filename=" + encodeURIComponent(filename || "") + "&_=" + Date.now();
  requestJson("GET", xmlUrl, null, function(data) {
    if (data && data.status === "success" && data.result) {
      const xml = extractTemplateXml(data);
      if (xml) {
        textarea.value = xml;
        saveBtn.disabled = false;
        statusEl.className = "xml-editor-status";
        statusEl.textContent = "加载完成，可编辑后保存";
      } else {
        statusEl.className = "xml-editor-status error";
        statusEl.textContent = "加载失败: 接口未返回 XML 内容";
      }
    } else {
      statusEl.className = "xml-editor-status error";
      statusEl.textContent = "加载失败: " + (data && data.message ? data.message : "unknown error");
    }
  }, function(err) {
    statusEl.className = "xml-editor-status error";
    statusEl.textContent = "加载失败: " + err.message;
  }, 30000);
  // save
  saveBtn.addEventListener("click", function() {
    if (saveBtn.disabled) return;
    saveBtn.disabled = true;
    statusEl.className = "xml-editor-status loading";
    statusEl.textContent = "正在保存...";
    requestJson("POST", "/api/template/save", JSON.stringify({ filename: filename, xml: textarea.value }), function(data) {
      if (data && data.status === "success") {
        statusEl.className = "xml-editor-status success";
        statusEl.textContent = "✓ 已保存: " + (data.saved_path || data.filename || "");
        const banner = document.createElement("div");
        banner.className = "save-status save-status-ok";
        banner.innerHTML =
          '<span class="save-icon">✓</span> 已写入 3DMPS 安装目录<br>' +
          '<code class="save-path">' + escapeHtml(data.saved_path || "") + '</code>' +
          '<span class="save-meta">，' + (data.bytes || 0) + ' 字节</span>';
        editor.appendChild(banner);
        saved = true;
        cancelBtn.textContent = "关闭";
      } else {
        statusEl.className = "xml-editor-status error";
        statusEl.textContent = "保存失败: " + (data && data.message ? data.message : "unknown error");
        saveBtn.disabled = false;
      }
    }, function(err) {
      statusEl.className = "xml-editor-status error";
      statusEl.textContent = "保存失败: " + err.message;
      saveBtn.disabled = false;
    }, 30000);
  });
}

// ============================================================
// 工艺输入 inbox 卡片
// ============================================================

/** 在 #log 里追加一张「待处理工艺输入」卡片,给用户「填充到输入框 / 复制 JSON」两个动作。 */
export function addProcessRouteInboxCard(payload) {
  const text = buildProcessRouteInboxText(payload);
  if (!text) return;
  state.latestProcessRouteInputPayload = payload || null;
  // 同步给 process_route 模块做元数据展示,即使调试模式关闭也要保留最新输入。
  import('./process_route.js').then(m => m.updateProcessRouteInputMeta(payload));
  if (!state.processRouteAwaitingInput && !state.processRoutePanelUnlocked) return;
  if (typeof state !== 'undefined' && state && state.debugMode === false) {
    return;
  }

  const container = document.createElement('div');
  container.className = 'process-route-inbox-msg';

  const inputFile = payload.input_file || '';
  const traceId = payload.trace_id || '';
  const createdAt = payload.created_at || '';
  const source = payload.source || 'mps_local';

  container.innerHTML =
    '<div class="process-route-inbox-head">' +
      '<div class="process-route-inbox-title">待处理工艺输入</div>' +
      '<div class="process-route-inbox-meta">' + escapeHtml(source) + '</div>' +
    '</div>' +
    '<div class="process-route-inbox-desc">' +
      '3DMPS 已推送一份新的工艺输入 JSON。可先查看，再填充到输入框或直接触发工艺智能体。' +
      (inputFile ? '<br><span style="color:#64748b">文件: ' + escapeHtml(inputFile) + '</span>' : '') +
      (traceId ? '<br><span style="color:#64748b">Trace: ' + escapeHtml(traceId) + '</span>' : '') +
      (createdAt ? '<br><span style="color:#64748b">时间: ' + escapeHtml(createdAt) + '</span>' : '') +
    '</div>' +
    '<div class="process-route-inbox-actions">' +
      '<button type="button" class="process-route-inbox-primary" data-action="fill">填充到输入框</button>' +
      '<button type="button" class="process-route-inbox-secondary" data-action="copy">复制 JSON</button>' +
      '<button type="button" class="process-route-inbox-toggle" data-action="toggle-json">查看 JSON ▾</button>' +
    '</div>' +
    '<pre class="process-route-inbox-pre" data-json-hidden="true" style="display:none">' + escapeHtml(text) + '</pre>';

  // 折叠/展开 JSON 预览
  container.querySelector('[data-action="toggle-json"]').addEventListener('click', function() {
    const pre = container.querySelector('.process-route-inbox-pre');
    const btn = container.querySelector('[data-action="toggle-json"]');
    if (!pre) return;
    const hidden = pre.style.display === 'none';
    pre.style.display = hidden ? '' : 'none';
    btn.textContent = hidden ? '收起 JSON ▴' : '查看 JSON ▾';
  });

  container.querySelector('[data-action="fill"]').addEventListener('click', function() {
    dom.input.value = text;
    dom.input.focus();
    setStatus('ok', '已将工艺输入 JSON 填充到输入框');
  });

  container.querySelector('[data-action="copy"]').addEventListener('click', function() {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() {
        setStatus('ok', '已复制工艺输入 JSON');
      }, function() {
        setStatus('warn', '复制失败，请手动复制');
      });
    } else {
      setStatus('warn', '当前环境不支持自动复制');
    }
  });

  dom.log.appendChild(container);
  dom.log.scrollTop = dom.log.scrollHeight;
}

export function syncProcessRouteInboxCardVisibility() {
  clearProcessRouteInboxCard();
  if (typeof state !== 'undefined' && state && state.debugMode === false) {
    return;
  }
  addProcessRouteInboxCard(state.latestProcessRouteInputPayload);
}

/** 移除聊天日志里所有「待处理工艺输入」卡片。
 *  - 用户从未点过第 4 步、或已离开第 4 步状态(切智能体 / 重置工作流 / 切到别的步骤)时调用。
 *  - 第 4 步被重新触发时,addProcessRouteInboxCard 会再次插入新的卡片。
 */
export function clearProcessRouteInboxCard() {
  if (!dom || !dom.log) return;
  const cards = dom.log.querySelectorAll('.process-route-inbox-msg');
  cards.forEach(function(el) { el.remove(); });
}
