# 移除 KMRAG 介绍面板实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 KMRAG 助手顶部介绍面板，让聊天记录直接占用主内容区。

**Architecture:** 保留 KMRAG Agent、会话隔离和专属输入提示，仅删除 KMRAG 介绍面板的渲染函数及依赖注入。默认助手介绍和工艺助手工作流继续沿用现有分支与样式。

**Tech Stack:** 原生 ES Module JavaScript、Python `unittest` 静态前端契约测试。

## Global Constraints

- 不引入新依赖或构建步骤。
- 不修改 KMRAG 后端、检索能力、会话隔离和输入提示。
- 不影响默认助手介绍区和工艺自动生成工作流。
- 保留工作区中已有的用户修改，不执行 Git 提交。

---

### Task 1: 移除 KMRAG 专属介绍面板

**Files:**
- Modify: `KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`
- Modify: `tests/test_frontend_assets.py`
- Modify: `KmMpsMcpServer/frontend/assets/modules/chat.js`
- Modify: `KmMpsMcpServer/frontend/assets/modules/entry.js`
- Modify: `KmMpsMcpServer/frontend/assets/modules/workflow.js`

**Interfaces:**
- Consumes: `KMRAG_AGENT_ID = "kmrag-knowledge-agent"`，继续用于 KMRAG 输入提示。
- Produces: KMRAG 助手进入普通非默认 Agent 分支，清空 `workflowDock` 后直接显示聊天区。

- [x] **Step 1: 写失败的前端契约测试**

将 KMRAG UI 边界测试改为断言 `showKmragKnowledgeIntro` 不再出现在 `chat.js`、`entry.js` 和 `workflow.js`，同时保留 KMRAG 输入提示断言。

- [x] **Step 2: 运行测试并确认失败**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_default_assistant_ui_boundaries -v
Pop-Location
python -B -m unittest tests.test_frontend_assets -v
```

Expected: 旧实现仍包含 `showKmragKnowledgeIntro`，测试失败。

- [x] **Step 3: 删除 KMRAG 介绍面板实现和接线**

从 `workflow.js` 删除 `KMRAG_ASSISTANT_CAPABILITIES` 和 `showKmragKnowledgeIntro()`；从 `chat.js`、`entry.js` 删除对应依赖注入和导出。KMRAG 助手沿用普通 Agent 的空 `workflowDock` 分支。

- [x] **Step 4: 运行定向测试和项目验证**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_default_assistant_ui_boundaries tests.test_chat_input_placeholder -v
Pop-Location
python -B -m unittest tests.test_frontend_assets -v
git diff --check
python -m compileall -q KmMpsMcpServer tests
```

Expected: 全部通过，且无空白错误或编译错误。
