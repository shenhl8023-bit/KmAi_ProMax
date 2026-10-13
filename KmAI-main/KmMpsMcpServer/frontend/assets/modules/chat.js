// chat.js —— 聊天主循环 + 智能体管理。
//
// 负责:
//   1. 智能体列表加载和切换(把 select 里的项和后端 /api/agents 拉过来的对齐)
//   2. `send()` —— 流式聊天,POST /api/chat/stream,逐 chunk 渲染到 #log
//   3. `sendProcessWorkflowPrompt()` —— workflow 一键执行时复用的「模拟用户输入」
//
// 跟 workflow.js 的边界:workflow 不直接发请求,而是拼一个 prompt 字符串
// 调 `sendProcessWorkflowPrompt`,由本模块负责发。这样流式响应、tool_call
// 渲染、ping 这些都走同一套路径。

import {
  state, dom, escapeHtml, setStatus, addUserMsg,
  requestJson, ping, getStoredAgentId, setStoredAgentId,
  PROCESS_AUTO_AGENT_ID, KMRAG_AGENT_ID, getTimeStr, getApiToken,
} from './shared.js';

// 在 entry.js 里 setSelectedAgent 会调 addProcessWorkflowCard(workflow 模块提供),
// 通过这个 setter 在 chat.js 里注入,避免循环 import。
let _addProcessWorkflowCard = null;
let _showProcessAutoWorkflow = null;
let _showDefaultAssistantIntro = null;
let _resetProcessRoutePanelFlowState = null;
let _chatRequestInFlight = false;

export function setChatDeps(deps) {
  _addProcessWorkflowCard = deps.addProcessWorkflowCard;
  _showProcessAutoWorkflow = deps.showProcessAutoWorkflow;
  _showDefaultAssistantIntro = deps.showDefaultAssistantIntro;
  _resetProcessRoutePanelFlowState = deps.resetProcessRoutePanelFlowState;
}

// ============================================================
// 智能体管理
// ============================================================

export function getSelectedAgentName() {
  const mappedName = state.agentNamesById[state.currentAgentId];
  if (mappedName) return mappedName;
  const option = dom.agentSelect.options[dom.agentSelect.selectedIndex];
  return option ? option.text : state.currentAgentId;
}

function fillAgentOptions(agents) {
  const items = Array.isArray(agents) && agents.length ? agents : [{ id: 'default', name: '默认助手' }];
  dom.agentSelect.innerHTML = '';
  state.agentNamesById = {};
  items.forEach(function(agent) {
    state.agentNamesById[agent.id || 'default'] = agent.name || agent.id || 'default';
    const option = document.createElement('option');
    option.value = agent.id || 'default';
    option.textContent = agent.name || agent.id || 'default';
    option.title = agent.description || '';
    dom.agentSelect.appendChild(option);
  });
}

/** 拉 /api/agents 填 select,完成后用 localStorage 里存的上次选择初始化。 */
export function loadAgents() {
  requestJson('GET', '/api/agents', null, function(data) {
    const agents = data && data.agents ? data.agents : [];
    fillAgentOptions(agents);
    setSelectedAgent(getStoredAgentId(), true);
  }, function(err) {
    fillAgentOptions(null);
    setSelectedAgent('default', true);
    console.warn('[agents] load failed', err);
  }, 15000);
}

function saveCurrentAgentLog() {
  if (!dom.log || !state.currentAgentId) return;
  state.agentLogSnapshots[state.currentAgentId] = dom.log.innerHTML;
}

function restoreAgentLog(agentId) {
  if (!dom.log) return false;
  const snapshot = state.agentLogSnapshots[agentId || 'default'];
  if (snapshot === undefined) {
    dom.log.innerHTML = '';
    return false;
  }
  dom.log.innerHTML = snapshot;
  dom.log.scrollTop = dom.log.scrollHeight;
  return true;
}

function syncManualChatInputState() {
  const manualInputDisabled = state.currentAgentId === PROCESS_AUTO_AGENT_ID;
  dom.input.disabled = manualInputDisabled;
  dom.sendBtn.disabled = manualInputDisabled || _chatRequestInFlight;

  if (manualInputDisabled) {
    dom.input.placeholder = '当前工作流无需输入';
  } else if (state.currentAgentId === KMRAG_AGENT_ID) {
    dom.input.placeholder = '例如：自动识别怎么使用';
  } else {
    dom.input.placeholder = '例如：读取当前BOF';
  }
}

/**
 * 切换智能体。这是模块化后唯一一份定义(以前 IIFE 里同一函数有两次,
 * 后一次覆盖前一次;模块化后这个隐患自然消失)。
 *
 * 行为:
 *   - 自动智能体:清空聊天 → 进入 process-auto 工作流
 *   - 普通智能体:面板复位 → 始终显示工作流 dock(任何智能体下都可点工艺面板)
 */
export function setSelectedAgent(agentId, silent) {
  const nextId = agentId || 'default';
  const previousAgentId = state.currentAgentId || 'default';
  let hasOption = false;
  for (let i = 0; i < dom.agentSelect.options.length; i++) {
    if (dom.agentSelect.options[i].value === nextId) {
      dom.agentSelect.selectedIndex = i;
      hasOption = true;
      break;
    }
  }
  if (!hasOption && dom.agentSelect.options.length > 0) {
    dom.agentSelect.selectedIndex = 0;
  }
  const selectedAgentId = dom.agentSelect.value || 'default';
  const agentChanged = selectedAgentId !== previousAgentId;
  if (agentChanged) {
    saveCurrentAgentLog();
  }
  state.currentAgentId = selectedAgentId;
  setStoredAgentId(state.currentAgentId);
  if (agentChanged) {
    restoreAgentLog(state.currentAgentId);
  }

  if (state.currentAgentId === PROCESS_AUTO_AGENT_ID) {
    if (_showProcessAutoWorkflow) _showProcessAutoWorkflow();
  } else {
    // 默认助手和普通智能体分开展示，避免把普通 agent 误标成“默认助手”。
    if (_resetProcessRoutePanelFlowState) _resetProcessRoutePanelFlowState();
    state.processRoutePanelManuallyClosed = false;
    const shouldShowDefaultIntro = state.currentAgentId === 'default' && _showDefaultAssistantIntro;
    if (shouldShowDefaultIntro) {
      _showDefaultAssistantIntro();
    } else {
      dom.workflowDock.innerHTML = '';
      dom.workflowDock.style.display = state.currentAgentId === KMRAG_AGENT_ID ? 'none' : '';
    }
  }
  syncManualChatInputState();
  saveCurrentAgentLog();
}

// ============================================================
// 聊天发送 + 流式接收
// ============================================================

/** workflow 一键执行时复用 send(),把 prompt 写到输入框再触发。 */
export async function sendProcessWorkflowPrompt(promptText) {
  dom.input.value = promptText;
  return await send();
}

/** 把 prompt 写到输入框并立即发送,目前没有 UI 入口,保留以备扩展。 */
export function quick(text) {
  dom.input.value = text;
  send();
}

/**
 * 发送聊天消息并流式接收回复。
 *
 * 这是整个对话界面的「主循环入口」,被输入框回车和发送按钮的 click 监听
 * 调用,也通过 `sendProcessWorkflowPrompt` 被工作流一键执行复用。
 *
 * 协议:POST /api/chat/stream 返回 SSE 响应,每条消息格式为:
 *   data: {"type":"content","text":"片段"}\n\n
 *   data: {"type":"tool_call","tool":"...","args":...,"result":...}\n\n
 *   data: {"type":"error","message":"..."}\n\n
 *   data: [DONE]\n\n
 *
 * 关键实现点:
 *  1. **流控制**:用 `reader.read()` 拉流式 chunk,按 `\n` 切行处理。
 *     用 `buffer` 跨 chunk 暂存「半截行」(SSE 可能在任意字节边界断)。
 *  2. **`[DONE]` 显式终止**:服务端发 `[DONE]` 后立刻跳出循环,不再等
 *     `reader.read()` 返回 done:true(否则会卡在「生成中」状态)。
 *  3. **光标动画**:流式过程中在 bot 气泡末尾追一个 `<span class="cursor">`,
 *     它由 CSS 的 blink 动画闪烁;流结束或出错时把光标替换为最终文本/错误。
 *  4. **tool_call 旁路渲染**:JSON 里遇到 `tool_call` 类型时由 tool_call.js
 *     渲染为可视化卡片(候选 / XML 编辑器),不混入文本气泡。
 *  5. **错误兜底**:HTTP 4xx/5xx、JSON 解析失败、error 类型消息都会被
 *     捕获并显示在气泡里(红字);finally 块会按当前智能体恢复输入控件状态。
 *  6. **完成时 ping**:成功后重新调一次 `/api/health` 刷新顶栏 LLM 状态显示。
 *
 * @returns {Promise<boolean>} true=成功收到回复,false=空消息/出错
 */
export async function send() {
  const message = dom.input.value.trim();
  if (!message) {
    console.log('[send] empty message, ignored');
    return false;
  }
  dom.input.value = '';
  _chatRequestInFlight = true;
  syncManualChatInputState();
  addUserMsg(message);
  console.log('[send] POST /api/chat/stream, message:', message);

  // 使用方案 B 商务卡片风格：头像 + 时间戳 + 气泡
  const botDiv = document.createElement('div');
  botDiv.className = 'msg bot';
  botDiv.innerHTML =
    '<div class="avatar bot">沐</div>' +
    '<div class="bubble-wrap">' +
      '<div class="msg-meta">AI 助手 · ' + getTimeStr() + '</div>' +
      '<div class="bubble"><span class="stream-status">正在理解问题...</span><span class="cursor"></span></div>' +
    '</div>';
  dom.log.appendChild(botDiv);
  dom.log.scrollTop = dom.log.scrollHeight;

  setStatus('warn', '正在理解问题...');

  let fullText = '';

  function renderStreamStatus(text) {
    const bubble = botDiv.querySelector('.bubble');
    if (!bubble || fullText) return;
    bubble.innerHTML = '<span class="stream-status">' + escapeHtml(text) + '</span><span class="cursor"></span>';
    dom.log.scrollTop = dom.log.scrollHeight;
  }

  let reader = null;
  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-KmAI-Token': getApiToken() },
      body: JSON.stringify({ message: message, session_id: state.sessionId, agent_id: state.currentAgentId })
    });
    console.log('[send] response status:', resp.status, resp.statusText);

    if (!resp.ok) {
      let errBody = '';
      try { errBody = await resp.text(); } catch (e) { /* ignore */ }
      throw new Error('HTTP ' + resp.status + (errBody ? ' · ' + errBody.slice(0, 200) : ''));
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let streamError = '';
    let chunkCount = 0;
    // [DONE] 是服务端明确的流结束信号。收到后立即跳出 while 循环,
    // 否则会一直等 reader.read() 返回 done:true，导致状态卡在「生成中」
    let serverDone = false;

    while (!serverDone) {
      const { done, value } = await reader.read();
      if (done) {
        console.log('[send] stream done (server closed), total chunks:', chunkCount);
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      const NL = String.fromCharCode(10);
      const lines = buffer.split(NL);
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line || !line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') {
          console.log('[send] received [DONE], ending stream');
          serverDone = true;
          continue;
        }
        let obj;
        try {
          obj = JSON.parse(data);
        } catch (parseErr) {
          console.warn('[send] json parse error, data:', data, parseErr);
          continue;
        }
        if (obj.type === 'content') {
          fullText += obj.text;
          chunkCount++;
          const bubble = botDiv.querySelector('.bubble');
          if (bubble) {
            bubble.innerHTML = escapeHtml(fullText) + '<span class="cursor"></span>';
          }
          dom.log.scrollTop = dom.log.scrollHeight;
        } else if (obj.type === 'status') {
          renderStreamStatus(obj.text || '正在处理...');
          setStatus('warn', obj.text || '正在处理...');
        } else if (obj.type === 'tool_call') {
          // 动态 import 避免 chat.js ↔ tool_call.js 循环依赖
          const { addToolCall } = await import('./tool_call.js');
          addToolCall(obj.tool, obj.args, obj.result);
        } else if (obj.type === 'error') {
          streamError = obj.message || '调用失败';
          botDiv.className = 'msg bot error';
          botDiv.innerHTML = '<div class="bubble error">' + escapeHtml(streamError) + '</div>';
          setStatus('err', '调用失败');
          serverDone = true;
        }
      }
    }

    if (streamError) {
      const bubble = botDiv.querySelector('.bubble');
      if (bubble) {
        bubble.className = 'bubble error';
        bubble.innerHTML = escapeHtml(streamError);
      } else {
        botDiv.innerHTML = '<div class="bubble error">' + escapeHtml(streamError) + '</div>';
      }
      return false;
    } else {
      const bubble = botDiv.querySelector('.bubble');
      if (bubble) {
        bubble.innerHTML = escapeHtml(fullText) || '<i>（无回复）</i>';
      } else {
        botDiv.innerHTML = '<div class="bubble">' + (escapeHtml(fullText) || '<i>（无回复）</i>') + '</div>';
      }
      // 重新检查服务状态
      ping();
      return true;
    }
  } catch (err) {
    console.error('[send] error', err);
    const bubble = botDiv.querySelector('.bubble');
    if (bubble) {
      bubble.className = 'bubble error';
      bubble.innerHTML = '<span style="color:#ef4444">调用失败: ' + escapeHtml(err.message) + '</span>';
    } else {
      botDiv.innerHTML = '<div class="bubble error"><span style="color:#ef4444">调用失败: ' + escapeHtml(err.message) + '</span></div>';
    }
    setStatus('err', '调用失败');
    return false;
  } finally {
    if (reader) {
      try { reader.releaseLock(); } catch (e) { /* ignore */ }
    }
    _chatRequestInFlight = false;
    syncManualChatInputState();
    if (!dom.input.disabled) dom.input.focus();
  }
}
