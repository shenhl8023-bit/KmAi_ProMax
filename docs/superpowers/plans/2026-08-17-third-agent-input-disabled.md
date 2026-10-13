# 第三个智能体输入禁用实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 禁用第三个智能体的人工聊天输入，同时保留工作流自动发送能力。

**Architecture:** 在现有 `chat.js` 的智能体切换边界增加一个按固定智能体 ID 同步输入控件状态的函数。发送请求完成后复用该同步函数，避免自动工作流请求的清理逻辑重新启用人工控件。

**Tech Stack:** 原生 ES Module JavaScript、HTML DOM、Python `unittest`、Node.js 模块行为测试。

## Global Constraints

- 复用现有 `PROCESS_AUTO_AGENT_ID`，不按下拉选项顺序判断。
- 不引入新的前端依赖或构建步骤。
- 保留 `sendProcessWorkflowPrompt` 的程序化发送路径。
- 不修改工作区中已有的无关改动，仅在用户明确授权后执行 commit/push。

---

### Task 1: 添加第三个智能体输入状态的失败测试

**Files:**
- Modify: `KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`

**Interfaces:**
- Consumes: `chat.js` 导出的 `setSelectedAgent` 和共享 `dom`/`state`。
- Produces: 一个可复现第三个智能体禁用、普通智能体恢复的 Node.js 行为测试。

- [x] **Step 1: Write the failing test**

在现有 `DefaultAssistantUiBoundaryTest` 中增加 Node.js 行为测试，导入 `chat.js` 与 `shared.js`，用最小 DOM stub 提供 `agentSelect`、`input`、`sendBtn`、`workflowDock` 和日志所需成员；先调用 `setSelectedAgent('process-auto-generate-agent', true)`，断言输入框和发送按钮禁用，再调用 `setSelectedAgent('default', true)`，断言二者恢复可用。

- [x] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m unittest KmMpsMcpServer.tests.test_default_assistant_ui_boundaries.DefaultAssistantUiBoundaryTest.test_process_auto_agent_disables_manual_chat_input -v`

Expected: FAIL because the current `setSelectedAgent` does not set either chat control's `disabled` property.

### Task 2: 实现输入控件状态同步

**Files:**
- Modify: `KmMpsMcpServer/frontend/assets/modules/chat.js:95-139, 325-331`

**Interfaces:**
- Consumes: `state.currentAgentId`, `PROCESS_AUTO_AGENT_ID`, `dom.input`, `dom.sendBtn`。
- Produces: `syncManualChatInputState()`，按当前智能体同步两个原生禁用状态和第三个智能体的占位提示。

- [x] **Step 1: Write minimal implementation**

增加 `syncManualChatInputState()`：当 `state.currentAgentId === PROCESS_AUTO_AGENT_ID` 时设置 `dom.input.disabled = true`、`dom.sendBtn.disabled = true`，并把占位文字设为“当前工作流无需输入”；其他智能体设置两个 `disabled` 为 `false`，保留现有默认/KMRAG 占位文字。`setSelectedAgent` 在更新 `state.currentAgentId` 后调用它；`send()` 的 `finally` 用它替换无条件的 `dom.sendBtn.disabled = false`。

- [x] **Step 2: Run the focused test**

Run: `py -3.14 -m unittest KmMpsMcpServer.tests.test_default_assistant_ui_boundaries.DefaultAssistantUiBoundaryTest.test_process_auto_agent_disables_manual_chat_input -v`

Expected: PASS, including the switch-back assertions.

### Task 3: 执行回归验证

**Files:**
- Test only: `KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`
- Test only: `KmMpsMcpServer/tests/test_chat_input_placeholder.py`

- [x] **Step 1: Run related frontend boundary tests**

Run: `py -3.14 -m unittest KmMpsMcpServer.tests.test_default_assistant_ui_boundaries KmMpsMcpServer.tests.test_chat_input_placeholder -v`

Result: the 15 tests in `test_default_assistant_ui_boundaries.py` pass. The adjacent placeholder suite retains one pre-existing KMRAG copy mismatch: it expects “查询公司的供应商准入流程” while the current product copy is “自动识别怎么使用”.

- [x] **Step 2: Run static verification**

Run: `py -3.14 -m compileall -q KmMpsMcpServer tests; git diff --check`

Expected: exit code 0 and no diff whitespace errors.

- [x] **Step 3: Inspect final scope**

Run: `git status --short; git diff -- KmMpsMcpServer/frontend/assets/modules/chat.js KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`

Expected: only the requested frontend behavior, its regression test, and the two task documents are newly changed; existing unrelated changes remain untouched.
