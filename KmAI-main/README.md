# KmAI — 3DMPS AI 智能体模块

> 集成于 3DMPS（3D 测量/加工/模组化系统）的本地 AI 助手模块。
> 通过 CEF 内嵌浏览器 + 本地 HTTP 服务 + 命名管道桥接，给 3DMPS 主程序加一个能"听指令、点按钮、跑工艺"的 AI 小沐。

---

## 1. 它是什么

`KmAI` 是 3DMPS 主程序的 AI 扩展模块，由两部分组成：

- **`CefView/`**：基于 CEF（Chromium Embedded Framework）的浏览器壳，内嵌 AI 小沐的聊天界面。
- **`KmMpsMcpServer/`**：本地 Python HTTP 服务（默认端口 `9095`），承担 AI agent 逻辑、工具调用、命名管道桥接、网页静态托管等职责。
- **`KmAiChatCef.exe`**：另一个基于 CEF 的独立可执行入口（具体职责以源码为准）。

AI 小沐通过 **Windows 命名管道** `\\.\pipe\3dmps_service` 与 3DMPS C++ 主程序通信（读写消息、调用主程序注册到 `PythonBridge` 的函数），通过 **HTTP + JSON** 与前端聊天界面通信。

---

## 2. 核心能力

| 模块 | 能力 |
|---|---|
| 对话 | LLM 模式（OpenAI 兼容 API）或关键词匹配模式（无 LLM 也能跑） |
| 工具调用 | 按业务域拆分的 7 类工具，约 30+ 个工具，统一 OpenAI function calling 格式 |
| 弹窗自动化 | 对 3DMPS 各类弹窗（分组模板、自动识别、特征方向）执行原子操作（OK / Cancel / 全选 / 设置勾选） |
| 工艺生成 | 通过 Skill 系统调用外部脚本生成分组模板、工艺路线、技术要求 |
| 智能体切换 | 从 `agents/` 目录加载多个 agent 提示词（markdown + front-matter），前端可切换 |
| 模板保存 | 前端编辑的 XML 模板回写到 3DMPS 安装目录的 `Resources\GroupTemplate\` |

---

## 3. 目录结构

```
KmAI/
├── CLAUDE.md                       # 给 Claude 的项目协作说明
├── README.md                       # 本文件
├── KmAiChatCef.exe                 # CEF 入口程序（独立聊天窗口）
├── CefView/                        # CEF 浏览器壳
│   ├── CefViewWing.exe             # CEF Wing 子进程
│   ├── libcef.dll / chrome_elf.dll # CEF 运行时
│   ├── locales/                    # CEF 多语言 .pak
│   └── *.dll / *.pak / *.bin       # 其它 CEF 资源
└── KmMpsMcpServer/                 # 本地 AI agent 服务
    ├── agent_server.py             # 入口脚本（包装 backend.agent_server.main）
    ├── start_agent.bat             # 启动脚本（端口探测 + 后台启动 + 日志重定向）
    ├── stop_agent.bat              # 停止脚本（按命令行匹配杀进程 + 端口释放校验）
    ├── backend/                    # 后端核心
    │   ├── agent_server.py         # HTTP 服务入口（ThreadedHTTPServer, 默认 9095）
    │   ├── http_api.py             # 路由（/api/health /api/chat /api/tool /api/agents ...）
    │   ├── agent_core.py           # MiniAgent 主循环 + 工具调度
    │   ├── agent_profiles.py       # agent 加载（agents/ + 用户目录）
    │   ├── agent_config.py         # config.ini 加载（LLM 配置 + 路径）
    │   ├── agent_utils.py          # JSON 编码、消息构造
    │   ├── prompts.py              # 默认 system prompt
    │   ├── llm_client.py           # OpenAI 兼容 LLM 客户端
    │   ├── tool_runtime.py         # 工具调度 + skill runner 注册表
    │   ├── pipe_client.py          # Windows 命名管道客户端（带超时/重试/取消）
    │   └── audit.py                # 调用审计
    ├── tools/                      # 工具集（OpenAI function calling 格式）
    │   ├── __init__.py             # 按域聚合工具定义 + 参数构建器 + 关键词规则 + 超时
    │   ├── original.py             # 基础工具（主程序已验证）
    │   ├── ai_bridge_ops.py        # 主窗口 AI 桥接工具
    │   ├── dialog_ops.py           # 弹窗自动化工具（仅激活弹窗可用）
    │   ├── file_ops.py             # 文件/模型操作（保存/导出）
    │   ├── process_ops.py          # 工艺执行（识别/推理/创建工序）
    │   ├── query_ops.py            # 数据查询（模型/工序/特征/毛坯）
    │   └── reference_ops.py        # 参考 MCP 项目工具的业务化别名
    ├── skills/                     # 插件式技能
    │   ├── registry.json           # skill 注册表
    │   ├── kmsoft-group-template/  # 分组模板选择（propose / confirm）
    │   ├── process-route-generator/# 工艺路线生成（v1 协议）
    │   └── technical-requirements-generator/ # 技术要求补充
    ├── agents/                     # agent 提示词（markdown + YAML front-matter）
    │   ├── process-auto-generate-agent.md
    │   └── process-auto-generate-agent-test-prompt.md
    ├── frontend/                   # 聊天页面（HTTP 形式提供）
    │   ├── web_page.py             # 模板拼装（CSS 9 文件按序合并 + JS ES Module）
    │   ├── preview_edit.html       # 模板/工艺 XML 编辑器（独立页面）
    │   ├── assets/
    │   │   ├── index.html          # 主聊天页模板
    │   │   ├── css/                # 9 个 CSS（base → chat → workflow → ... → responsive）
    │   │   └── modules/            # 前端 JS 模块
    │   │       ├── entry.js        # 入口（DOM 初始化 + setter 注入 + 事件绑定 + 启动）
    │   │       ├── shared.js       # DOM 引用 + 工具
    │   │       ├── chat.js         # 聊天流（send / SSE）
    │   │       ├── tool_call.js    # 工具调用卡片 + XML 编辑器
    │   │       ├── workflow.js     # 工作流胶囊 + 步骤状态
    │   │       ├── process_route.js# 工艺路线 inbox + 滑出面板
    │   │       └── model_config.js # LLM 配置弹窗
    │   └── 前端JS重构说明.md       # 前端模块化重构笔记
    └── tools/                      # 同级 tools（已合并）
```

---

## 4. 技术栈

| 项 | 选型 |
|---|---|
| 平台 | Win32 桌面应用（`DbgRelease` 配置） |
| 浏览器壳 | CEF（Chromium Embedded Framework），通过 HTTP 加载页面（**不走 file://**） |
| 语言（前端） | 原生 HTML + ES Module JS + CSS（无构建步骤） |
| 语言（后端） | Python 3.10+（启动脚本和核心 Skill 统一要求 3.10 或更高版本） |
| 进程间通信 | Windows 命名管道 `\\.\pipe\3dmps_service`（消息模式 + 64KB 缓冲） |
| HTTP 服务 | `http.server.HTTPServer` + `ThreadingMixIn`（默认 `127.0.0.1:9095`） |
| LLM | OpenAI 兼容协议（`base_url` 可改），无 key 时降级到关键词匹配 |
| 工具定义 | OpenAI function calling JSON Schema |
| 启动方式 | `.bat` 脚本（PowerShell 探测端口 / 后台启动 / 日志重定向） |

---

## 5. 与 3DMPS 主程序的集成

```
┌──────────────────────────────────┐        HTTP/JSON         ┌──────────────────────┐
│  3DMPS 主程序 (C++)              │ ◀─── 命名管道 ──────────▶│  KmAI Agent (Python) │
│  - CAD 模型/工艺树                │    \\.\pipe\3dmps_service │  - HTTP 9095          │
│  - PythonBridge 注册函数          │                          │  - 工具调度            │
│  - 弹窗 (临时注册到 Bridge)        │                          │  - LLM / 关键词匹配    │
└──────────────────────────────────┘                          └──────────┬───────────┘
                                                                          │ HTTP
                                                                          ▼
                                                              ┌────────────────────┐
                                                              │  CEF 浏览器壳       │
                                                              │  (CefViewWing /    │
                                                              │   KmAiChatCef)     │
                                                              └────────────────────┘
```

**调用约定**：

- 命名管道：消息模式（`PIPE_READMODE_MESSAGE`），单次调用默认 30 秒超时（可按工具覆盖），最大响应 8MB。
- 协议：JSON `{"function": "<name>", "params": {...}}` → 3DMPS 返回 `{"status": "success"/"error", ...}`。
- 函数未注册时返回结构化降级响应（`error_code: "FUNCTION_NOT_FOUND"`），调用方可识别。

---

## 6. 运行 / 启动

### 6.1 启动 Agent 服务

```cmd
:: 默认端口 9095（与 config.ini [WebView] url 一致）
start_agent.bat

:: 指定端口
start_agent.bat 9097
```

启动脚本会：
1. 探测 Python 3.10+（优先 `KMAI_PYTHON_EXE` / `KMAI_SKILL_PYTHON`，再尝试内置 `Python3.10+_win32`、`py` launcher 和 PATH 里的 `python`）。
2. 用 PowerShell 检查目标端口是否被占用。
3. 用 `Start-Process -WindowStyle Hidden` 后台启动，运行日志写到用户运行时目录 `%LOCALAPPDATA%\KmAI\logs`（可用 `KMAI_RUNTIME_DIR` 覆盖）。

### 6.2 停止服务

```cmd
stop_agent.bat           :: 默认停止 9095
stop_agent.bat 9097      :: 指定端口
```

按命令行 `agent_server.py` 匹配杀进程，再校验端口释放。

### 6.3 验证

```bash
curl http://127.0.0.1:9095/api/health
```

返回示例：

```json
{
  "status": "ok",
  "pipe": "\\\\.\\pipe\\3dmps_service",
  "pipe_available": true,
  "llm_enabled": true,
  "llm": { "provider": "openai", "model": "gpt-4o", "...": "..." }
}
```

### 6.4 配置 LLM

配置位于 `KmAI\config.ini` 的 `[LLM]` 段（位于项目父目录）：

```ini
[LLM]
provider = openai
api_key = sk-xxxxxxxx
base_url = https://api.openai.com/v1
model = gpt-4o
max_tokens = 4096
temperature = 0.3
```

留空 `api_key`（或保留占位符 `YOUR_API_KEY_HERE`）会自动降级为关键词匹配模式，界面顶部会提示「当前为关键词匹配模式」。

### 6.5 配置 KMRAG 知识助手

从助手下拉框选择“`KMRAG 知识助手`”后，可基于企业知识库检索记录回答问题。它与默认助手、工艺自动生成助手隔离：KMRAG 助手不调用 3DMPS 工具，其他助手也不会看到 KMRAG 检索工具。

先复制 `config.example.ini` 为本机 `config.ini`，再在 `[KMRAG]` 中填写经授权的本机配置：

```ini
[KMRAG]
enabled = true
base_url = https://your-kmrag-api-root
api_key =
bearer_token =
timeout = 30
```

`base_url` 是 KMRAG API 根地址，程序会请求其 `/api/v2/collections/search` 路径。`api_key` 优先于 `bearer_token`；二者任选其一。KMRAG 只做检索，仍需启用 `[LLM]` 才能将检索记录组织成自然语言答案。

无命中时助手会明确提示；401/403 表示鉴权失败，连接失败或超时表示服务不可达。`/api/health` 仅返回 `enabled`、`configured` 和 `auth_mode`，不会探测远端服务或返回地址、Token、Key。已在聊天或截图中暴露的凭据必须撤销并轮换，不能写入源代码、样例、日志或提交。内网迁移时携带内置 `kmrag-search` Skill 和 `config.example.ini`，不要携带 `config.ini`、日志、缓存或外部目录链接。

### 6.6 配置“匹配分组模板”

第一步“匹配分组模板”从固定目录读取当前零件 XML，调用远程服务提取 256 维向量，并在本地索引中按余弦相似度返回 Top N 候选（默认 5）。左侧显示固定当前 STEP，右侧显示当前候选同名 STEP。切换候选后可编辑其映射模板，再点击“应用当前分组模板”；服务沿用既有 `apply_group_template` 调用，成功后继续原第 2 步。MCP 函数实现保持原样。

先把零件数据压缩包解压到稳定目录，再在 `config.ini` 增加：

```ini
[SimilarParts]
enabled = true
matching_backend = feature_vector
feature_api_base_url =
feature_api_timeout_seconds = 120
feature_model_version =
feature_index_file = cache/similar_parts_features.sqlite3
top_k = 5
step_viewer_root = ..\..\step-compare-main\step-compare-main
xml_library_dir = data/xml
step_library_dir = data/step
current_xml_file = data/current/AIBasicInfo.xml
current_step_file = data/current/stepModel.stp
template_map_file = ..\..\PartClassification-main\PartClassification-main\source\模板\模板映射.json
upload_max_bytes = 5242880
cache_ttl_seconds = 1800
model_cache_entries = 8
model_cache_bytes = 268435456
```

路径说明：

- `xml_library_dir` 是相似度样本库。项目自带的 20 个 XML 已与 `模板映射.json` 完整对应。
- `step_library_dir` 是候选 STEP 库；每个 `.stp/.step` 必须与样本 XML 去掉扩展名后的名称相同。用户提供的数据包中 20/20 均已配对。
- `current_xml_file` 与 `current_step_file` 指向当前固定导出的零件文件。未指定 XML 文件时可设置 `current_part_dir`，其目录必须只有一个 XML。
- `template_map_file` 所在目录同时是模板目录，候选模板通过映射读取，不要求模板与零件同名。
- `feature_api_base_url` 填当前部署允许访问的服务地址；`feature_model_version` 是人工部署标签，模型权重或预处理更新时必须更换标签并重新建库。
- `top_k` 允许 1 到 1000；库中有效零件不足时返回实际数量。
- 配置和接口不会向浏览器返回本机绝对路径。缺少排名内任一 STEP 或模板时会明确报数据库错误，不会用后续候选顶替。

STEP 三维转换复用 `step-compare`。Windows x64 运行环境按其锁定依赖安装（当前依赖文件面向 CPython 3.12）：

这里的“转换”只用于浏览器预览：原始 `.stp/.step` 文件保持不变，服务在内存中生成临时 GLB 网格供 Three.js 显示。浏览器不能直接解析 STEP 的 CAD/B-Rep 几何。预览采用交互显示精度，避免复杂 NX STEP 因过细网格长时间占用 CPU；相似度计算和模板应用不读取临时 GLB。

```cmd
py -3.12 -m pip install --require-hashes -r ..\..\step-compare-main\step-compare-main\requirements.txt
```

填好配置后，先运行 `python KmMpsMcpServer/build_feature_index.py` 建立零件库索引，再启动系统。操作顺序：打开五步工作流 → 点击“匹配分组模板” → 在候选列表或“上一件/下一件”间切换 → 编辑或应用当前分组模板。库内 XML 新增或变更后重新运行建库脚本，成功向量可增量复用。应用失败不会完成第一步，可直接重试。详见 [特征向量匹配说明](docs/feature-vector-matching.md)。

---

## 7. HTTP API 一览

所有响应统一为 `{"status": "success"/"error", ...}`。

### GET

| 路径 | 用途 |
|---|---|
| `/` 或 `/index.html` | 主聊天页面（HTML） |
| `/assets/*` | 前端静态资源（仅允许 `_ASSETS_DIR` 内部，防 `..` 穿越） |
| `/similar-assets/three/*` | 本地 Three.js 模块（仅允许配置的离线 vendor 目录） |
| `/api/similar-parts/models/{modelId}.glb` | 获取一次查询登记的当前/候选 GLB 模型 |
| `/api/health` | 健康检查（含命名管道、LLM 状态） |
| `/api/config/llm` | 当前 LLM 配置（API key 仅返回脱敏后版本） |
| `/api/agents` | 列出已加载的 agent 概要 |
| `/api/process-route/input/latest` | 最近一次工艺路线输入 |
| `/api/process-route/result/latest` | 最近一次工艺路线生成结果 |
| `/api/template/xml?templateId=xxx` | 获取指定模板的 XML（复用 `kmsoft_group_template_confirm`） |

### POST

| 路径 | 用途 |
|---|---|
| `/api/tool` | 调用任意工具（`{"function": "<name>", "params": {...}, "timeout": 30}`） |
| `/api/chat` | 单轮聊天（`{"message": "...", "session_id": "...", "agent_id": "..."}`） |
| `/api/chat/stream` | 流式聊天（SSE） |
| `/api/process-route/input/push` | 主程序推送 AI 工艺输入 JSON |
| `/api/process-route/generate` | 触发工艺路线生成 |
| `/api/process-route/generate-technical-requirements` | 补充技术要求 |
| `/api/process-route/export` | 导出工艺路线 |
| `/api/process-route/submit` | 提交工艺路线 |
| `/api/template/save` | 保存前端编辑后的 XML 模板 |
| `/api/config/llm` | 热更新 LLM 配置 |
| `/api/similar-parts/upload` | 上传并校验当前零件 XML |
| `/api/similar-parts/current` | 从固定目录读取当前零件 XML |
| `/api/similar-parts/query` | 按特征向量查询 Top N 相似零件并登记模型 |
| `/api/similar-parts/template` | 读取候选映射的模板供前端编辑 |
| `/api/similar-parts/apply-template` | 应用当前候选绑定的分组模板 |

---

## 8. 工具域（`tools/`）

| 模块 | 说明 |
|---|---|
| `original` | 4 个最基础工具（主程序已验证可用），含 `auto_identify`、`ai_feature_inference`、`click_generate_all_button` 等 |
| `ai_bridge_ops` | 主窗口常驻 AI 桥接工具（`set_auto_featidentify_box`、`do_cmdResponse_by_python`） |
| `dialog_ops` | 弹窗原子操作（`OnBnClickedOk` / `OnBnClickedCancel` / `SelectAllFeatures` 等），**默认不注册** |
| `file_ops` | 文件/模型保存、导出 PDF/Excel/GXK |
| `process_ops` | 工艺执行（创建工序、重排工序号、模型对比、识别报告） |
| `query_ops` | 数据查询（模型信息、工序列表、特征列表、毛坯、BOP 树） |
| `reference_ops` | 参考 MCP 项目的业务化别名 + 描述标注 |

新增域：在 `tools/` 下新建 `my_domain.py`，导出 `TOOLS / TOOL_PIPE_BUILDER / KEYWORD_RULES / TOOL_TIMEOUTS`，在 `tools/__init__.py` 的 `_MODULES` 列表里追加即可。

---

## 9. Skill 插件（`skills/`）

| Skill | 作用 |
|---|---|
| `kmsoft-group-template` | 分组模板选择（propose 候选 / confirm 选定 + XML 输出 + handoff payload） |
| `process-route-generator` | 工艺路线生成（`cad_input` + `manual` → 标准路线 / 分组匹配 / 导出路线） |
| `technical-requirements-generator` | 在已有工艺路线上补充每个工序的 `技术要求`（不改工序结构） |

注册表：`skills/registry.json` 列出 skill 名字，每个 skill 在 `skills/<name>.json` 写元信息。新增 skill：加一个 `skills/<name>.json` + 一个 `skills/<name>/` 目录（带 `SKILL.md` 和 `scripts/`）。

---

## 10. Agent 提示词（`agents/`）

`agents/` 下的 markdown 文件（带 YAML front-matter）会作为可选 agent 加载。front-matter 字段示例：

```markdown
---
description: 工艺自动生成 agent ...
mode: primary
temperature: 0.0
boundSkill: mps-mcp2cli
tools:
  skill: true
  bash: true
  permission:
    skill: { "*": "allow" }
---

你是工艺自动生成 agent...
```

加载顺序：内置 `default` agent → `agents/*.md` → `~/.config/opencode/agents/*.md`（后加载覆盖前加载）。`-test-prompt.md` 结尾的文件、`skill-bound-template.md` 会被跳过。

---

## 11. 前端架构

- **无构建步骤**：`assets/css/*.css` 在服务启动时按顺序拼成单个 `<style>` 块注入；`assets/modules/*.js` 作为 ES Module 按需加载。
- **CSS 顺序**：`base → chat → process_route → workflow → cards → xml_editor → bar → modals → responsive`（`responsive` 必须最后，覆盖默认布局）。
- **JS 模块图**：`entry.js` 是入口；`shared.js` 是底层工具集；`chat/tool_call/process_route/workflow/model_config` 通过 setter 注入打破循环依赖。
- **占位符防护**：模板里残留任何 `{{...}}` 都会在 `build_index_html` 启动时直接抛错（fail-fast）。
- **静态资源隔离**：`/assets/*` 仅允许在 `_ASSETS_DIR` 内部解析，拒绝任何 `..` 穿越。

---

## 12. 调试与日志

| 来源 | 位置 |
|---|---|
| Agent stdout | `%LOCALAPPDATA%\KmAI\logs\agent_server.out.log` |
| Agent stderr | `%LOCALAPPDATA%\KmAI\logs\agent_server.err.log` |
| CEF 子进程 | 暂无独立日志（可在 CefViewWing 启动参数加 `--enable-logging --v=1`） |
| 命名管道调用 | `backend/audit.py`（审计模块） |

**快速排查清单**：

1. `/api/health` 返回 `pipe_available: false` → 3DMPS 主程序未启动，或 PythonBridge 注册未完成。
2. `llm_enabled: false` 但你配了 key → 检查 `config.ini` 路径（默认在项目父目录），确认 `api_key` 不是占位符。
3. 工具调用返回 `FUNCTION_NOT_FOUND` → 该函数未在 3DMPS `Km3dmps.exe` 的 PythonBridge 注册，需联系主程序团队暴露。
4. 工具调用返回 `TIMEOUT` → 可调大 `timeout` 字段（POST `/api/tool` 支持），或拆任务后重试。

---

## 13. 已知约束 / 注意点

- **Python 字节码缓存**：启动脚本会设置 `PYTHONDONTWRITEBYTECODE=1`，避免在发布目录生成 `__pycache__` / `*.pyc`。
- **CEF 不要走 `file://`**：从项目记忆里强调过，CEF 必须通过 HTTP 加载（`http://127.0.0.1:9095/`），否则 CORS / fetch / 跨域 cookie 会出问题。
- **命名管道是单实例的**：所有 HTTP 请求共享一个 `_PIPE_CALL_LOCK`，单次开管 + 一次请求-响应；重试之间不持锁，避免把整个服务卡死。
- **超时不重试**：调用方已等过一次超时，重试只会让用户再等一遍，所以 `PipeCallTimeout` 直接上抛。
- **关键词匹配模式是降级而非默认**：上线应配齐 `config.ini [LLM]` 段，否则工具调用逻辑会走到最简规则。
- **模板保存路径**：默认写入 3DMPS 安装目录的 `Resources\GroupTemplate\`，由 `agent_config.GROUP_TEMPLATE_SAVE_DIR` 控制；保存时校验 `basename` 与 `commonpath` 防穿越。

---

## 14. 给开发者的常见任务

**加一个工具**（假设业务域是「打印」）：

1. 在 `tools/` 下新建 `print_ops.py`，导出：
   ```python
   TOOLS = [{"type": "function", "function": {"name": "print_model", ...}}]
   TOOL_PIPE_BUILDER = {"print_model": lambda a: {"file_path": a["file_path"]}}
   KEYWORD_RULES = [("打印|print", "print_model")]
   TOOL_TIMEOUTS = {"print_model": 60}
   ```
2. 在 `tools/__init__.py` 的 `_MODULES` 列表里追加 `print_ops`。
3. 重启 `start_agent.bat`。

**加一个 Skill**：

1. `skills/<name>.json` 写元信息。
2. `skills/<name>/SKILL.md` 写说明。
3. `skills/<name>/scripts/*.js` 或 `*.py` 写主逻辑。
4. `skills/registry.json` 的 `skills` 数组里追加名字。

**加一个 Agent 提示词**：

在 `agents/` 下新建 `<name>.md`，加 YAML front-matter + 正文提示词。重启后自动出现在前端下拉框里。

---

## 15. 变更日志

| 日期 | 改动 |
|---|---|
| 2026-06-30 | 初版 README 生成（基于项目结构与源码梳理） |
