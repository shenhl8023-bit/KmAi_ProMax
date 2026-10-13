# CLAUDE.md

## 任务范围

你正在维护 KmAI：一个面向 3DMPS 的 Windows 本地 AI 助手。默认只修改用户明确要求的范围；不要因为发现旧代码、换行符差异或可疑的重构机会而扩大任务。

项目最终要迁移到内网。任何开发和发布建议都必须优先保证源代码可迁移、凭据不外泄、外网依赖可替换，并且不能把当前开发机环境当成目标运行环境。

## 开始工作前

先检查：

```powershell
git status --short --branch
git remote -v
Get-ChildItem -Force
```

再阅读本文件和根目录 `AGENTS.md`，然后根据任务读取相关模块和测试。不要在未确认工作区状态前使用 `reset`、批量格式化、换行符转换、清理命令或历史重写。

如果工作区存在用户改动：保留它们；只修改与当前任务相关的文件。遇到疑似凭据、内网地址或不明生成物时，先停止发布动作并报告，不要擅自把它提交或删除。

## 项目事实

- Python 服务入口：`KmMpsMcpServer/agent_server.py`。
- 后端核心：`KmMpsMcpServer/backend/`。
- 工具实现：`KmMpsMcpServer/tools/`。
- 技能包：`KmMpsMcpServer/skills/`；注册表为 `KmMpsMcpServer/skills/registry.json`。
- Agent prompt：`KmMpsMcpServer/agents/`。
- 前端：`KmMpsMcpServer/frontend/`，原生 HTML/CSS/ES Module，无默认构建步骤。
- 默认 HTTP 服务：`127.0.0.1:9095`。
- 与 3DMPS 的 Windows 命名管道：`\\.\pipe\3dmps_service`。
- 本机配置：根目录 `config.ini`；模板：`config.example.ini`。
- 运行时配置由 `KmMpsMcpServer/backend/agent_config.py` 加载，配置中可能包含 LLM 服务凭据，因此 `config.ini` 永远不能进入提交。

## 实现要求

### 后端和工具

修改工具时，沿着完整链路检查：工具定义、参数构建、注册/allowlist、实际执行、超时、错误响应、关键词匹配降级和测试。对 3DMPS 命名管道调用要保持现有超时、取消、响应大小和结构化错误约定。

HTTP 接口必须：

- 校验输入长度、类型和必要字段；
- 对无效请求返回稳定的 4xx JSON 响应；
- 不向客户端返回 traceback、API Key、Token、内网路径或敏感配置；
- 遵循现有认证、CORS、静态资源路径和响应结构；
- 为新增边界补测试，而不是只测试正常路径。

### Skill 系统

Skill 的规则和模板是业务数据，脚本是执行逻辑。修改其中一项时检查输入输出兼容性；不要用宽松的“看起来能解析”替代 schema 和现有契约。外部导出的规则包只能经人工核对后覆盖 `references/`，不要把临时导出包、绝对路径或本地数据直接提交。

### 前端

保持现有原生模块边界和事件流。优先修改负责该状态或行为的模块，不要把业务逻辑塞进页面模板。避免引入 npm、CDN 或构建工具；内网环境默认不能访问公网。涉及交互时检查加载、空数据、错误、重复点击、取消和窗口尺寸变化等状态。

## 测试与验证

改代码前先找对应测试；缺少测试时先定义可验证行为。常用命令：

```powershell
.\run_tests.ps1
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s KmMpsMcpServer\tests -p "test_*.py"
python -m compileall -q KmMpsMcpServer tests
```

Windows 命名管道和 CEF 相关行为必须在 Windows 目标环境验证。Linux/macOS 上的测试结果只能说明不依赖 Windows API 的部分。验证结束前查看完整输出、退出码和失败数量；不要仅凭修改内容或“应该可以”宣称完成。

提交前执行：

```powershell
git diff --check
git status --short --branch
```

## 外网与内网边界

- 不读取、打印、提交或复制真实凭据。
- 不把 `config.ini` 改成带真实 key 的示例；使用 `config.example.ini` 和 `YOUR_API_KEY_HERE`/空值占位。
- 不提交 `*.dll`、`*.exe`、`*.pdb`、`*.pak`、`*.bin`、`*.dat`、`*.pyc`、日志和缓存；这些文件由目标环境或受控制品流程提供。
- 外网开发阶段可以使用外部 LLM，但必须通过本机未跟踪配置注入地址和凭据。代码应在无 key 时可降级到关键词模式。
- 内网迁移前生成清理版源代码包；在内网重新配置 LLM 地址、路径、Python、CEF/Qt 和 3DMPS 依赖。
- 内网无公网访问时，不能依赖运行时 pip 安装、CDN、远程字体、外部 API 或自动下载二进制。

## Git 操作边界

默认只在当前工作分支提交。推送前确认 remote、目标分支和发布内容；不要直接把包含本机凭据或构建产物的完整工作区推到外网。

如果需要从当前开发目录制作外网发布版：

1. 复制到独立目录或使用独立发布分支。
2. 移除配置、凭据、日志、缓存和运行时二进制。
3. 运行凭据扫描、文件大小检查、`git diff --check` 和可执行测试。
4. 查看发布目录的 `git status` 和提交树。
5. 只有验证通过后才推送。

如果历史中曾出现真实凭据，先轮换凭据，再讨论历史清理；删除工作区文件不能撤销已暴露的凭据。

## 工作完成的判断

只有当实现、测试、发布边界和 Git 状态都得到实际命令验证后，才报告完成。最终说明应包含改动文件、执行的验证命令、测试结果和仍未验证的 Windows/3DMPS 依赖范围。