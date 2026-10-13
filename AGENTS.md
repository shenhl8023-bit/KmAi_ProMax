# AGENTS.md

## 项目定位

KmAI 是 3DMPS 的本地 AI 助手模块。它由 Windows CEF 客户端、本地 Python HTTP Agent 服务、浏览器前端和 Windows 命名管道桥接组成。默认 HTTP 地址为 `http://127.0.0.1:9095`，与 3DMPS 主程序的通信管道为 `\\.\pipe\3dmps_service`。

本项目当前在外网环境开发，最终代码会迁移到内网。开发时必须把外网依赖、凭据和构建产物与可迁移源代码分开管理。

## 目录地图

- `KmMpsMcpServer/`：本地 Python Agent 服务。
- `KmMpsMcpServer/backend/`：HTTP API、Agent 主循环、LLM 配置、命名管道、会话和审计。
- `KmMpsMcpServer/tools/`：按业务域组织的工具定义和实现。
- `KmMpsMcpServer/skills/`：可注册的技能包及其脚本、规则、模板和 schema。
- `KmMpsMcpServer/agents/`：Agent 提示词。
- `KmMpsMcpServer/frontend/`：由 HTTP 服务托管的 HTML、CSS 和原生 ES Module 前端。
- `tests/` 与 `KmMpsMcpServer/tests/`：项目测试。
- `CefView/`、根目录 `*.dll`/`*.exe`、`platforms/`：Windows/CEF 运行时和构建产物，不属于可迁移源代码发布包。
- `config.ini`：本机配置，不应提交；以 `config.example.ini` 为模板创建。

## 开发环境

- Windows 10/11。
- Python 3.10 或更高版本；以项目启动脚本实际探测到的解释器为准。
- 前端不需要构建步骤，使用原生 HTML、CSS 和 ES Module JavaScript。
- 命名管道相关代码依赖 Windows API；在 Linux/macOS 上只能运行不触发 Windows 管道的静态检查或单元测试子集。
- 不要把外网服务地址、代理地址、API Key、Token、内网地址或用户目录写入源代码、测试快照和文档示例。

## 常用命令

在项目根目录执行：

```powershell
# 运行项目测试脚本
.\run_tests.ps1

# 或使用批处理入口
.\run_tests.bat

# 直接运行 Python 测试发现
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s KmMpsMcpServer\tests -p "test_*.py"
```

运行 Agent 前，先从模板创建本机配置：

```powershell
Copy-Item config.example.ini config.ini
# 编辑 config.ini，填写本机允许访问的 LLM 地址；没有 key 时应保持关键词匹配模式
.\KmMpsMcpServer\start_agent.bat
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:9095/api/health
```

停止服务：

```powershell
.\KmMpsMcpServer\stop_agent.bat
```

## 改动规则

1. 先读相关代码、测试和配置，再修改；不要凭文件名猜测接口行为。
2. 做最小、可追溯的改动。不要顺手重排文件、统一换行符或重构无关模块。
3. 后端工具必须同时检查工具注册表、参数 schema、实际实现、关键词降级路径和对应测试。
4. 新增 HTTP API 时，补齐成功、无效输入、权限/安全边界和内部异常不泄漏的测试。
5. 前端修改应保持原生模块结构，优先复用 `shared.js`、现有状态管理和既有 CSS 约定；不要引入新的构建系统或依赖，除非需求明确要求。
6. Skill 修改必须同步检查 `registry.json`、入口脚本、输入输出 schema、参考规则和错误输出。
7. 注释解释原因和约束，不重复代码本身。避免大函数、深层嵌套、隐式全局状态和魔法值。
8. 不要修改或删除用户未要求的现有工作区改动。

## 安全与凭据

- `config.ini` 只能存在于本机，必须保持未跟踪状态。
- 真实 API Key、访问 Token、Cookie、内网 URL、用户名、密码和模型服务凭据禁止进入 Git 历史。
- 如果凭据曾经进入提交，不能只删除当前文件；必须停止发布、撤销/轮换凭据，并清理要发布的 Git 历史。
- 推送到外网仓库前，必须检查：`git status`、跟踪文件中的大文件、凭据模式、日志、缓存和运行时二进制。
- 运行日志、调试快照、截图和编译产物除非明确需要，不应进入源代码提交。
- 不要把外网临时代理或下载缓存写入项目目录；内网迁移时应由内网管理员提供依赖、模型服务和证书配置。

## 外网开发到内网迁移

迁移目标是可复现的源代码包，而不是当前外网机器的完整运行目录。迁移前应完成以下检查：

- 导出源代码、测试、技能规则、模板、Agent prompt、`README.md`、`AGENTS.md`、`CLAUDE.md` 和 `config.example.ini`。
- 排除 `config.ini`、所有真实凭据、日志、缓存、`__pycache__`、`*.pyc`、CEF/Qt 运行时二进制和本机截图。
- 在内网重新创建 `config.ini`，将 `[LLM]`、`[Paths]` 和 `[WebView]` 配置替换为内网值。
- 在内网重新提供 Python 3.10+、CEF/Qt 运行时、3DMPS 主程序和命名管道服务；不要从外网提交的源代码仓库中恢复这些二进制。
- 内网环境如果不能访问公网，禁止依赖运行时下载 Python 包、前端 CDN 或外部 API；依赖应提前放入经批准的内网制品库或离线安装包。
- 迁移后先运行静态检查和测试，再连接真实 3DMPS 命名管道；连接真实主程序的测试必须由授权环境执行。
- 内网仓库应重新设置 remote 和访问控制。不要把外网仓库中的凭据、访问令牌或历史提交直接带入内网。

## 提交与发布

提交信息应说明行为变化，例如：`修复工艺路线输入回退`、`补充分组模板确认校验`。一次提交尽量只包含一个主题。

提交前至少执行：

```powershell
git status --short --branch
git diff --check
python -m compileall -q KmMpsMcpServer tests
```

如果测试无法在当前操作系统运行，必须说明具体原因、已运行的检查和未验证的范围，不得把未验证状态表述为通过。

外网发布前，先生成独立的清理版发布目录或分支，确认它不包含凭据和超大运行时文件，再推送。原始开发目录和发布目录应保持边界清晰。
