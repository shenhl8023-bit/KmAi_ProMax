// process_route.js 鈥斺€?宸ヨ壓璺嚎闈㈡澘 + 鍚庡彴 inbox 杞銆?//
// 璐熻矗:
//   1. 宸ヨ壓璺嚎闈㈡澘鐨勬墦寮€/鍏抽棴銆佸弬鏁拌〃鍗曘€佺敓鎴?鎶€鏈姹?鎻愪氦涓変釜鎸夐挳
//   2. 鍚庡彴杞 /api/process-route/input/latest,鎹曡幏 3DMPS 鎺ㄨ繃鏉ョ殑 input JSON
//   3. 绗?4 姝ャ€岃繘琛孉I宸ヨ壓鎺ㄧ悊銆嶇殑鐘舵€佹満鍏ュ彛
//
// 涓庡叾瀹冩ā鍧楃殑杈圭晫:
//   - 鏀跺埌鏂?input 鏃惰皟 `addProcessRouteInboxCard`(tool_call.js),閫氳繃鍔ㄦ€?import
//   - 宸ヤ綔娴?dock 鐨勬楠ゅ垏鎹㈢敱 workflow.js 瑙﹀彂,鏈ā鍧椾笉鐩存帴鐢诲伐浣滄祦鍗?//   - 琛ㄥ崟瀛楁 change 浜嬩欢鐢?entry.js 缁戝畾鍒版湰妯″潡鐨?setPrParamChips

import {
  state, dom, escapeHtml, setStatus, addErrorMsg, addUserMsg,
  requestJson, isToolSuccess,
  getProcessRouteInboxKey, splitCommaList,
  PROCESS_AUTO_AGENT_ID,
} from './shared.js';

// 缂撳瓨鐨?addProcessRouteInboxCard(鐢?entry 娉ㄥ叆),閬垮厤寰幆 import
let _addProcessRouteInboxCard = null;
let _updateProcessWorkflowCards = null;
let _markProcessWorkflowStepIdle = null;
let _markProcessWorkflowStepDone = null;
let currentResultView = 'route';

const PROCESS_ROUTE_MANUAL_DEFAULTS = {
  material_grade: '9Cr18',
  part_type: '\u886c\u5957',
  heat_treatment: '\u6dec\u706b',
  surface_treatments: [],
  inspection_items: ['\u88c2\u7eb9\u68c0\u6d4b'],
  marking_methods: ['\u6807\u5370'],
  special_process_flags: {
    shaped_hole_or_cut_flat: true,
    post_stage_added_hole: false
  }
};

export function setProcessRouteDeps(deps) {
  _addProcessRouteInboxCard = deps.addProcessRouteInboxCard || null;
  _updateProcessWorkflowCards = deps.updateProcessWorkflowCards || null;
  _markProcessWorkflowStepIdle = deps.markProcessWorkflowStepIdle || null;
  _markProcessWorkflowStepDone = deps.markProcessWorkflowStepDone || null;
}

// ============================================================
// 鐘舵€侀噸缃?// ============================================================

/** 鍒囨櫤鑳戒綋鏃惰皟,鎶婇潰鏉挎祦绋嬬浉鍏崇殑鍑犱釜鏍囧織浣嶅叏閮ㄦ竻鎺夈€?*/
export function resetProcessRoutePanelFlowState() {
  state.processRoutePanelUnlocked = false;
  state.processRouteAwaitingInput = false;
  state.processRouteAwaitingBaseKey = '';
  state.latestProcessRouteInboxKey = '';
  currentResultView = 'route';
  // 鍚屾娓呮帀鑱婂ぉ鏃ュ織閲屾畫鐣欑殑銆屽緟澶勭悊宸ヨ壓杈撳叆銆嶅崱鐗囷紝
  // 閬垮厤鍦ㄨ繕娌＄偣杩囩 4 姝ユ椂灏辨樉绀恒€
  import('./tool_call.js').then(function(m) {
    if (m && typeof m.clearProcessRouteInboxCard === 'function') {
      m.clearProcessRouteInboxCard();
    }
  }).catch(function() {});
}

// ============================================================
// 闈㈡澘鍙鎬?// ============================================================

export function openProcessRoutePanel(forceOpen) {
  if (!dom.processRoutePanel) return;
  if (forceOpen) state.processRoutePanelManuallyClosed = false;
  dom.processRoutePanel.style.display = '';
  if (dom.processRoutePanelBackdrop) {
    dom.processRoutePanelBackdrop.style.display = '';
  }
  window.requestAnimationFrame(function() {
    dom.processRoutePanel.classList.add('is-open');
    if (dom.processRoutePanelBackdrop) {
      dom.processRoutePanelBackdrop.classList.add('is-open');
    }
  });
}

export function closeProcessRoutePanel(manual) {
  if (!dom.processRoutePanel) return;
  if (manual) state.processRoutePanelManuallyClosed = true;
  dom.processRoutePanel.classList.remove('is-open');
  if (dom.processRoutePanelBackdrop) {
    dom.processRoutePanelBackdrop.classList.remove('is-open');
  }
  window.setTimeout(function() {
    if (dom.processRoutePanel.classList.contains('is-open')) return;
    dom.processRoutePanel.style.display = 'none';
    if (dom.processRoutePanelBackdrop && !dom.processRoutePanelBackdrop.classList.contains('is-open')) {
      dom.processRoutePanelBackdrop.style.display = 'none';
    }
  }, 220);
}

/** 宸ヨ壓璺嚎闈㈡澘榛樿闅愯棌;鍙湁褰撶敤鎴峰湪鍥哄畾宸ヤ綔娴侀噷鐐瑰嚮绗?4 姝? *  (杩涜AI宸ヨ壓鎺ㄧ悊)瑙﹀彂瑙ｉ攣銆佸苟鏀跺埌鏈夋晥杈撳叆 JSON 鍚?鎵嶆樉绀恒€? */
export function updateProcessRoutePanelVisibility() {
  if (!dom.processRoutePanel) return;
  const shouldShow = state.processRoutePanelUnlocked && hasProcessRouteInput(state.latestProcessRouteInputPayload);
  if (!shouldShow) {
    closeProcessRoutePanel(false);
    return;
  }
  if (!state.processRoutePanelManuallyClosed) {
    openProcessRoutePanel(false);
  }
}

/** 宸ヤ綔娴佺 4 姝ユ垚鍔熻Е鍙?/ 鍚庡彴杞鎹曡幏鍒版柊 input 鏃惰皟,鐪熸銆岃В閿併€嶉潰鏉裤€?*/
export function unlockProcessRoutePanelForInput(payload) {
  state.processRoutePanelUnlocked = true;
  state.processRouteAwaitingInput = false;
  state.processRouteAwaitingBaseKey = '';
  state.processWorkflowState.activeStepId = 'ai_process_input';
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = '';
  state.processWorkflowState.waitingUserStepId = 'ai_process_input';
  state.processWorkflowState.autoSubmittedRoute = false;
  updateProcessRouteInputMeta(payload);
  // 第 4 步收到 CAD 输入后要主动弹出工艺面板，即使用户之前手动关过面板。
  openProcessRoutePanel(true);
  if (_updateProcessWorkflowCards) _updateProcessWorkflowCards();
  setStatus('warn', '已收到 AI 工艺输入 JSON，请在工艺路线面板生成并提交结果');
  setProcessRoutePanelStatus('warn', '已收到 CAD 输入，请补充参数后点击开始生成工艺路线');
}

// ============================================================
// 闈㈡澘灏忓伐鍏?// ============================================================

function hasProcessRouteInput(payload) {
  return !!(payload && typeof payload === 'object' &&
    Array.isArray(payload.input_json) && payload.input_json.length);
}

function setProcessRoutePanelStatus(kind, text) {
  if (!dom.processRouteStatus) return;
  dom.processRouteStatus.className = 'pr-status' + (kind ? ' ' + kind : '');
  dom.processRouteStatus.textContent = text || '';
}

function setPrParamsOpen(open) {
  if (!dom.prParamsBlock) return;
  dom.prParamsBlock.classList.toggle('is-open', !!open);
}

export function setProcessRouteAdvancedOpen(open) {
  setPrParamsOpen(!!open);
}

function setPrParamChips(manual) {
  if (!dom.prChipMaterial) return;
  const m = manual || {};
  dom.prChipMaterial.textContent = m.material_grade || '—';
  dom.prChipPartType.textContent = m.part_type || '—';
  dom.prChipHeat.textContent = m.heat_treatment || '—';
  const surface = Array.isArray(m.surface_treatments) ? m.surface_treatments.filter(Boolean) : [];
  const flags = m.special_process_flags && typeof m.special_process_flags === 'object' ? m.special_process_flags : {};
  const options = [];
  if (flags.shaped_hole_or_cut_flat) options.push('型孔 / 割扁');
  if (flags.post_stage_added_hole) options.push('后段补充孔');
  if (!options.length && surface.length) options.push(surface.join('+'));
  dom.prChipSurface.textContent = options.length ? options.join('，') : '—';
}

function resetProcessRouteManualInputs() {
  setProcessRouteSelectValue(dom.processRouteMaterialGrade, '');
  setProcessRouteSelectValue(dom.processRoutePartType, '');
  setProcessRouteSelectValue(dom.processRouteHeatTreatment, '');
  if (dom.processRouteInspectionItems) dom.processRouteInspectionItems.value = '';
  if (dom.processRouteMarkingMethods) dom.processRouteMarkingMethods.value = '';
  if (dom.processRouteFlagShapedHole) dom.processRouteFlagShapedHole.checked = false;
  if (dom.processRouteFlagPostStageHole) dom.processRouteFlagPostStageHole.checked = false;
  document.querySelectorAll('[data-surface]').forEach(function(el) {
    el.checked = false;
  });
  setPrParamChips(null);
}


function joinManualList(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join('\uff0c');
  }
  if (typeof value === 'string') {
    return value;
  }
  return '';
}

function manualArray(value) {
  if (Array.isArray(value)) {
    return value.map(function(item) { return String(item || '').trim(); }).filter(Boolean);
  }
  return splitCommaList(value);
}

function firstProcessRouteManualValue(value, fallback) {
  const values = manualArray(value);
  return values.length ? values[0] : fallback;
}

function applyProcessRouteManualDefaults(manual) {
  const raw = manual && typeof manual === 'object' ? manual : {};
  const rawFlags = raw.special_process_flags && typeof raw.special_process_flags === 'object' ? raw.special_process_flags : {};
  const defaultFlags = PROCESS_ROUTE_MANUAL_DEFAULTS.special_process_flags;
  const materialGrade = firstProcessRouteManualValue(raw.material_grade, PROCESS_ROUTE_MANUAL_DEFAULTS.material_grade);
  const partType = firstProcessRouteManualValue(raw.part_type, PROCESS_ROUTE_MANUAL_DEFAULTS.part_type);
  const surfaceTreatments = manualArray(raw.surface_treatments);
  const inspectionItems = manualArray(raw.inspection_items);
  const markingMethods = manualArray(raw.marking_methods);
  return {
    material_grade: materialGrade === '45' ? PROCESS_ROUTE_MANUAL_DEFAULTS.material_grade : materialGrade,
    part_type: partType === '\u56de\u8f6c\u4f53' ? PROCESS_ROUTE_MANUAL_DEFAULTS.part_type : partType,
    heat_treatment: firstProcessRouteManualValue(raw.heat_treatment, PROCESS_ROUTE_MANUAL_DEFAULTS.heat_treatment),
    surface_treatments: surfaceTreatments.length ? surfaceTreatments : PROCESS_ROUTE_MANUAL_DEFAULTS.surface_treatments.slice(),
    inspection_items: inspectionItems.length ? inspectionItems : PROCESS_ROUTE_MANUAL_DEFAULTS.inspection_items.slice(),
    marking_methods: markingMethods.length ? markingMethods : PROCESS_ROUTE_MANUAL_DEFAULTS.marking_methods.slice(),
    special_process_flags: {
      shaped_hole_or_cut_flat: rawFlags.shaped_hole_or_cut_flat === true || defaultFlags.shaped_hole_or_cut_flat,
      post_stage_added_hole: Object.prototype.hasOwnProperty.call(rawFlags, 'post_stage_added_hole') ? !!rawFlags.post_stage_added_hole : defaultFlags.post_stage_added_hole
    }
  };
}

function setProcessRouteSelectValue(selectEl, value, fallbackValue) {
  if (!selectEl) return;
  const normalized = String(value || '').trim();
  const fallback = String(fallbackValue || '').trim();
  function hasOption(optionValue) {
    return Array.from(selectEl.options).some(function(option) {
      return option.value === optionValue;
    });
  }
  const targetValue = normalized && fallback && !hasOption(normalized) ? fallback : normalized;
  Array.from(selectEl.querySelectorAll('option[data-manual-default="true"]')).forEach(function(option) {
    if (!targetValue || option.value !== targetValue) option.remove();
  });
  if (!targetValue) {
    selectEl.value = '';
    return;
  }
  if (!hasOption(targetValue)) {
    const option = document.createElement('option');
    option.value = targetValue;
    option.textContent = targetValue;
    option.dataset.manualDefault = 'true';
    selectEl.appendChild(option);
  }
  selectEl.value = targetValue;
}

function applyManualDefaultsToProcessRouteForm(payload) {
  const rawManual = payload && (payload.manual_defaults || payload.manual || payload['\u4eba\u5de5\u8865\u5145']);
  const manual = applyProcessRouteManualDefaults(rawManual);
  setProcessRouteSelectValue(dom.processRouteMaterialGrade, manual.material_grade, PROCESS_ROUTE_MANUAL_DEFAULTS.material_grade);
  setProcessRouteSelectValue(dom.processRoutePartType, manual.part_type, PROCESS_ROUTE_MANUAL_DEFAULTS.part_type);
  setProcessRouteSelectValue(dom.processRouteHeatTreatment, manual.heat_treatment, PROCESS_ROUTE_MANUAL_DEFAULTS.heat_treatment);
  setProcessRouteSelectValue(dom.processRouteInspectionItems, manual.inspection_items[0], PROCESS_ROUTE_MANUAL_DEFAULTS.inspection_items[0]);
  setProcessRouteSelectValue(dom.processRouteMarkingMethods, manual.marking_methods[0], PROCESS_ROUTE_MANUAL_DEFAULTS.marking_methods[0]);
  const flags = manual.special_process_flags && typeof manual.special_process_flags === 'object' ? manual.special_process_flags : {};
  if (dom.processRouteFlagShapedHole) dom.processRouteFlagShapedHole.checked = !!flags.shaped_hole_or_cut_flat;
  if (dom.processRouteFlagPostStageHole) dom.processRouteFlagPostStageHole.checked = !!flags.post_stage_added_hole;
  const surfaceTreatments = manualArray(manual.surface_treatments);
  document.querySelectorAll('[data-surface]').forEach(function(el) {
    el.checked = surfaceTreatments.indexOf(el.value) >= 0;
  });
  setPrParamChips(buildManualProcessRoutePayload());
}

function setPrMetaInfo(payload) {
  if (!dom.prMetaInfo) return;
  const file = payload && payload.input_file ? payload.input_file : '';
  const trace = payload && payload.trace_id ? payload.trace_id : '';
  if (!file && !trace) {
    dom.prMetaInfo.textContent = '';
    dom.prMetaInfo.title = '';
    return;
  }
  const parts = [];
  if (file) parts.push(file);
  if (trace) parts.push(trace);
  const text = parts.join(' 路 ');
  dom.prMetaInfo.textContent = text;
  dom.prMetaInfo.title = text;
  // 涓嶄富鍔?display='' 鈥斺€?璺緞榛樿闅愯棌,鍙湪鐢ㄦ埛鐐?... 鎸夐挳鏃剁敱 onMoreClick 鏄惧紡鎵撳紑
}

function updateGenerateButtonText() {
  if (!dom.processRouteGenerateBtn) return;
  const hasResult = !!(state.latestProcessRouteResult && Array.isArray(state.latestProcessRouteResult.route) && state.latestProcessRouteResult.route.length);
  dom.processRouteGenerateBtn.textContent = hasResult ? '重新生成工艺路线' : '生成工艺路线';
}

function hasProcessRouteReadyToSubmit() {
  return !!(state.latestProcessRouteResult &&
    Array.isArray(state.latestProcessRouteResult.route) &&
    state.latestProcessRouteResult.route.length &&
    state.latestProcessRouteTechnicalReady);
}

function updateProcessRouteSubmitButton() {
  if (!dom.processRouteSubmitBtn) return;
  const submitState = state.processRouteSubmitState || 'idle';
  dom.processRouteSubmitBtn.classList.remove('is-submitting', 'is-submitted', 'is-error');
  dom.processRouteSubmitBtn.title = state.processRouteSubmitMessage || '';
  if (submitState === 'submitting') {
    dom.processRouteSubmitBtn.classList.add('is-submitting');
    dom.processRouteSubmitBtn.textContent = '提交中...';
    dom.processRouteSubmitBtn.disabled = true;
    return;
  }
  if (submitState === 'submitted') {
    dom.processRouteSubmitBtn.classList.add('is-submitted');
    dom.processRouteSubmitBtn.textContent = '已提交 ✓';
    dom.processRouteSubmitBtn.disabled = true;
    return;
  }
  if (submitState === 'error') {
    dom.processRouteSubmitBtn.classList.add('is-error');
    dom.processRouteSubmitBtn.textContent = '提交失败，点击重试';
    dom.processRouteSubmitBtn.disabled = !hasProcessRouteReadyToSubmit();
    return;
  }
  dom.processRouteSubmitBtn.textContent = '提交工艺数据';
  dom.processRouteSubmitBtn.disabled = !hasProcessRouteReadyToSubmit();
}

function setProcessRouteSubmitButtonState(status, message) {
  state.processRouteSubmitState = status || 'idle';
  state.processRouteSubmitMessage = message || '';
  updateProcessRouteSubmitButton();
}

function resetProcessRouteSubmitButtonState() {
  setProcessRouteSubmitButtonState('idle', '');
}

function formatProcessRouteSubmitTime() {
  const now = new Date();
  function pad(value) { return String(value).padStart(2, '0'); }
  return pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
}

function setProcessRouteResultView(view) {
  const hasTechnical = !!(state.latestProcessRouteTechnicalReady && state.latestProcessRouteResult && Array.isArray(state.latestProcessRouteResult.route) && state.latestProcessRouteResult.route.length);
  currentResultView = 'route';
  if (dom.processRouteResultSwitch) {
    dom.processRouteResultSwitch.style.display = hasTechnical ? 'flex' : 'none';
  }
  if (dom.processRouteRouteTab) {
    dom.processRouteRouteTab.classList.toggle('is-active', currentResultView === 'route');
  }
  if (dom.processRouteTechnicalTab) {
    dom.processRouteTechnicalTab.classList.toggle('is-active', currentResultView === 'technical');
    dom.processRouteTechnicalTab.disabled = !hasTechnical;
  }
  if (dom.processRouteResults) {
    dom.processRouteResults.style.display = '';
  }
  if (dom.processRouteTechnicalView) {
    dom.processRouteTechnicalView.style.display = 'none';
  }
}

function syncProcessRouteActionRows() {
  const hasRoute = !!(state.latestProcessRouteResult && Array.isArray(state.latestProcessRouteResult.route) && state.latestProcessRouteResult.route.length);
  const canSubmit = hasProcessRouteReadyToSubmit();
  if (dom.processRouteTechnicalRow) {
    dom.processRouteTechnicalRow.style.display = (hasRoute && !state.latestProcessRouteTechnicalReady) ? 'flex' : 'none';
  }
  if (dom.processRouteTechnicalBtn) {
    dom.processRouteTechnicalBtn.disabled = !hasRoute || !!state.latestProcessRouteTechnicalReady;
  }
  if (dom.processRouteSubmitRow) {
    dom.processRouteSubmitRow.style.display = canSubmit ? 'flex' : 'none';
  }
  updateProcessRouteSubmitButton();
  setProcessRouteResultView(currentResultView);
}


function resetProcessRouteResultView(emptyText) {
  state.latestProcessRouteResult = null;
  state.latestProcessRouteTechnicalReady = false;
  currentResultView = 'route';
  resetProcessRouteSubmitButtonState();
  if (dom.prSummary) {
    dom.prSummary.style.display = 'none';
  }
  const routeEmptyText = emptyText || '尚未生成工艺路线。';
  dom.processRouteResults.innerHTML = '<div class="pr-empty">' + escapeHtml(routeEmptyText) + '</div>';
  if (dom.processRouteTechnicalView) {
    dom.processRouteTechnicalView.innerHTML = '<div class="pr-empty">尚未生成技术要求。</div>';
  }
  syncProcessRouteActionRows();
  updateGenerateButtonText();
}


/** 鎶婃渶鏂?payload 鍚屾鍒伴潰鏉垮ご/meta/chips,骞舵寜闇€閲嶇疆缁撴灉鍖恒€?*/
export function updateProcessRouteInputMeta(payload) {
  state.latestProcessRouteInputPayload = payload || null;
  if (!payload || typeof payload !== 'object') {
    state.currentProcessRouteInputKey = '';
    resetProcessRouteManualInputs();
    if (dom.prHeadStatusText) dom.prHeadStatusText.textContent = '绛夊緟 CAD 杈撳叆';
    setPrMetaInfo(null);
    resetProcessRouteResultView('尚未生成工艺路线。');
    setProcessRoutePanelStatus('', '绛夊緟 CAD 杈撳叆');
    return;
  }
  const nextKey = getProcessRouteInboxKey(payload);
  if (nextKey && nextKey !== state.currentProcessRouteInputKey) {
    state.currentProcessRouteInputKey = nextKey;
    resetProcessRouteManualInputs();
    applyManualDefaultsToProcessRouteForm(payload);
    resetProcessRouteResultView('尚未生成工艺路线。');
  }
  const inputJson = payload.input_json;
  const blockCount = Array.isArray(inputJson) ? inputJson.length : 0;
  setPrMetaInfo(payload);
  if (dom.prHeadStatusText) dom.prHeadStatusText.textContent = '已接收 ' + blockCount + ' 个 CAD 分组';
  setProcessRoutePanelStatus('ok', 'CAD 输入已就绪，可补充参数后开始生成');
}

// ============================================================
// 宸ヨ壓杈撳叆 helper
// ============================================================

export function extractProcessRouteInputPayload(payload) {
  if (hasProcessRouteInput(payload)) return payload;
  if (payload && typeof payload === 'object' && hasProcessRouteInput(payload.result)) {
    return payload.result;
  }
  return null;
}

function getProcessRouteToolErrorMessage(result, fallbackText) {
  if (result && typeof result === 'object') {
    const message = result.message || result.error || '';
    if (message) return String(message);
  }
  return fallbackText || '瑙﹀彂 AI 宸ヨ壓鎺ㄧ悊澶辫触';
}

// ============================================================
// 宸ヨ壓璺嚎缁撴灉娓叉煋
// ============================================================

function renderProcessRouteSummary(result) {
  const summary = result && result.summary ? result.summary : null;
  if (!summary || !dom.prSummary) {
    if (dom.prSummary) dom.prSummary.style.display = 'none';
    return;
  }
  if (dom.prStatGroup) dom.prStatGroup.textContent = summary.group_block_count != null ? summary.group_block_count : 0;
  if (dom.prStatFeature) dom.prStatFeature.textContent = summary.feature_count != null ? summary.feature_count : 0;
  if (dom.prStatProcess) dom.prStatProcess.textContent = summary.process_count != null ? summary.process_count : 0;
  if (dom.prStatStep) dom.prStatStep.textContent = summary.step_count != null ? summary.step_count : 0;
  const processCount = summary.process_count != null ? summary.process_count : 0;
  if (dom.prSummaryOk) dom.prSummaryOk.textContent = '已回传 3DMPS';
  if (dom.prHeadStatusText) dom.prHeadStatusText.textContent = '已生成 ' + processCount + ' 条工艺路线';
  dom.prSummary.style.display = '';
}

function buildProcessRouteStepHtml(step) {
  // This function is no longer used for the table layout, but we keep it in case it's called elsewhere
  return '';
}

function collectProcessRouteFeatureTexts(steps) {
  if (!Array.isArray(steps) || !steps.length) {
    return '';
  }

  const allFeatures = [];
  steps.forEach(function(step) {
    if (step && step.candidates && typeof step.candidates === 'object') {
      Object.keys(step.candidates).forEach(function(groupName) {
        const groupFeatures = Array.isArray(step.candidates[groupName]) ? step.candidates[groupName] : [];
        if (groupFeatures.length) {
          groupFeatures.forEach(function(featureName) {
            const featureText = formatProcessRouteFeatureText(groupName, featureName);
            if (featureText) allFeatures.push(featureText);
          });
          return;
        }
        if (groupName) allFeatures.push(groupName);
      });
      return;
    }
    if (step && Array.isArray(step.candidate_details)) {
      step.candidate_details.forEach(function(detail) {
        const featureText = detail && formatProcessRouteFeatureText(
          detail.group_path || detail.group_name || '',
          detail.feature_name || detail.sub_feature || detail.canonical_feature || detail.feature || ''
        );
        if (featureText) allFeatures.push(featureText);
      });
    }
  });

  const uniqueFeatures = [];
  for (let i = 0; i < allFeatures.length; i++) {
    if (allFeatures[i] && uniqueFeatures.indexOf(allFeatures[i]) === -1) {
      uniqueFeatures.push(allFeatures[i]);
    }
  }
  return uniqueFeatures.join('，');
}

function formatProcessRouteFeatureText(groupName, featureName) {
  const groupText = (groupName || '').toString().trim();
  const featureText = (featureName || '').toString().trim();
  if (groupText && featureText && groupText !== featureText) return groupText + '：' + featureText;
  return groupText || featureText;
}

function renderProcessRouteFeatureCell(featuresText) {
  const text = (featuresText || '').toString().trim();
  if (!text || text === '—') return '<span class="pr-cell-empty">—</span>';
  const featureParts = text.split(/[，,]+/).map(function(item) {
    return item.trim();
  }).filter(Boolean);
  return '<div class="pr-cell-lines pr-feature-lines">' + featureParts.map(function(item) {
    const pair = item.split(/[：:]/);
    const groupText = pair.length > 1 ? pair.shift().trim() : '';
    const featureText = pair.join('：').trim() || item;
    return '<div class="pr-cell-line pr-feature-line">' +
      (groupText ? '<span class="pr-feature-group">' + escapeHtml(groupText) + '</span>' : '') +
      '<span class="pr-feature-name">' + escapeHtml(featureText) + '</span>' +
    '</div>';
  }).join('') + '</div>';
}

function renderProcessRouteRequirementCell(requirementsValue) {
  const parts = Array.isArray(requirementsValue)
    ? requirementsValue.map(function(item) {
      return (item || '').toString().trim();
    }).filter(Boolean)
    : [(requirementsValue || '').toString().trim()].filter(Boolean);
  if (!parts.length) return '<span class="pr-tech-empty">暂无要求</span>';
  return '<div class="pr-cell-lines pr-requirement-lines">' + parts.map(function(item, reqIndex) {
    return '<div class="pr-cell-line"><span class="pr-line-index">' + (reqIndex + 1) + '.</span><span class="pr-line-text">' + escapeHtml(item) + '</span></div>';
  }).join('') + '</div>';
}

function renderProcessRouteCards(result) {
  const rows = result && Array.isArray(result.route) ? result.route : [];
  if (!rows.length) {
    dom.processRouteResults.innerHTML = '<div class="pr-empty">未生成可展示的工艺路线。</div>';
    return;
  }

  const tableRows = rows.map(function(row, index) {
    const steps = Array.isArray(row.steps) ? row.steps : [];
    const processType = (row.process_type || '').toString().trim();
    const isAux = /辅助|aux/i.test(processType) || steps.length === 0;

    let featuresText = collectProcessRouteFeatureTexts(steps);

    if (!featuresText && row.precision && row.precision !== processType) {
      featuresText = row.precision;
    }

    const techReqs = Array.isArray(row.technical_requirements) ? row.technical_requirements : [];

    return '<tr>' +
      '<td class="pr-index-cell"><span class="idx' + (isAux ? ' aux' : '') + '">' + (index + 1) + '</span></td>' +
      '<td class="pr-name-cell"><div class="name">' + escapeHtml(row.process_name || '未命名工序') + '</div></td>' +
      '<td class="pr-type-cell"><span class="tag">' + escapeHtml(processType || (isAux ? '辅助工序' : '加工工序')) + '</span></td>' +
      '<td class="pr-feature-cell">' + renderProcessRouteFeatureCell(featuresText || '—') + '</td>' +
      '<td class="pr-requirement-cell">' + renderProcessRouteRequirementCell(techReqs) + '</td>' +
    '</tr>';
  }).join('');

  dom.processRouteResults.innerHTML =
    '<div class="table-card" style="width:100%;overflow-x:auto;">' +
      '<table>' +
        '<thead>' +
          '<tr>' +
            '<th style="width:48px;">序号</th>' +
            '<th style="width:116px;">工序</th>' +
            '<th style="width:76px;">类型</th>' +
            '<th style="width:220px;">特征</th>' +
            '<th>技术要求</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>' +
          tableRows +
        '</tbody>' +
      '</table>' +
    '</div>';

  // Call the technical cards renderer (which we might just hide or repurpose)
  renderProcessRouteTechnicalCards(result);
}

function renderProcessRouteTechnicalCards(result) {
  if (!dom.processRouteTechnicalView) return;

  const rows = result && Array.isArray(result.route) ? result.route : [];
  if (!rows.length) {
    dom.processRouteTechnicalView.innerHTML = '<div class="pr-empty">请先生成技术要求。</div>';
    return;
  }

  const tableRows = rows.map(function(row, index) {
    const processType = (row.process_type || row.precision || '').toString().trim();
    const steps = Array.isArray(row.steps) ? row.steps : [];
    let featuresText = collectProcessRouteFeatureTexts(steps);
    if (!featuresText && row.precision && row.precision !== processType) {
      featuresText = row.precision;
    }

    const techReqs = Array.isArray(row.technical_requirements) ? row.technical_requirements : [];
    const techReqsHtml = techReqs.length
      ? '<div class="pr-tech-lines">' + techReqs.map(function(item, reqIndex) {
        return '<div class="pr-tech-line"><span class="pr-tech-line-index">' + (reqIndex + 1) + '.</span><span>' + escapeHtml(item) + '</span></div>';
      }).join('') + '</div>'
      : '<span class="pr-tech-empty">暂无要求</span>';

    return '<tr>' +
      '<td class="pr-index-cell"><span class="idx">' + (index + 1) + '</span></td>' +
      '<td class="pr-name-cell"><div class="name">' + escapeHtml(row.process_name || '未命名工序') + '</div></td>' +
      '<td class="pr-type-cell"><span class="tag">' + escapeHtml(processType || '工序') + '</span></td>' +
      '<td class="pr-feature-cell">' + renderProcessRouteFeatureCell(featuresText || '—') + '</td>' +
      '<td class="pr-requirement-cell">' + techReqsHtml + '</td>' +
    '</tr>';
  }).join('');

  dom.processRouteTechnicalView.innerHTML =
    '<div class="table-card" style="width:100%;overflow-x:auto;">' +
      '<table>' +
        '<thead>' +
          '<tr>' +
            '<th style="width:48px;">序号</th>' +
            '<th style="width:116px;">工序</th>' +
            '<th style="width:76px;">类型</th>' +
            '<th style="width:220px;">特征</th>' +
            '<th>技术要求</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>' +
          tableRows +
        '</tbody>' +
      '</table>' +
    '</div>';
}

function renderProcessRouteResult(result) {
  state.latestProcessRouteResult = result || null;
  state.latestProcessRouteTechnicalReady = !!(result && result.technical_requirements_generated);
  currentResultView = 'route';
  resetProcessRouteSubmitButtonState();
  renderProcessRouteSummary(result || {});
  renderProcessRouteCards(result || {});
  syncProcessRouteActionRows();
  updateGenerateButtonText();
}


function buildManualProcessRoutePayload() {
  const payload = {
    material_grade: dom.processRouteMaterialGrade.value.trim(),
    part_type: dom.processRoutePartType.value.trim(),
    special_process_flags: {
      shaped_hole_or_cut_flat: !!dom.processRouteFlagShapedHole.checked,
      post_stage_added_hole: !!dom.processRouteFlagPostStageHole.checked
    }
  };
  payload.heat_treatment = dom.processRouteHeatTreatment.value.trim();
  payload.surface_treatments = Array.from(document.querySelectorAll('[data-surface]'))
    .filter(function(el) { return el.checked; })
    .map(function(el) { return el.value; });
  payload.inspection_items = splitCommaList(dom.processRouteInspectionItems.value);
  payload.marking_methods = splitCommaList(dom.processRouteMarkingMethods.value);
  return payload;
}

function invalidateProcessRouteResultsAfterManualChange() {
  resetProcessRouteSubmitButtonState();
  const hasGeneratedResult = !!(state.latestProcessRouteResult &&
    Array.isArray(state.latestProcessRouteResult.route) &&
    state.latestProcessRouteResult.route.length);
  if (!hasGeneratedResult) return;
  resetProcessRouteResultView('参数已修改，请重新生成工艺路线。');
  setProcessRoutePanelStatus('warn', '参数已修改，请重新生成工艺路线。');
}

function handleProcessRouteParamsChange() {
  setPrParamChips(buildManualProcessRoutePayload());
  invalidateProcessRouteResultsAfterManualChange();
}

function scrollProcessRoutePanelToResults() {
  if (!dom.processRoutePanel || !dom.processRouteResults) return;
  const scroller = dom.processRoutePanel.querySelector('.pr-body');
  if (!scroller) return;
  const target = dom.processRouteResults.querySelector('.table-card') || dom.processRouteResults;
  const top = Math.max(0, target.offsetTop - scroller.offsetTop - 10);
  if (typeof scroller.scrollTo === 'function') {
    scroller.scrollTo({ top: top, behavior: 'smooth' });
  } else {
    scroller.scrollTop = top;
  }
}

// ============================================================
// 鐢熸垚 / 鎶€鏈姹?/ 鎻愪氦
// ============================================================

function generateProcessRoute() {
  return new Promise(function(resolve, reject) {
    if (!state.latestProcessRouteInputPayload || !Array.isArray(state.latestProcessRouteInputPayload.input_json) || !state.latestProcessRouteInputPayload.input_json.length) {
      const message = '还没有收到可用的 CAD 输入 JSON';
      setProcessRoutePanelStatus('err', message);
      reject(new Error(message));
      return;
    }
    state.processWorkflowState.autoSubmittedRoute = false;
    state.latestProcessRouteTechnicalReady = false;
    resetProcessRouteSubmitButtonState();
    let manual;
    try {
      manual = buildManualProcessRoutePayload();
    } catch (err) {
      setProcessRoutePanelStatus('err', '人工补充参数解析失败: ' + err.message);
      reject(err);
      return;
    }
    dom.processRouteGenerateBtn.disabled = true;
    dom.processRouteTechnicalBtn.disabled = true;
    dom.processRouteSubmitBtn.disabled = true;
    setProcessRoutePanelStatus('warn', '正在生成工艺路线...');
    requestJson('POST', '/api/process-route/generate', JSON.stringify({
      cad_input: state.latestProcessRouteInputPayload.input_json,
      manual: manual
    }), function(data) {
      dom.processRouteGenerateBtn.disabled = false;
      if (data && data.status === 'error') {
        const message = '工艺路线生成失败: ' + (data.message || '接口返回错误');
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      const result = data && data.result ? data.result : null;
      if (!result) {
        const message = '工艺路线接口未返回结果';
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      try {
        renderProcessRouteResult(result);
        const processCount = result.summary && result.summary.process_count ? result.summary.process_count : 0;
        setProcessRoutePanelStatus('ok', '工艺路线生成完成，共 ' + processCount + ' 道工序');
        resolve(result);
        maybeAutoGenerateTechnicalAfterUserRoute();
      } catch (err) {
        syncProcessRouteActionRows();
        setProcessRoutePanelStatus('err', '工艺路线结果渲染失败: ' + err.message);
        reject(err);
      }
    }, function(err) {
      dom.processRouteGenerateBtn.disabled = false;
      syncProcessRouteActionRows();
      setProcessRoutePanelStatus('err', '工艺路线生成失败: ' + err.message);
      reject(err);
    }, 120000);
  });
}

function generateTechnicalRequirements() {
  return new Promise(function(resolve, reject) {
    if (!state.latestProcessRouteResult || !Array.isArray(state.latestProcessRouteResult.route) || !state.latestProcessRouteResult.route.length) {
      const message = '请先生成工艺路线';
      setProcessRoutePanelStatus('warn', message);
      reject(new Error(message));
      return;
    }
    let manual;
    try {
      manual = buildManualProcessRoutePayload();
    } catch (err) {
      setProcessRoutePanelStatus('err', '人工补充参数解析失败: ' + err.message);
      reject(err);
      return;
    }
    dom.processRouteTechnicalBtn.disabled = true;
    dom.processRouteSubmitBtn.disabled = true;
    state.latestProcessRouteTechnicalReady = false;
    resetProcessRouteSubmitButtonState();
    syncProcessRouteActionRows();
    setProcessRoutePanelStatus('warn', '正在生成技术要求...');
    requestJson('POST', '/api/process-route/generate-technical-requirements', JSON.stringify({
      manual: manual
    }), function(data) {
      dom.processRouteTechnicalBtn.disabled = false;
      if (data && data.status === 'error') {
        const message = '技术要求生成失败: ' + (data.message || '接口返回错误');
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      const result = data && data.result ? data.result : null;
      if (!result) {
        const message = '技术要求接口未返回结果';
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      try {
        renderProcessRouteResult(result);
        setProcessRoutePanelStatus('ok', '技术要求生成完成，可提交工艺数据');
        resolve(result);
      } catch (err) {
        syncProcessRouteActionRows();
        setProcessRoutePanelStatus('err', '技术要求结果渲染失败: ' + err.message);
        reject(err);
      }
    }, function(err) {
      dom.processRouteTechnicalBtn.disabled = false;
      state.latestProcessRouteTechnicalReady = false;
      syncProcessRouteActionRows();
      setProcessRoutePanelStatus('err', '技术要求生成失败: ' + err.message);
      reject(err);
    }, 120000);
  });
}

function submitLatestProcessRoute() {
  return new Promise(function(resolve, reject) {
    const traceId = state.latestProcessRouteResult && state.latestProcessRouteResult.trace_id ||
      state.latestProcessRouteInputPayload && state.latestProcessRouteInputPayload.trace_id ||
      '';
    if (!state.latestProcessRouteResult || !Array.isArray(state.latestProcessRouteResult.route) || !state.latestProcessRouteResult.route.length) {
      const message = '还没有可提交的工艺路线结果';
      setProcessRouteSubmitButtonState('error', message);
      setProcessRoutePanelStatus('warn', message);
      reject(new Error(message));
      return;
    }
    if (!traceId) {
      const message = '提交失败：缺少 trace_id，请重新生成工艺路线';
      setProcessRouteSubmitButtonState('error', message);
      setProcessRoutePanelStatus('err', message);
      reject(new Error(message));
      return;
    }
    setProcessRouteSubmitButtonState('submitting', '正在回传工艺路线到 3DMPS...');
    setProcessRoutePanelStatus('warn', '正在回传工艺路线到 3DMPS...');
    requestJson('POST', '/api/process-route/submit', JSON.stringify({ timeout: 120, trace_id: traceId }), function(data) {
      if (data && data.status === 'error') {
        const message = '提交失败: ' + (data.message || data.error_code || 'submit process route failed');
        setProcessRouteSubmitButtonState('error', message);
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      const result = data && data.result ? data.result : null;
      if (!result) {
        const message = '提交接口未返回结果';
        setProcessRouteSubmitButtonState('error', message);
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      const submitResult = result.submit_result || {};
      if (submitResult && submitResult.status === 'error') {
        const message = '提交失败: ' + (submitResult.message || 'submit process route failed');
        setProcessRouteSubmitButtonState('error', message);
        setProcessRoutePanelStatus('err', message);
        reject(new Error(message));
        return;
      }
      const routeCount = result.route_count || 0;
      const submitMessage = '已回传到 3DMPS，共 ' + routeCount + ' 条工艺路线 · ' + formatProcessRouteSubmitTime();
      state.processWorkflowState.autoSubmittedRoute = true;
      if (state.processWorkflowState.waitingUserStepId === 'ai_process_input') {
        state.processWorkflowState.waitingUserStepId = '';
      }
      if (_markProcessWorkflowStepDone) _markProcessWorkflowStepDone('ai_process_input');
      setProcessRouteSubmitButtonState('submitted', submitMessage);
      setProcessRoutePanelStatus('ok', submitMessage);
      setStatus('ok', '第 4 步完成：AI 工艺路线和技术要求已生成并提交');
      resolve(result);
    }, function(err) {
      const message = '提交失败: ' + err.message;
      setProcessRouteSubmitButtonState('error', message);
      setProcessRoutePanelStatus('err', message);
      reject(err);
    }, 150000);
  });
}


function shouldAutoGenerateTechnicalAfterUserRoute() {
  if (!state.processWorkflowState.runningAll) return false;
  if (state.processWorkflowState.activeStepId !== 'ai_process_input') return false;
  if (state.processWorkflowState.waitingUserStepId !== 'ai_process_input') return false;
  if (state.latestProcessRouteTechnicalReady) return false;
  return true;
}

async function maybeAutoGenerateTechnicalAfterUserRoute() {
  if (!shouldAutoGenerateTechnicalAfterUserRoute()) return;
  if (state.processWorkflowState.autoGeneratingTechnical) return;
  state.processWorkflowState.autoGeneratingTechnical = true;
  state.processWorkflowState.autoRouteError = '';
  setStatus('warn', '工艺路线已生成，正在自动生成技术要求...');
  setProcessRoutePanelStatus('warn', '工艺路线已生成，正在自动生成技术要求...');
  try {
    await generateTechnicalRequirements();
    scrollProcessRoutePanelToResults();
    setStatus('warn', '技术要求已生成，请确认后点击提交工艺数据');
    setProcessRoutePanelStatus('ok', '技术要求已生成，请确认后点击提交工艺数据');
  } catch (err) {
    const message = err && err.message ? err.message : String(err || '未知错误');
    state.processWorkflowState.autoRouteError = message;
    setProcessRoutePanelStatus('err', '自动生成技术要求失败: ' + message);
    setStatus('err', '第 4 步自动生成技术要求失败');
  } finally {
    state.processWorkflowState.autoGeneratingTechnical = false;
    if (_updateProcessWorkflowCards) _updateProcessWorkflowCards();
  }
}

function maybeAutoRunProcessRouteAfterInput(payload) {
  if (!state.processWorkflowState.runningAll) return false;
  if (state.processWorkflowState.activeStepId !== 'ai_process_input') return false;
  const inputKey = getProcessRouteInboxKey(payload) || 'latest';
  if (state.processWorkflowState.autoSubmittingRouteKey === inputKey) return true;
  state.processWorkflowState.autoSubmittingRouteKey = inputKey;
  state.processWorkflowState.autoRouteError = '';
  state.processWorkflowState.runningStepId = '';
  state.processWorkflowState.awaitingStepId = '';
  state.processWorkflowState.waitingUserStepId = 'ai_process_input';
  state.processRouteAwaitingInput = false;
  if (_updateProcessWorkflowCards) _updateProcessWorkflowCards();
  setStatus('warn', '已收到 AI 工艺输入 JSON，参数已自动填充，请确认参数后点击生成工艺路线');
  setProcessRoutePanelStatus('warn', '参数已自动填充，请确认参数后点击生成工艺路线');
  return true;
}


// ============================================================
// inbox 杞
// ============================================================

export function startProcessRouteInboxPolling() {
  if (state.processRouteInboxPollTimer) return;
  pollLatestProcessRouteInput(true);
  state.processRouteInboxPollTimer = window.setInterval(function() {
    pollLatestProcessRouteInput(true);
  }, 2000);
}

/**
 * 杞 3DMPS 鎺ㄩ€佺殑鏈€鏂板伐鑹鸿緭鍏?JSON)銆傗瓙 杩欐槸鐪熸鐢熸晥鐨勭増鏈? * (妯″潡鍖栧墠 IIFE 閲屽悓鍚嶆棫瀹氫箟宸茶杩欑増瑕嗙洊)銆? *
 * 鐢?`startProcessRouteInboxPolling` 姣?2s 璋冧竴娆?涔熶細琚? * `runProcessAiProcessInputStep` 閫氳繃 `scheduleProcessRouteInputPoll`
 * 鍦?250ms / 1s 鍚庢姠璺戣皟鐢?浠ュ敖鏃╂崟鑾峰搷搴斻€? *
 * 鏍稿績鍘婚噸閫昏緫:
 *  - 鐢?`getProcessRouteInboxKey(payload)` 浠?input_file / trace_id /
 *    created_at / input_json 绠楀嚭涓€涓ǔ瀹?key
 *  - 涓?`latestProcessRouteInboxKey` 姣旇緝,鐩稿悓灏辫烦杩?閬垮厤閲嶅娓叉煋)
 *  - 涓嶅悓鍒欐洿鏂?key 骞剁户缁鐞? *
 * 鏍规嵁褰撳墠鏅鸿兘浣撳拰绛夊緟鐘舵€佹湁涓夌鍒嗘敮:
 *  - 鑷姩鏅鸿兘浣?+ 姝ｅ湪绛夎緭鍏?+ 鏂?payload 涓嶆槸鍩虹嚎:瑙ｉ攣闈㈡澘 + 娓叉煋 inbox
 *  - 鑷姩鏅鸿兘浣?+ 闈㈡澘杩樻病瑙ｉ攣杩?闈欓粯 return(閬垮厤鍦ㄨ繕娌″埌绗?4 姝ユ椂鍒峰崱鐗?
 *  - 鍏跺畠鎯呭喌:鏃犳潯浠舵覆鏌?inbox 鍗＄墖(鏅€氭櫤鑳戒綋鐨勭敤鎴峰凡缁忎富鍔ㄥ睍寮€闈㈡澘)
 *
 * @param {boolean} silent true 鏃朵笉鍦ㄩ《鏍忓脊銆屽凡鏀跺埌銆嶇殑鐘舵€佹彁绀? *                       (鍚庡彴杞鏃惰 true,鎵嬪姩瑙﹀彂鏃惰 false)
 */
export function pollLatestProcessRouteInput(silent) {
  requestJson('GET', '/api/process-route/input/latest', null, function(data) {
    const payload = data && data.result ? data.result : {};
    const nextKey = getProcessRouteInboxKey(payload);
    if (!nextKey) return;
    if (nextKey === state.latestProcessRouteInboxKey) return;
    state.latestProcessRouteInboxKey = nextKey;
    state.latestProcessRouteInputPayload = payload || null;

    if (state.processRouteAwaitingInput && hasProcessRouteInput(payload) &&
        nextKey !== state.processRouteAwaitingBaseKey) {
      unlockProcessRoutePanelForInput(payload);
      if (_addProcessRouteInboxCard) _addProcessRouteInboxCard(payload);
      if (maybeAutoRunProcessRouteAfterInput(payload)) return;
      if (!silent) {
        setStatus('warn', '已收到 AI 工艺输入 JSON，请在工艺路线面板生成并提交结果');
      }
      return;
    }

    if (!state.processRoutePanelUnlocked) {
      return;
    }

    if (_addProcessRouteInboxCard) _addProcessRouteInboxCard(payload);
    if (!silent) {
      setStatus('ok', '已收到新的工艺输入 JSON');
    }
  }, function(err) {
    console.warn('[process-route-input] poll failed', err);
  }, 10000);
}

function scheduleProcessRouteInputPoll(delayMs) {
  window.setTimeout(function() {
    if (state.processRouteAwaitingInput) {
      pollLatestProcessRouteInput(true);
    }
  }, delayMs);
}

// ============================================================
// 宸ヤ綔娴佺 4 姝ャ€岃繘琛孉I宸ヨ壓鎺ㄧ悊銆嶇姸鎬佹満鍏ュ彛
// ============================================================

// 绗?4 姝ャ€岃繘琛孉I宸ヨ壓鎺ㄧ悊銆嶈嚜鍔ㄩ噸璇曠殑閰嶇疆
const PROCESS_RETRY_CONFIG = {
  maxRetries: 30,          // 第 4 步有时需要等待 3DMPS 多轮推理，放宽失败判定窗口。
  retryDelayMs: 3000,     // 重试间隔（毫秒）
  timeoutPerCall: 120,     // 姣忔璋冪敤鐨勮秴鏃讹紙绉掞級
};

// 瑙﹀彂 AI 宸ヨ壓鎺ㄧ悊鐨勬牳蹇冮€昏緫锛堟敮鎸侀噸璇曪級
function triggerAiProcessInputWithRetry(retryCount, stepId) {
  setStatus('warn', '正在触发 AI 工艺推理（第 ' + (retryCount + 1) + ' 次）...');
  scheduleProcessRouteInputPoll(500);
  scheduleProcessRouteInputPoll(2000);

  requestJson('POST', '/api/tool', JSON.stringify({
    function: 'get_ai_process_route_input',
    params: {},
    timeout: PROCESS_RETRY_CONFIG.timeoutPerCall
  }), function(data) {
    const result = data && data.result ? data.result : data;
    const directPayload = extractProcessRouteInputPayload(result);
    import('./tool_call.js').then(m => m.addToolCall('get_ai_process_route_input', {}, result));
    state.processWorkflowState.runningStepId = '';

    if (directPayload) {
      // 鎴愬姛鑾峰彇鍒版湁鏁堟暟鎹?      const directKey = getProcessRouteInboxKey(directPayload);
      if (directKey) {
        state.latestProcessRouteInboxKey = directKey;
      }
      state.latestProcessRouteInputPayload = directPayload;
      unlockProcessRoutePanelForInput(directPayload);
      if (_addProcessRouteInboxCard) _addProcessRouteInboxCard(directPayload);
      if (maybeAutoRunProcessRouteAfterInput(directPayload)) return;
      setStatus('warn', '已收到 AI 工艺输入 JSON，请在工艺路线面板生成并提交结果');
      return;
    }

    // 娌℃湁鑾峰彇鍒版湁鏁堟暟鎹紝妫€鏌ユ槸鍚﹂渶瑕侀噸璇曘€
    if (!isToolSuccess(result)) {
      if (state.processRoutePanelUnlocked) {
        return;
      }
      // 杩斿洖閿欒鏃跺噺灏戦噸璇曟鏁般€
      retryCount = Math.min(retryCount, 2);
    }

    if (retryCount < PROCESS_RETRY_CONFIG.maxRetries) {
      // 缁х画绛夊緟涓€娈垫椂闂村悗鍐嶉噸璇曘€
      setStatus('warn', '第 ' + (retryCount + 1) + ' 次未获取到数据，' + (PROCESS_RETRY_CONFIG.retryDelayMs / 1000) + ' 秒后重试...');
      state.processWorkflowState.awaitingStepId = stepId;
      if (_updateProcessWorkflowCards) _updateProcessWorkflowCards();

      window.setTimeout(function() {
        if (state.processRouteAwaitingInput && state.processWorkflowState.activeStepId === stepId) {
          triggerAiProcessInputWithRetry(retryCount + 1, stepId);
        }
      }, PROCESS_RETRY_CONFIG.retryDelayMs);
    } else {
      // 閲嶈瘯娆℃暟鐢ㄥ畬锛屾爣璁板け璐ャ€
      state.processRouteAwaitingInput = false;
      state.processRouteAwaitingBaseKey = '';
      if (_markProcessWorkflowStepIdle) _markProcessWorkflowStepIdle(stepId);
      const message = getProcessRouteToolErrorMessage(result, '触发 AI 工艺推理失败（已重试 ' + PROCESS_RETRY_CONFIG.maxRetries + ' 次）');
      addErrorMsg(message + '。请检查 3DMPS 是否正常运行，或手动点击第 4 步重试。');
      setStatus('err', message);
    }
  }, function(err) {
    if (state.processRoutePanelUnlocked) {
      return;
    }
    state.processWorkflowState.runningStepId = '';
    state.processRouteAwaitingInput = false;
    state.processRouteAwaitingBaseKey = '';
    if (_markProcessWorkflowStepIdle) _markProcessWorkflowStepIdle(stepId);
    addErrorMsg('触发 AI 工艺推理失败。' + err.message);
    setStatus('err', '触发 AI 工艺推理失败');
  }, PROCESS_RETRY_CONFIG.timeoutPerCall * 1000);
}

/**
 * 宸ヤ綔娴佺 4 姝ャ€岃繘琛孉I宸ヨ壓鎺ㄧ悊銆嶇殑鐘舵€佹満鍏ュ彛銆? *
 * 鐢ㄦ埛鐐瑰伐浣滄祦鍗′笂鐨勭 4 姝?鎴栦竴閿墽琛岃蛋鍒拌繖涓€姝?鏃惰皟鐢ㄣ€傛暣涓祦绋嬫槸
 * 涓€娆°€屾媿鍙?杞+閲嶈瘯銆嶇殑娣峰悎:鍚屾鍙戜竴涓Е鍙戣姹?鍚屾椂鍚姩鍚庡彴杞,
 * 濡傛灉娌℃湁鑾峰彇鍒版湁鏁堟暟鎹垯鑷姩閲嶈瘯,鐩村埌鑾峰彇鍒板伐鑹鸿緭鍏?JSON銆? *
 * 娴佺▼:
 *  1. 閲嶇疆绗?4 姝ョ殑 done 鐘舵€?鎶?activeStepId/runningStepId 鍒囧埌杩欎竴姝? *  2. 閿佸畾宸ヨ壓闈㈡澘,璁颁笅銆屽熀绾?inbox key銆?鐢ㄤ簬鍚庨潰鍖哄垎鏂版棫鎺ㄩ€?
 *  3. 璋冪敤 `triggerAiProcessInputWithRetry` 鎵ц瑙﹀彂鍜岄噸璇曢€昏緫
 *  4. 姣忔璋冪敤鍚庢鏌ュ搷搴?
 *     - 鐩存帴杩斿洖 payload:鐩存帴瑙ｉ攣闈㈡澘銆佸埛鏂?inbox,缁撴潫
 *     - 杩斿洖 error:鍑忓皯閲嶈瘯娆℃暟鍚庣户缁? *     - 鍟ヤ篃娌¤繑鍥?澧炲姞閲嶈瘯璁℃暟鍣?绛夊緟鍚庡啀娆¤皟鐢? *
 * 鐩稿叧鐘舵€?
 *  - `processRouteAwaitingInput`:鏍囧織鏄惁鍦ㄧ瓑 3DMPS 鎺?JSON(杞鐢?
 *  - `processRouteAwaitingBaseKey`:瑙﹀彂鏃剁殑 inbox key,鏂版帹閫佸繀椤讳笉绛変簬瀹冩墠绠楁柊
 *  - `processRoutePanelUnlocked`:闈㈡澘鏄惁宸茬粡鍥犱负鏀跺埌鏂拌緭鍏ヨ€岃В閿佽繃
 *    (鐢ㄤ簬閬垮厤 error 鍒嗘敮鎶婂凡缁忚В閿佺殑闈㈡澘鍙堥攣鍥炲幓)
 */
export function runProcessAiProcessInputStep(step) {
  const stepId = step.id;
  delete state.processWorkflowState.doneStepIds[stepId];
  state.processWorkflowState.activeStepId = stepId;
  state.processWorkflowState.runningStepId = stepId;
  state.processWorkflowState.awaitingStepId = '';
  state.processRoutePanelManuallyClosed = false;
  state.processRoutePanelUnlocked = false;
  state.processRouteAwaitingInput = true;
  state.processRouteAwaitingBaseKey = state.latestProcessRouteInboxKey || getProcessRouteInboxKey(state.latestProcessRouteInputPayload) || '';
  updateProcessRoutePanelVisibility();
  if (_updateProcessWorkflowCards) _updateProcessWorkflowCards();
  addUserMsg(step.prompt);

  // 鍚姩甯﹂噸璇曠殑瑙﹀彂閫昏緫
  triggerAiProcessInputWithRetry(0, stepId);
}

// ============================================================
// 鍏ュ彛鐢?entry 璋?鍔ㄤ綔鎸夐挳鐨勪簨浠?handler
// ============================================================

export const processRouteActions = {
  onGenerateClick: function() { generateProcessRoute().catch(function() {}); },
  onTechnicalClick: function() { generateTechnicalRequirements().catch(function() {}); },
  onSubmitClick: function() { submitLatestProcessRoute().catch(function() {}); },
  onRouteTabClick: function() {
    setProcessRouteResultView('route');
    syncProcessRouteActionRows();
  },
  onTechnicalTabClick: function() {
    setProcessRouteResultView('technical');
    syncProcessRouteActionRows();
  },
  onMoreClick: function() {
    if (!dom.prMetaInfo) return;
    const isHidden = dom.prMetaInfo.style.display === 'none' || !dom.prMetaInfo.textContent;
    if (isHidden) {
      setPrMetaInfo(state.latestProcessRouteInputPayload);
      dom.prMetaInfo.style.display = '';
    } else {
      dom.prMetaInfo.style.display = 'none';
    }
  },
  onCloseClick: function() {
    closeProcessRoutePanel(true);
  },
  onBackdropClick: function() {
    closeProcessRoutePanel(true);
  },
  onParamsChange: function() { handleProcessRouteParamsChange(); },
};
