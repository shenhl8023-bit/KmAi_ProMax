// entry.js —— 前端入口。
//
// 负责:
//   1. 初始化 DOM 引用(domRefs)
//   2. 把跨模块的方法注入(打破循环依赖)
//   3. 绑定所有静态 DOM 事件
//   4. 启动时初始化(拉智能体、ping、画工作流、启动轮询、显示欢迎语)
//
// 模块依赖图(只列静态 import;动态 import 用于避免循环):
//   shared.js  ←←← chat.js / tool_call.js / model_config.js / process_route.js / workflow.js
//   tool_call.js ←(setter)← process_route.js
//   process_route.js ←(setter)← chat.js / workflow.js
//   workflow.js ←(setter)← chat.js
//
// 「setter 注入」在所有 import 完成后、绑定事件前调一次,这样各模块在被调
// 用时,需要的 cross-module 函数已经就位。

import {
  initDomRefs, dom, addBotMsg, ping, startKm3dmpsExitMonitor, state, setStatus,
} from './shared.js';

import { loadAgents, setSelectedAgent, send } from './chat.js';
import { setChatDeps } from './chat.js';
import { openModelConfig } from './model_config.js';
import {
  addToolCall, addProcessRouteInboxCard,
  syncProcessRouteInboxCardVisibility, openXmlEditor, openOptionCardEditor,
  setToolCallDeps,
} from './tool_call.js';
import {
  startProcessRouteInboxPolling, resetProcessRoutePanelFlowState, updateProcessRouteInputMeta,
  setProcessRouteAdvancedOpen, closeProcessRoutePanel, processRouteActions,
  setProcessRouteDeps,
} from './process_route.js';
import {
  addProcessWorkflowCard, showProcessAutoWorkflow, showDefaultAssistantIntro,
  markProcessWorkflowStepDone, markProcessWorkflowStepIdle,
  updateProcessWorkflowCards,
} from './workflow.js';

// ============================================================
// 1. 初始化 DOM 引用
// ============================================================

initDomRefs();

// ============================================================
// 2. 跨模块 setter 注入(打破循环依赖)
// ============================================================

// tool_call 需要 workflow 的「标记步骤 done / idle」
setToolCallDeps({
  markProcessWorkflowStepDone,
  markProcessWorkflowStepIdle,
});

// process_route 需要 tool_call 的「渲染 inbox 卡片」+ workflow 的「更新卡片 / 标记步骤」
setProcessRouteDeps({
  addProcessRouteInboxCard,
  updateProcessWorkflowCards,
  markProcessWorkflowStepDone,
  markProcessWorkflowStepIdle,
});

// chat 需要 workflow 的「添加工作流卡 / 显示自动智能体工作流」+ process_route 的「复位面板状态」
setChatDeps({
  addProcessWorkflowCard,
  showProcessAutoWorkflow,
  showDefaultAssistantIntro,
  resetProcessRoutePanelFlowState,
});

// ============================================================
// 3. 绑定静态事件
// ============================================================

function bindEvents() {
  // 发送按钮 + 输入框回车 → send()
  dom.sendBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    console.log('[event] sendBtn click');
    send();
  });
  dom.input.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      console.log('[event] input Enter');
      send();
    }
  });

  // 顶栏:模型配置 / 测试连接 / 智能体切换
  dom.configBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    openModelConfig();
  });
  dom.testBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    console.log('[event] testBtn click');
    ping();
  });
  dom.agentSelect.addEventListener('change', function() {
    setSelectedAgent(dom.agentSelect.value, false);
    dom.input.focus();
  });

  // 顶栏调试开关:开启时显示工具调用 details / JSON 预览,关闭时只渲染可视化卡片
  const debugToggleBtn = document.getElementById('debugToggleBtn');
  if (debugToggleBtn) {
    const updateDebugBtnVisual = function() {
      if (state.debugMode) {
        debugToggleBtn.classList.add('is-active');
        debugToggleBtn.setAttribute('aria-pressed', 'true');
        debugToggleBtn.title = '关闭调试信息';
      } else {
        debugToggleBtn.classList.remove('is-active');
        debugToggleBtn.setAttribute('aria-pressed', 'false');
        debugToggleBtn.title = '显示调试信息';
      }
    };
    updateDebugBtnVisual();
    debugToggleBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      state.debugMode = !state.debugMode;
      updateDebugBtnVisual();
      syncProcessRouteInboxCardVisibility();
      setStatus(state.debugMode ? 'ok' : 'ok',
        state.debugMode ? '已开启调试信息(显示工具调用 / JSON 预览)' : '已关闭调试信息(隐藏工具调用 / JSON 预览)');
    });
  }

  // 工艺路线面板按钮
  dom.processRouteGenerateBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    processRouteActions.onGenerateClick();
  });
  dom.processRouteTechnicalBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    processRouteActions.onTechnicalClick();
  });
  dom.processRouteSubmitBtn.addEventListener('click', function(ev) {
    ev.preventDefault();
    processRouteActions.onSubmitClick();
  });
  if (dom.processRouteRouteTab) {
    dom.processRouteRouteTab.addEventListener('click', function(ev) {
      ev.preventDefault();
      processRouteActions.onRouteTabClick();
    });
  }
  if (dom.processRouteTechnicalTab) {
    dom.processRouteTechnicalTab.addEventListener('click', function(ev) {
      ev.preventDefault();
      processRouteActions.onTechnicalTabClick();
    });
  }
  if (dom.prMoreBtn) {
    dom.prMoreBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      processRouteActions.onMoreClick();
    });
  }
  if (dom.prCloseBtn) {
    dom.prCloseBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      processRouteActions.onCloseClick();
    });
  }
  if (dom.processRoutePanelBackdrop) {
    dom.processRoutePanelBackdrop.addEventListener('click', function() {
      processRouteActions.onBackdropClick();
    });
  }
  if (dom.processRouteMaterialGrade) {
    dom.processRouteMaterialGrade.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRoutePartType) {
    dom.processRoutePartType.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRouteHeatTreatment) {
    dom.processRouteHeatTreatment.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRouteInspectionItems) {
    dom.processRouteInspectionItems.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRouteMarkingMethods) {
    dom.processRouteMarkingMethods.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRouteFlagShapedHole) {
    dom.processRouteFlagShapedHole.addEventListener('change', processRouteActions.onParamsChange);
  }
  if (dom.processRouteFlagPostStageHole) {
    dom.processRouteFlagPostStageHole.addEventListener('change', processRouteActions.onParamsChange);
  }
  Array.from(document.querySelectorAll('[data-surface]')).forEach(function(el) {
    el.addEventListener('change', processRouteActions.onParamsChange);
  });

  // 窗口失焦后 refocus 回输入框,避免 Enter 失效
  window.addEventListener('blur', function() {
    setTimeout(function() { dom.input.focus(); }, 0);
  });
}

// ============================================================
// 4. 启动初始化
// ============================================================

function bootstrap() {
  bindEvents();

  // 初始面板状态
  setProcessRouteAdvancedOpen(false);
  closeProcessRoutePanel(false);
  updateProcessRouteInputMeta(null);

  // 页面加载时先渲染默认助手说明卡,后续由智能体选择决定是否切换为工艺工作流
  showDefaultAssistantIntro();
  dom.input.focus();

  // 启动时检查连接
  loadAgents();
  ping();
  startKm3dmpsExitMonitor();
  startProcessRouteInboxPolling();

  // 欢迎语 —— llm_status 由 web_page.py 注入到 window.__LLM_STATUS__,
  // 缺失时退回到「已启用」文案只是为了不显示 undefined,真实部署里 window 一定被设了。
  const llmStatus = (typeof window !== 'undefined' && window.__LLM_STATUS__) || '已启用 LLM 智能对话模式。';
  addBotMsg('已启用 AI 小沐 Agent。' + llmStatus);
}

// 整个脚本在 <script type="module"> 里,默认就是 DOMContentLoaded 之后才执行,
// 所以 bootstrap 直接调就行,不需要再包一层 DOMContentLoaded 监听。
bootstrap();

// 暴露给 browser console 调试用(开发期方便,生产不影响)
if (typeof window !== 'undefined') {
  window.__kmai__ = {
    shared: { dom },
    chat: { loadAgents, setSelectedAgent, send },
    toolCall: { addToolCall, openXmlEditor, openOptionCardEditor, addProcessRouteInboxCard },
    modelConfig: { openModelConfig },
    processRoute: {
      startProcessRouteInboxPolling,
      resetProcessRoutePanelFlowState,
      updateProcessRouteInputMeta,
      closeProcessRoutePanel,
    },
    workflow: {
      addProcessWorkflowCard, showProcessAutoWorkflow, showDefaultAssistantIntro,
      markProcessWorkflowStepDone, markProcessWorkflowStepIdle,
      updateProcessWorkflowCards,
    },
  };
}
