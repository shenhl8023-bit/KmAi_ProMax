# 第三个智能体输入禁用设计

## 目标

选中 `process-auto-generate-agent`（第三个智能体）时，底部人工聊天输入框和发送按钮均不可用；切换到其他智能体后恢复。工作流内部通过 `sendProcessWorkflowPrompt` 发起的自动提示不受影响。

## 根因

`setSelectedAgent` 当前只更新工作流区域和输入框占位文字，没有同步 `dom.input.disabled` 与 `dom.sendBtn.disabled`。此外，`send()` 的 `finally` 块会无条件把发送按钮设为可用；工作流自动请求结束后，这会覆盖第三个智能体应保持的禁用状态。

## 方案

复用现有的 `PROCESS_AUTO_AGENT_ID`，增加一个仅负责同步聊天输入控件状态的小函数。智能体切换完成后调用该函数；`send()` 的 `finally` 块也调用同一函数，确保人工控件状态始终由当前智能体决定。输入区保留原布局，第三个智能体使用明确的禁用占位提示。

## 验收标准

1. 选择 `process-auto-generate-agent` 后，输入框和发送按钮的 `disabled` 都为 `true`。
2. 切换到 `default` 或其他智能体后，两者的 `disabled` 都为 `false`。
3. 工作流自动调用 `sendProcessWorkflowPrompt` 仍可写入提示并发送。
4. 现有前端边界测试和 Python 编译检查通过。
