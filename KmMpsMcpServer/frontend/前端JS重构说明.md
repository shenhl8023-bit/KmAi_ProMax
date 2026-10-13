# 前端 JS 模块化重构说明

本文档记录 `frontend/assets/` 下从「单体 IIFE」拆到「ES Module + 静态文件路由」的完整改造,以及对应的 Python 侧改动。

## 一、改造背景

改造前,前端代码全部挤在 `frontend/assets/app.js` 一个 2756 行的 IIFE 里,带来三个具体问题:

1. **函数重复定义**:`pollLatestProcessRouteInput`、`setSelectedAgent`、`showProcessAutoWorkflow`、`resetProcessWorkflowState`、`getProcessWorkflowStepMeta`、`updateProcessWorkflowCards`、`markProcessWorkflowStepDone`、`markProcessWorkflowStepIdle`、`runProcessWorkflowStep` 这 9 个函数都在文件里出现两次,后定义者覆盖前定义者。靠 JS 函数提升兜着没崩,但改的是上面的版本、跑的是下面的版本,排查极痛苦。
2. **状态散落**:11 个 `let` 顶层变量(`currentAgentId`、`latestProcessRouteInputPayload`、`processRoutePanelUnlocked`、`processWorkflowState` 等)各自为政,谁改了谁很难追。
3. **DOM 引用分散**:51 个 `getElementById` 调用散落各处,每次加新元素都要翻几百行找 ID。

## 二、改造后的文件结构

```
frontend/assets/
├── index.html                       # 改为 <script type="module" src="/assets/modules/entry.js">
├── css/                             # 9 个 CSS 文件(本次未动)
├── modules/                         # 新增:7 个 ES Module
│   ├── shared.js                    # state、dom、escapeHtml、requestJson、ping、DOM refs
│   ├── chat.js                      # send()、智能体切换、流式响应
│   ├── tool_call.js                 # 候选卡 / XML 编辑器 / 工艺输入 inbox
│   ├── model_config.js              # 顶栏「模型配置」弹窗
│   ├── process_route.js             # 工艺面板 + 3 个按钮 + 后台轮询 + 第 4 步状态机
│   ├── workflow.js                  # 5 步状态机 + 工作流 dock + 一键执行
│   └── entry.js                     # 入口:DOM 初始化 + setter 注入 + 事件绑定 + 启动
└── style.css                        # 旧版 CSS 占位,当前运行入口不引用
```

7 个模块按职责切分,文件大小从 2756 行的单体降到每个模块 100 ~ 900 行。
旧版单体 `app.js` 已从发布目录移除,避免与模块化入口并存。

## 三、模块职责边界

| 模块 | 单一职责 | 对外导出 | 跨模块依赖 |
|------|---------|---------|-----------|
| **shared.js** | 共享 state、DOM refs、工具函数 | `state`、`dom`、`initDomRefs`、`escapeHtml`、`requestJson`、`callTool`、`ping` 等 | 无(根模块) |
| **chat.js** | 聊天主循环 + 智能体管理 | `send`、`loadAgents`、`setSelectedAgent`、`sendProcessWorkflowPrompt` | workflow(注入) + process_route(注入) |
| **tool_call.js** | 工具调用结果可视化渲染 | `addToolCall`、`addOptionCards`、`openXmlEditor`、`addProcessRouteInboxCard` | workflow(注入) |
| **model_config.js** | 顶栏模型配置弹窗 | `openModelConfig` | 仅 shared |
| **process_route.js** | 工艺路线面板 + 后台轮询 + 第 4 步状态机 | `openProcessRoutePanel`、`closeProcessRoutePanel`、`pollLatestProcessRouteInput`、`runProcessAiProcessInputStep`、`processRouteActions` | tool_call(注入) + workflow(注入) |
| **workflow.js** | 5 步工作流 dock + 状态机 + 一键执行 | `addProcessWorkflowCard`、`showProcessAutoWorkflow`、`updateProcessWorkflowCards`、`markProcessWorkflowStepDone/Idle`、`runProcessWorkflowAllSteps` | process_route(动态 import) + chat(动态 import) + tool_call(动态 import) |
| **entry.js** | 入口装配 | 无导出 | 全部 |

## 四、循环依赖处理

3 处循环依赖全部用「setter 注入」模式解决:

- `tool_call → workflow`:卡片点击后要标记步骤 done/idle
- `process_route → tool_call`:轮询捕获到新 input 后要渲染 inbox 卡片
- `process_route → workflow`:第 4 步触发后要更新工作流卡

`entry.js` 在顶层、绑定事件前一次性注入:

```js
setToolCallDeps({ markProcessWorkflowStepDone, markProcessWorkflowStepIdle });
setProcessRouteDeps({ addProcessRouteInboxCard, updateProcessWorkflowCards, ... });
setChatDeps({ addProcessWorkflowCard, showProcessAutoWorkflow, ... });
```

每个模块文件顶部声明 `let _xxx = null;` 的占位变量,setter 调用时填进去。模块被调用时,跨模块函数已经就位。

运行时(非启动时)的跨模块调用用 `import()` 动态导入。已加载的模块从 ES Module 缓存返回,无网络/解析开销,只多一个微任务的 `.then`。

## 五、Python 侧改动

### `frontend/web_page.py`

- 不再内联 JS(原来读 `app.js` 然后拼到 `<script>{{app_js}}</script>`)
- 保留 CSS 内联(`{{style}}` 占位符和 `css/` 目录下的 9 个文件拼接)
- 新增 `{{llm_status_json}}` 占位符,运行时注入 `window.__LLM_STATUS__ = "..."`
- 启动时 fail-fast 检查 `assets/modules/entry.js` 存在,缺失立即报错

### `backend/http_api.py`

新增 `GET /assets/*` 静态文件路由,带路径穿越防护和 MIME 映射:

```python
def _serve_static_asset(self):
    rel = self.path[len("/assets/"):]
    rel = urllib_unquote(rel)
    if ".." in rel.split("/"):  # 防 ../ 越权
        self._send_json(403, ...)
        return
    target = os.path.normpath(os.path.join(_ASSETS_DIR, rel))
    if os.path.commonpath([_ASSETS_DIR, target]) != _ASSETS_DIR:  # 最终路径必须仍在 _ASSETS_DIR 里
        self._send_json(403, ...)
        return
    # ... 读文件 + 按扩展名返回 MIME
```

`do_GET` 里在路由表前面插入 `if self.path.startswith("/assets/"): self._serve_static_asset()`,优先匹配。

## 六、保留的关键业务逻辑

下列逻辑和原 IIFE 完全等价,只是物理位置换了:

1. **`process_route.runProcessAiProcessInputStep`**:第 4 步「拍发+轮询」混合策略、3 分支判断(`directPayload` / `error` / 啥也没返回)、`scheduleProcessRouteInputPoll` 250ms/1s 抢跑、`processRoutePanelUnlocked` 防止 error 分支把已解锁面板又锁回去
2. **`chat.send`**:SSE 流解析、`buffer` 跨 chunk 暂存半截行、`[DONE]` 显式终止跳出 while 循环、光标闪烁动画、tool_call 旁路渲染、错误兜底
3. **`pollLatestProcessRouteInput`**:核心去重逻辑(getProcessRouteInboxKey 比较)、自动/普通智能体的不同分支
4. **5 步状态机**:`processWorkflowState` 的 7 个字段(activeStepId / runningStepId / awaitingStepId / runningAll / waitingUserStepId / autoSubmittedRoute / doneStepIds)、`runProcessWorkflowAllSteps` 的串行调度
5. **JSDoc 注释**:之前加在 `pollLatestProcessRouteInput` / `runProcessAiProcessInputStep` / `send` 上的 4 段关键函数文档,已原样迁移到新位置

## 七、验证清单

1. **页面能加载**:浏览器打开 `http://localhost:9095/`,DevTools Network 面板应该看到:
   - `/` (200, text/html)
   - `/assets/modules/entry.js` (200, application/javascript)
   - `/assets/modules/shared.js`、`chat.js`、`tool_call.js` 等陆续加载
   - 没有 404 或 MIME 类型错误
2. **控制台无报错**:不应该有 `import` 失败、循环依赖警告、未捕获异常
3. **核心路径**:
   - 发送消息 → SSE 流式渲染、tool_call 卡片出现
   - 切换到「自动工艺生成」智能体 → 工作流 dock 显示、5 步按钮可点
   - 点第 4 步 → 触发 3DMPS → 面板解锁
   - 生成工艺路线 → 时间线渲染 → 提交后第 4 步标记 done
4. **缓存验证**:清掉浏览器缓存后,改任意一个 `modules/*.js`,重启 Python 服务后改动立即生效(Python 端 `_STYLE_CSS` 等缓存也是启动时一次性加载)

## 八、发布收尾

旧版单体 `app.js` 已从 `frontend/assets/` 移除,运行入口只保留模板里的 `/assets/modules/entry.js`。
`tests/test_frontend_assets.py` 覆盖两件事:发布目录不再携带 `app.js`,并且 `build_index_html()` 输出的外部脚本只引用模块化入口。

如果想做更彻底的改进,`web_page.py` 里 `_STYLE_CSS` 模块级缓存是「启动时一次性读 + 永不失效」的逻辑,改成启动时检测文件 mtime、缓存命中但文件变了的自动 reload 可以单独做,跟模块化正交,不影响本次结构。

## 九、后续可优化方向

1. **拆分 CSS 模块化**:9 个 CSS 文件目前是手动按顺序拼到 `<style>` 里,可以改成 `<link rel="stylesheet" href="/assets/css/base.css">` 等多个 link,样式表单独缓存,改 CSS 不影响 HTML 响应
2. **TypeScript / JSDoc 类型检查**:目前只有 3 个关键函数加了 JSDoc,可以加 `// @ts-check` 到 `entry.js` 顶部让 IDE 做基础类型推断
3. **单元测试**:7 个模块按职责切得很干净,适合加 Vitest / Jest 之类的单测;特别是 `pollLatestProcessRouteInput` 的 3 分支逻辑、`runProcessAiProcessInputStep` 的状态机流转
4. **CSS-in-JS 风险隔离**:目前 CSS class 命名靠人工规范(`pr-` / `option-card` / `template-type-`),后续可以考虑 CSS Modules 或者加 `data-module` 属性做命名空间隔离
