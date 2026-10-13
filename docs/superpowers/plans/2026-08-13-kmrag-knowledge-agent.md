# KMRAG 知识助手实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended when the user explicitly authorizes subagents) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 KmAI 中新增一个与默认助手、工艺自动生成助手互相隔离的 KMRAG 知识助手，仅基于 KMRAG 检索证据回答问题。

**Architecture:** 继续复用现有 Agent 自动发现、`agent_id::session_id` 会话隔离、OpenAI function calling 和 SkillRunner。KMRAG 作为内置 Skill 接入，聊天入口按 `agent_id` 过滤工具定义，dispatcher 在执行前再次校验权限；KMRAG 配置仅由本机配置加载并注入 Skill 子进程，前端复用现有助手介绍区和聊天快照机制。

**Tech Stack:** Python 3.10+、标准库 `urllib`/`configparser`/`unittest`、原生 ES Module JavaScript、HTML/CSS、Windows PowerShell、现有 KmAI SkillRunner。

## Global Constraints

- 默认使用中文界面文案和错误提示。
- 不新增 Python 包、前端依赖或构建系统。
- 不修改默认助手和工艺自动生成助手的既有职责及可用工具，唯一变化是它们看不到 `kmrag_search`。
- KMRAG 助手只允许调用 `kmrag_search`，不允许调用任何 3DMPS 或其他 Skill 工具。
- KMRAG 查询长度上限为 2000 个字符；最多返回 5 条记录；每条内容最多 1200 个字符；所有内容合计最多 6000 个字符。
- KMRAG 地址、API Key、Bearer Token、响应头、完整异常堆栈和原始后端响应不得进入 Git、前端、健康接口、测试快照或日志。
- `config.ini` 是本机文件；实现过程中不读取、不打印、不覆盖其现有敏感值。
- 不依赖 `D:\Project\skills\kmrag-search`、目录联接、当前用户目录或公网运行时下载。
- 保持 Windows 10/11 和 Python 3.10+ 兼容；Skill 只使用 Python 标准库。
- 不自动 stage、commit、push、rebase 或改写 Git 历史；每个任务只做差异检查。提交仅在用户明确要求后进行，提交信息使用中文。
- 不覆盖当前工作区中与本功能无关的现有修改。

---

## 文件职责图

### 新增文件

- `KmMpsMcpServer/agents/kmrag-knowledge-agent.md`：KMRAG 助手元数据、严格检索提示词和引用规则。
- `KmMpsMcpServer/skills/kmrag-search.json`：`kmrag_search` function calling schema 和 SkillRunner 配置。
- `KmMpsMcpServer/skills/kmrag-search/SKILL.md`：内置 Skill 的可迁移说明。
- `KmMpsMcpServer/skills/kmrag-search/references/kmrag_api.md`：KMRAG 接口契约与鉴权说明，不含实例凭据。
- `KmMpsMcpServer/skills/kmrag-search/scripts/kmrag_search.py`：HTTP 客户端、错误映射、响应规范化与上下文截断。
- `KmMpsMcpServer/skills/kmrag-search/scripts/kmai_kmrag_search.py`：解析 SkillRunner stdin JSON 并输出单个结构化 JSON。
- `KmMpsMcpServer/tests/test_kmrag_skill.py`：KMRAG 客户端和适配入口单元测试。
- `tests/test_kmrag_config.py`：配置、公开状态、Skill 子进程环境覆盖和健康输出测试。
- `config.example.ini`：可提交的无凭据配置模板。

### 修改文件

- `KmMpsMcpServer/skills/registry.json`：注册 `kmrag-search`。
- `KmMpsMcpServer/skills/runner.py`：允许 dispatcher 在单次运行时传入受控环境变量覆盖。
- `KmMpsMcpServer/backend/agent_profiles.py`：定义稳定的 `KMRAG_AGENT_ID`。
- `KmMpsMcpServer/backend/agent_config.py`：读取 `[KMRAG]`，产生公开状态和子进程运行环境。
- `KmMpsMcpServer/backend/tool_runtime.py`：按 Agent 返回工具定义并判断聊天工具权限。
- `KmMpsMcpServer/backend/tool_dispatcher.py`：聊天工具执行前做 Agent 权限校验，并给 KMRAG runner 注入配置。
- `KmMpsMcpServer/backend/llm_service.py`：非流式聊天使用 Agent 专属工具集合并传递 `agent_id`。
- `KmMpsMcpServer/backend/chat_service.py`：流式聊天使用专属工具、严格处理未检索/空结果/错误和检索状态文案。
- `KmMpsMcpServer/backend/http_api.py`：健康接口增加无敏感信息的 `kmrag` 状态。
- `KmMpsMcpServer/frontend/assets/modules/shared.js`：增加 KMRAG Agent ID 常量。
- `KmMpsMcpServer/frontend/assets/modules/chat.js`：切换 KMRAG 介绍区和输入提示，保留逐 Agent 聊天快照。
- `KmMpsMcpServer/frontend/assets/modules/workflow.js`：提供 KMRAG 助手介绍区。
- `KmMpsMcpServer/frontend/assets/modules/entry.js`：注入并导出 KMRAG 介绍区函数。
- `KmMpsMcpServer/tests/test_agent_profiles.py`：真实项目 Agent 注册和提示词契约。
- `KmMpsMcpServer/tests/test_agent_boundaries.py`：流式/非流式工具隔离、严格检索和会话隔离。
- `KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`：KMRAG UI 与其他助手 UI 隔离。
- `KmMpsMcpServer/tests/test_chat_input_placeholder.py`：按 Agent 切换输入提示。
- `tests/test_tool_allowlist.py`：dispatcher 权限拒绝和 `/api/tool` 诊断边界。
- `tests/test_frontend_assets.py`：前端模块依赖和介绍区契约。
- `README.md`：KMRAG 助手配置、使用、诊断和内网迁移说明。
- `.gitignore`：排除本机配置、Skill 设置文件、日志、缓存和字节码。

---

### Task 1: 注册独立 KMRAG Agent 并锁定提示词边界

**Files:**
- Create: `KmMpsMcpServer/agents/kmrag-knowledge-agent.md`
- Modify: `KmMpsMcpServer/backend/agent_profiles.py`
- Modify: `KmMpsMcpServer/tests/test_agent_profiles.py`

**Interfaces:**
- Produces: `agent_profiles.KMRAG_AGENT_ID == "kmrag-knowledge-agent"`。
- Produces: `/api/agents` 通过现有 `list_agent_summaries()` 自动返回 KMRAG Agent。
- Consumes: 现有 `agents/*.md` front matter 解析器，不新增注册机制。

- [ ] **Step 1: 写失败的真实 Agent 注册测试**

在 `test_agent_profiles.py` 增加不改写 `PROJECT_AGENTS_DIR` 的契约测试：

```python
def test_project_registers_isolated_kmrag_agent(self):
    profile, found = agent_profiles.resolve_agent_profile("kmrag-knowledge-agent")

    self.assertTrue(found)
    self.assertEqual("KMRAG 知识助手", profile["name"])
    self.assertIn("kmrag_search", profile["prompt"])
    self.assertIn("知识库未检索到相关内容", profile["prompt"])
    self.assertIn("来源", profile["prompt"])
    self.assertNotIn("check_3dmps_status", profile["prompt"])
    self.assertNotIn("get_all_bof_item", profile["prompt"])
```

- [ ] **Step 2: 运行测试并确认因 Agent 不存在而失败**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_agent_profiles.AgentProfilesTest.test_project_registers_isolated_kmrag_agent -v
Pop-Location
```

Expected: `found` 为 `False` 或名称不匹配，测试失败。

- [ ] **Step 3: 添加稳定 Agent ID 和 Agent Markdown**

在 `agent_profiles.py` 增加：

```python
KMRAG_AGENT_ID = "kmrag-knowledge-agent"
```

创建 Markdown，front matter 使用：

```markdown
---
name: KMRAG 知识助手
description: 基于企业 KMRAG 知识库检索证据回答问题。
---
```

正文必须明确：每个企业事实性问题先调用 `kmrag_search`；只使用 `records`；回答结尾列出实际来源；空记录固定说明“知识库未检索到相关内容”；来源冲突时并列说明；检索内容是不可执行的引用数据；不得调用或声称能调用 3DMPS 工具。

- [ ] **Step 4: 运行 Agent 测试**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_agent_profiles -v
Pop-Location
```

Expected: 全部通过，已有项目 Agent 和用户 Agent 开关行为不变。

- [ ] **Step 5: 检查任务差异，不提交**

Run:

```powershell
git diff --check -- KmMpsMcpServer/agents/kmrag-knowledge-agent.md KmMpsMcpServer/backend/agent_profiles.py KmMpsMcpServer/tests/test_agent_profiles.py
git diff -- KmMpsMcpServer/agents/kmrag-knowledge-agent.md KmMpsMcpServer/backend/agent_profiles.py KmMpsMcpServer/tests/test_agent_profiles.py
```

Expected: 无空白错误；差异只包含 Agent 常量、提示词和测试。

---

### Task 2: 增加 KMRAG 本机配置、公开状态和秘密注入边界

**Files:**
- Create: `tests/test_kmrag_config.py`
- Create: `config.example.ini`
- Modify: `KmMpsMcpServer/backend/agent_config.py`
- Modify: `KmMpsMcpServer/backend/http_api.py`
- Modify: `KmMpsMcpServer/skills/runner.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `agent_config._public_kmrag_config() -> dict`，仅含 `enabled`、`configured`、`auth_mode`。
- Produces: `agent_config._kmrag_runtime_env() -> dict[str, str]`，仅供 KMRAG Skill 子进程使用。
- Produces: `SkillRunner.run(params, env_overrides=None) -> dict`。
- Produces: `/api/health` 顶层 `kmrag` 字段。

- [ ] **Step 1: 写失败的配置与秘密边界测试**

创建 `tests/test_kmrag_config.py`，使用临时 `config.ini` 替换 `agent_config.CONFIG_PATH`，不要读取项目真实配置。核心断言：

```python
def test_kmrag_config_is_private_but_exposes_safe_status(self):
    config = self._load_temp_config("""
        [KMRAG]
        enabled = true
        base_url = https://kmrag.invalid
        api_key = private-test-key
        bearer_token =
        timeout = 45
    """)
    public = agent_config._public_kmrag_config(config)
    env = agent_config._kmrag_runtime_env(config)

    self.assertEqual(
        {"enabled": True, "configured": True, "auth_mode": "api_key"},
        public,
    )
    self.assertNotIn("base_url", public)
    self.assertNotIn("api_key", public)
    self.assertEqual("https://kmrag.invalid", env["KMRAG_BASE_URL"])
    self.assertEqual("private-test-key", env["KMRAG_API_KEY"])
    self.assertEqual("45.0", env["KMRAG_TIMEOUT"])
```

再增加：`enabled=false`、缺少地址、缺少两种凭据均令 `configured=False`；Bearer-only 返回 `auth_mode="bearer_token"`；timeout 小于 1 或大于 180 回退到默认 30；公开字典序列化后不包含测试地址和秘密。

- [ ] **Step 2: 写失败的 SkillRunner 单次环境覆盖测试**

在同一测试文件创建临时脚本，让脚本只输出环境变量是否存在，不输出秘密本身：

```python
runner = SkillRunner({
    "name": "env-check",
    "tool_name": "env_check",
    "command": sys.executable,
    "args": [script_path],
    "timeout": 5,
})
result = runner.run({}, env_overrides={"KMRAG_API_KEY": "private-test-key"})
self.assertEqual({"key_set": True}, result)
self.assertIsNone(runner.env)
```

该测试锁定“运行时传入、runner 对象不持久保存”的要求。

- [ ] **Step 3: 运行新测试并确认接口尚不存在**

Run:

```powershell
python -B -m unittest tests.test_kmrag_config -v
```

Expected: 因 `_public_kmrag_config`、`_kmrag_runtime_env` 或 `env_overrides` 不存在而失败。

- [ ] **Step 4: 最小实现 `[KMRAG]` 配置**

在 `_load_config()` 默认字典中增加：

```python
"kmrag_enabled": False,
"kmrag_base_url": "",
"kmrag_api_key": "",
"kmrag_bearer_token": "",
"kmrag_timeout": 30.0,
```

解析 `[KMRAG]` 后实现：

```python
def _public_kmrag_config(config=None):
    current = config or CONFIG
    enabled = bool(current.get("kmrag_enabled"))
    has_url = bool((current.get("kmrag_base_url") or "").strip())
    has_api_key = bool((current.get("kmrag_api_key") or "").strip())
    has_bearer = bool((current.get("kmrag_bearer_token") or "").strip())
    auth_mode = "api_key" if has_api_key else ("bearer_token" if has_bearer else "")
    return {
        "enabled": enabled,
        "configured": bool(enabled and has_url and auth_mode),
        "auth_mode": auth_mode,
    }


def _kmrag_runtime_env(config=None):
    current = config or CONFIG
    return {
        "KMRAG_ENABLED": "true" if current.get("kmrag_enabled") else "false",
        "KMRAG_BASE_URL": (current.get("kmrag_base_url") or "").strip(),
        "KMRAG_API_KEY": (current.get("kmrag_api_key") or "").strip(),
        "KMRAG_BEARER_TOKEN": (current.get("kmrag_bearer_token") or "").strip(),
        "KMRAG_TIMEOUT": str(float(current.get("kmrag_timeout") or 30.0)),
    }
```

用专用 `_parse_kmrag_timeout()` 将无效值和越界值安全回退到 `30.0`，不要让错误配置阻止 Agent 服务启动。

- [ ] **Step 5: 让 SkillRunner 接收非持久化环境覆盖**

把签名改为：

```python
def run(self, params, env_overrides=None):
```

启动子进程前仅在需要时复制父环境并按顺序合并：`os.environ`、`self.env`、`env_overrides`。不得写回 `os.environ` 或 `self.env`。

- [ ] **Step 6: 增加健康接口安全状态**

在 `/api/health` 响应中加入：

```python
"kmrag": agent_config._public_kmrag_config(),
```

扩展测试，序列化健康响应后断言不含 `base_url`、`api_key`、`bearer_token` 和测试秘密。健康检查不得发出远程 HTTP 请求。

- [ ] **Step 7: 创建无凭据模板并加强忽略规则**

`config.example.ini` 保留现有 `[WebView]`、`[LLM]`、`[Paths]` 示例，并增加：

```ini
[KMRAG]
enabled = false
base_url =
api_key =
bearer_token =
timeout = 30
```

`.gitignore` 至少增加：

```gitignore
/config.ini
**/settings.env
**/__pycache__/
*.pyc
*.log
```

不要读取或改写现有 `config.ini`。它当前已被 Git 跟踪；只有用户明确授权 staging/commit 后，才执行 `git rm --cached -- config.ini` 让删除进入下一次提交，同时保留本机文件。未获授权时在最终状态中明确报告这个剩余发布风险。

- [ ] **Step 8: 运行配置、健康和 SkillRunner 回归测试**

Run:

```powershell
python -B -m unittest tests.test_kmrag_config tests.test_python_runtime_diagnostics tests.test_skill_runner_stderr_pipe -v
```

Expected: 全部通过，现有 SkillRunner 大 stderr/大 stdout 行为不变。

- [ ] **Step 9: 检查任务差异，不提交**

Run:

```powershell
git diff --check -- .gitignore config.example.ini KmMpsMcpServer/backend/agent_config.py KmMpsMcpServer/backend/http_api.py KmMpsMcpServer/skills/runner.py tests/test_kmrag_config.py
git status --short
```

Expected: `config.ini` 内容没有工作区差异；未发生自动 staging。

---

### Task 3: 内置 KMRAG 检索 Skill 和结构化适配入口

**Files:**
- Create: `KmMpsMcpServer/skills/kmrag-search.json`
- Create: `KmMpsMcpServer/skills/kmrag-search/SKILL.md`
- Create: `KmMpsMcpServer/skills/kmrag-search/references/kmrag_api.md`
- Create: `KmMpsMcpServer/skills/kmrag-search/scripts/kmrag_search.py`
- Create: `KmMpsMcpServer/skills/kmrag-search/scripts/kmai_kmrag_search.py`
- Create: `KmMpsMcpServer/tests/test_kmrag_skill.py`
- Modify: `KmMpsMcpServer/skills/registry.json`

**Interfaces:**
- Produces: `kmrag_search.search(query, environ=None, opener=None) -> dict`。
- Produces: `kmrag_search.sanitize_result(query, response) -> dict`。
- Produces: `kmai_kmrag_search.run_request(request, environ=None) -> dict`。
- Produces: OpenAI 工具 `kmrag_search(query: str)`。
- Consumes: Task 2 注入的 `KMRAG_ENABLED`、`KMRAG_BASE_URL`、`KMRAG_API_KEY`、`KMRAG_BEARER_TOKEN`、`KMRAG_TIMEOUT`。

- [ ] **Step 1: 写失败的客户端纯函数测试**

在 `test_kmrag_skill.py` 用 `importlib.util.spec_from_file_location()` 按文件路径加载两个脚本。覆盖以下精确行为：

```python
def test_build_payload_uses_fixed_hybrid_strategy(self):
    self.assertEqual({
        "query": "供应商准入流程",
        "vector_search": {"topk": 5, "similarity": 0.5},
        "fulltext_search": {"topk": 5},
        "rerank": True,
    }, self.client.build_payload("供应商准入流程"))


def test_api_key_takes_precedence_over_bearer_token(self):
    headers = self.client.build_headers("api-key", "bearer-token")
    self.assertEqual("api-key", headers["X-API-Key"])
    self.assertNotIn("Authorization", headers)
```

再覆盖：功能关闭/缺配置为 `KMRAG_NOT_CONFIGURED`；空查询和超过 2000 字符为 `INVALID_QUERY`；Base URL 去尾斜杠后只追加一次 `/api/v2/collections/search`；timeout 必须在 1 到 180 秒内。

- [ ] **Step 2: 写失败的响应缩减和提示注入数据测试**

构造 7 条记录，其中内容超过 1200 字符、总内容超过 6000 字符、metadata 包含 `password`/`token` 和安全字段。断言：

```python
self.assertEqual(5, len(result["records"]))
self.assertLessEqual(len(result["records"][0]["content"]), 1200)
self.assertLessEqual(sum(len(item["content"]) for item in result["records"]), 6000)
self.assertTrue(result["truncated"])
self.assertNotIn("password", result["records"][0]["metadata"])
self.assertNotIn("token", result["records"][0]["metadata"])
```

metadata 只允许：`source_id`、`chunk_id`、`page`、`page_number`、`title`、`section`、`collection_id`。保留设计文档列出的其余记录字段，未知字段全部丢弃。

- [ ] **Step 3: 写失败的错误映射和 stdin 适配测试**

模拟并断言：

- HTTP 401/403 -> `KMRAG_AUTH_FAILED`。
- `socket.timeout`/`TimeoutError` -> `KMRAG_TIMEOUT`。
- `urllib.error.URLError` -> `KMRAG_UNREACHABLE`。
- JSON 解码失败或成功响应不是对象 -> `KMRAG_BAD_RESPONSE`。
- `records=[]` -> `status="success"`，不是错误。
- `run_request({"action":"search","query":"什么是 KMRAG"})` 传给客户端的查询必须是纯文本，不能包含 JSON 外壳。
- adapter 遇到 `KmragClientError` 时打印/返回公开中文消息，不包含 HTTP body、URL、Key 或堆栈。

- [ ] **Step 4: 运行新测试并确认脚本尚不存在**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_kmrag_skill -v
Pop-Location
```

Expected: 因脚本文件或函数不存在而失败。

- [ ] **Step 5: 实现标准库 KMRAG 客户端**

定义结构化异常：

```python
class KmragClientError(RuntimeError):
    def __init__(self, error_code, public_message):
        RuntimeError.__init__(self, public_message)
        self.error_code = error_code
        self.public_message = public_message
```

实现固定常量：

```python
MAX_QUERY_LENGTH = 2000
MAX_RECORDS = 5
MAX_CONTENT_PER_RECORD = 1200
MAX_TOTAL_CONTENT = 6000
SAFE_METADATA_KEYS = frozenset([
    "source_id", "chunk_id", "page", "page_number",
    "title", "section", "collection_id",
])
```

`search()` 使用 `urllib.request.Request` 发 POST JSON；仅在 `KMRAG_ENABLED=true` 且地址和一种凭据齐全时请求。读取响应后先验证顶层为对象、`ok` 为真、`data` 为对象，再调用 `sanitize_result()`。API Key 优先于 Bearer Token。

- [ ] **Step 6: 实现 KmAI stdin JSON 适配入口**

`run_request()` 精确输出：

```python
{
    "status": "success",
    "ok": True,
    "query": query,
    "records": records,
    "record_count": len(records),
    "truncated": truncated,
}
```

失败精确输出：

```python
{
    "status": "error",
    "ok": False,
    "error_code": exc.error_code,
    "message": exc.public_message,
}
```

`main()` 从 `sys.stdin.buffer` 读取一个 JSON 对象，stdout 只输出一个 UTF-8 JSON；所有诊断只允许写 stderr，且不得含凭据或原始响应。结构化业务错误返回退出码 0，让 dispatcher 保留具体错误码；只有无法读取 stdin 或无法序列化这类适配器自身故障才返回非零。

- [ ] **Step 7: 注册 Skill**

`kmrag-search.json` action 使用：

```json
{
  "name": "search",
  "tool_name": "kmrag_search",
  "command": "python-auto",
  "args": ["scripts/kmai_kmrag_search.py"],
  "python_min_version": "3.10",
  "timeout": 180,
  "description": "从企业 KMRAG 知识库检索与问题相关的证据，仅返回检索记录、来源和分数。",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "需要检索的完整问题"}
    },
    "required": ["query"],
    "additionalProperties": false
  }
}
```

把 `kmrag-search` 追加到 `registry.json`。`SKILL.md` 和 `kmrag_api.md` 只记录可迁移接口契约和固定检索策略，不包含实际部署地址或凭据。

- [ ] **Step 8: 运行 Skill 与注册回归测试**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_kmrag_skill -v
Pop-Location
python -B -m unittest tests.test_skill_runtime_diagnostics tests.test_tool_compatibility -v
```

Expected: 新测试和已有 Skill 注册/运行时测试通过；测试不发真实网络请求。

- [ ] **Step 9: 检查任务差异，不提交**

Run:

```powershell
git diff --check -- KmMpsMcpServer/skills KmMpsMcpServer/tests/test_kmrag_skill.py
git diff --stat -- KmMpsMcpServer/skills KmMpsMcpServer/tests/test_kmrag_skill.py
```

Expected: Skill 完全位于项目内，差异中没有外部绝对路径或真实凭据。

---

### Task 4: 对聊天工具实施双层 Agent 授权并形成严格知识问答闭环

**Files:**
- Modify: `KmMpsMcpServer/backend/tool_runtime.py`
- Modify: `KmMpsMcpServer/backend/tool_dispatcher.py`
- Modify: `KmMpsMcpServer/backend/llm_service.py`
- Modify: `KmMpsMcpServer/backend/chat_service.py`
- Modify: `tests/test_tool_allowlist.py`
- Modify: `KmMpsMcpServer/tests/test_agent_boundaries.py`

**Interfaces:**
- Produces: `tool_runtime.get_tools_for_agent(agent_id) -> list[dict]`。
- Produces: `tool_runtime.is_tool_allowed_for_agent(agent_id, tool_name) -> bool`。
- Produces: `ToolDispatcherMixin._execute_tool(name, args, agent_id=DEFAULT_AGENT_ID)`。
- Consumes: Task 1 `KMRAG_AGENT_ID`、Task 2 `_kmrag_runtime_env()`、Task 3 `kmrag_search` runner。

- [ ] **Step 1: 写失败的工具可见性测试**

在 `tests/test_tool_allowlist.py` 增加：

```python
def _tool_names(tools):
    return [item["function"]["name"] for item in tools]


def test_kmrag_agent_sees_only_kmrag_search(self):
    from backend.tool_runtime import get_tools_for_agent
    self.assertEqual(["kmrag_search"], _tool_names(
        get_tools_for_agent("kmrag-knowledge-agent")
    ))


def test_other_agents_do_not_see_kmrag_search(self):
    from backend.tool_runtime import get_tools_for_agent
    self.assertNotIn("kmrag_search", _tool_names(get_tools_for_agent("default")))
    self.assertNotIn(
        "kmrag_search",
        _tool_names(get_tools_for_agent("process-auto-generate-agent")),
    )
```

- [ ] **Step 2: 写失败的执行层越权测试**

使用 fake runner 和 `RecordingPipe` 断言：

```python
result = agent._execute_tool(
    "check_3dmps_status", {}, agent_id="kmrag-knowledge-agent"
)
self.assertEqual("TOOL_NOT_ALLOWED_FOR_AGENT", result["error_code"])
self.assertEqual([], agent.pipe.calls)
```

再断言默认助手调用 `kmrag_search` 时 runner 不执行；KMRAG 助手调用 `kmrag_search` 时 runner 收到 `_kmrag_runtime_env()`；`agent.tool("kmrag_search", ...)` 作为 `/api/tool` 使用的无 Agent 诊断路径仍可执行。

- [ ] **Step 3: 写失败的聊天严格检索测试**

在 `test_agent_boundaries.py` 增加 fake LLM 场景：

1. KMRAG Agent 首轮收到的工具名只有 `kmrag_search`。
2. 默认 Agent 首轮工具不含 `kmrag_search`。
3. 模型请求 `kmrag_search` 时 `_execute_tool` 收到 `agent_id="kmrag-knowledge-agent"`。
4. KMRAG Agent 首轮未返回 tool call 时，不进入无工具最终生成，而是返回“未执行知识库检索，无法基于企业知识库回答”。
5. `records=[]` 时直接返回“知识库未检索到相关内容”，不调用第二轮 LLM。
6. Skill 返回 `KMRAG_AUTH_FAILED`、`KMRAG_TIMEOUT` 等错误时停止，不调用 3DMPS 工具或默认助手。
7. LLM 未启用时，KMRAG Agent 返回“需要先启用 LLM 智能对话”，不进入关键词匹配。
8. 相同 `session_id` 下，`default` 与 `kmrag-knowledge-agent` 使用不同 conversation key。

更新现有 monkeypatch `_execute_tool` 的 fake 签名为 `fake_execute_tool(name, args, agent_id=None)`，只做必要兼容修改。

- [ ] **Step 4: 运行授权和边界测试，确认失败**

Run:

```powershell
python -B -m unittest tests.test_tool_allowlist -v
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_agent_boundaries -v
Pop-Location
```

Expected: 因专属工具接口、执行层 Agent 参数和严格检索处理尚不存在而失败。

- [ ] **Step 5: 实现工具可见性策略**

在 `tool_runtime.py` 保留全局 `TOOLS` 作为注册工具全集，新增：

```python
KMRAG_TOOL_NAME = "kmrag_search"


def get_tools_for_agent(agent_id):
    if agent_id == KMRAG_AGENT_ID:
        return [tool for tool in TOOLS if _tool_name(tool) == KMRAG_TOOL_NAME]
    return [tool for tool in TOOLS if _tool_name(tool) != KMRAG_TOOL_NAME]


def is_tool_allowed_for_agent(agent_id, tool_name):
    if agent_id is None:
        return True
    if agent_id == KMRAG_AGENT_ID:
        return tool_name == KMRAG_TOOL_NAME
    return tool_name != KMRAG_TOOL_NAME
```

`agent_id=None` 只表示现有 `/api/tool` 管理员诊断路径；它不代表默认助手。未知聊天 Agent 不在这里回退，仍由 `resolve_agent_profile()` 在聊天入口拒绝。

- [ ] **Step 6: 在 dispatcher 实施执行前授权**

把内部签名扩展为：

```python
def _execute_tool_impl(self, function_name, params, timeout, source, agent_id=None):
```

注册检查之后、任何 Skill/管道调用之前增加 Agent 授权检查。拒绝结果必须包含 `status="error"`、`error_code="TOOL_NOT_ALLOWED_FOR_AGENT"`、`tool`、`agent_id` 和不泄密的中文 `message`，并写现有审计状态但不执行 runner/pipe。

`tool()` 传 `agent_id=None` 保持管理员诊断行为；`_execute_tool()` 改为：

```python
def _execute_tool(self, name, args, agent_id=DEFAULT_AGENT_ID):
    return self._execute_tool_impl(
        name, args, timeout=None, source="llm_chat", agent_id=agent_id
    )
```

仅当 `name == "kmrag_search"` 时调用：

```python
runner.run(params, env_overrides=agent_config._kmrag_runtime_env())
```

其他 runner 继续调用 `runner.run(params)`，避免改变已有 fake runner 和第三方 Skill 契约。

- [ ] **Step 7: 非流式聊天使用 Agent 专属工具**

在 `_llm_chat()` 取得：

```python
agent_tools = get_tools_for_agent(agent_id)
```

首轮只传 `agent_tools`，后续仍按现有兼容规则传 `None`。所有聊天工具执行调用 `_execute_tool(func_name, func_args, agent_id=agent_id)`。

若 KMRAG Agent 没有 tool call，立即返回固定拒答；若 `kmrag_search` 成功但 `records` 为空，立即返回固定无命中文案；若有记录，再把缩减后的工具结果交给第二轮 LLM 组织带来源回答。

- [ ] **Step 8: 流式聊天实现同样边界**

`stream_chat()` 与非流式逻辑保持一致：

- 首轮传 `get_tools_for_agent(agent_id)`。
- 执行传 `agent_id`。
- `kmrag_search` 状态文案固定为“正在检索企业知识库...”。
- 未调用工具、空记录和结构化错误均在第二轮生成前停止。
- `TOOL_NOT_ALLOWED_FOR_AGENT`、`KMRAG_NOT_CONFIGURED`、`KMRAG_AUTH_FAILED`、`KMRAG_UNREACHABLE`、`KMRAG_TIMEOUT`、`KMRAG_BAD_RESPONSE` 使用各自简洁中文提示。
- 无 LLM 的 KMRAG Agent 不进入 `_keyword_match()`。

把共用判断抽成不产生副作用的小函数，例如 `_is_empty_kmrag_result(result)` 和 `_kmrag_error_reply(result)`；不要复制两套不同文案。

- [ ] **Step 9: 运行授权、聊天和兼容回归测试**

Run:

```powershell
python -B -m unittest tests.test_tool_allowlist tests.test_tool_compatibility -v
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_agent_boundaries tests.test_agent_core_decomposition -v
Pop-Location
```

Expected: 全部通过；默认助手的直接 BOF/关键词优先行为保持不变。

- [ ] **Step 10: 检查任务差异，不提交**

Run:

```powershell
git diff --check -- KmMpsMcpServer/backend/tool_runtime.py KmMpsMcpServer/backend/tool_dispatcher.py KmMpsMcpServer/backend/llm_service.py KmMpsMcpServer/backend/chat_service.py tests/test_tool_allowlist.py KmMpsMcpServer/tests/test_agent_boundaries.py
```

Expected: Agent 授权同时存在于模型可见工具层和执行层。

---

### Task 5: 增加隔离的 KMRAG 前端入口和介绍区

> 2026-08-13 变更：KMRAG 专属介绍区已按用户确认取消；以 `2026-08-13-remove-kmrag-intro-panel.md` 为准。KMRAG 输入提示、Agent 切换和聊天隔离要求继续保留。

**Files:**
- Modify: `KmMpsMcpServer/frontend/assets/modules/shared.js`
- Modify: `KmMpsMcpServer/frontend/assets/modules/chat.js`
- Modify: `KmMpsMcpServer/frontend/assets/modules/workflow.js`
- Modify: `KmMpsMcpServer/frontend/assets/modules/entry.js`
- Modify: `KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py`
- Modify: `KmMpsMcpServer/tests/test_chat_input_placeholder.py`
- Modify: `tests/test_frontend_assets.py`

**Interfaces:**
- Produces: `KMRAG_AGENT_ID = "kmrag-knowledge-agent"` 前端常量。
- Produces: `showKmragKnowledgeIntro() -> HTMLElement | null`。
- Consumes: `/api/agents` 自动返回的 KMRAG Agent，不硬编码 `<option>`。

- [ ] **Step 1: 写失败的 KMRAG UI 边界测试**

在 `test_default_assistant_ui_boundaries.py` 断言：

```python
self.assertIn("state.currentAgentId === KMRAG_AGENT_ID", chat_source)
self.assertIn("_showKmragKnowledgeIntro();", chat_source)
self.assertIn("export function showKmragKnowledgeIntro()", workflow_source)
self.assertIn("KMRAG 知识助手", workflow_source)
self.assertIn("知识库问答", workflow_source)
self.assertIn("答案来源", workflow_source)
self.assertIn("无命中", workflow_source)
```

同时保留原测试：默认介绍只对 `default` 展示，工艺助手只展示工艺工作流，Agent 切换不调用 `resetSession()`，聊天日志按 Agent 保存和恢复。

- [ ] **Step 2: 写失败的输入提示和模块注入测试**

把 `test_chat_input_placeholder.py` 的切换断言改为按 Agent：

```python
self.assertIn(
    "state.currentAgentId === KMRAG_AGENT_ID",
    source,
)
self.assertIn("例如：查询公司的供应商准入流程", source)
self.assertIn("例如：读取当前BOF", source)
```

在 `test_frontend_assets.py` 断言 `entry.js` import、`setChatDeps` 注入和调试导出均包含 `showKmragKnowledgeIntro`。

- [ ] **Step 3: 运行前端静态契约测试并确认失败**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_default_assistant_ui_boundaries tests.test_chat_input_placeholder -v
Pop-Location
python -B -m unittest tests.test_frontend_assets -v
```

Expected: 因 KMRAG 常量、介绍区和提示逻辑不存在而失败。

- [ ] **Step 4: 实现 KMRAG Agent 前端常量和依赖注入**

在 `shared.js` 增加：

```javascript
export const KMRAG_AGENT_ID = 'kmrag-knowledge-agent';
```

`chat.js` 新增 `_showKmragKnowledgeIntro` 依赖；`entry.js` import、注入并加入 `window.__kmai__.workflow`。不改变 `/api/agents` 动态填充选项的现有逻辑。

- [ ] **Step 5: 实现复用现有样式的 KMRAG 介绍区**

在 `workflow.js` 使用现有 `.default-assistant-intro` 结构，不新增卡片嵌套或新依赖。显示三项：

```javascript
const KMRAG_ASSISTANT_CAPABILITIES = [
  { title: '知识库问答', desc: '从当前账号有权访问的企业知识库检索内容。' },
  { title: '答案来源', desc: '回答基于检索记录，并列出实际使用的来源。' },
  { title: '无命中提示', desc: '知识库没有相关记录时明确说明，不编造企业结论。' }
];
```

标题为“KMRAG 知识助手”，徽标为“知识库问答 / 来源可追溯”。不得写入 KMRAG 地址、集合名称或权限信息。

- [ ] **Step 6: 按 Agent 切换介绍区和输入提示**

`setSelectedAgent()` 分支顺序保持：工艺助手 -> KMRAG 助手 -> 默认助手 -> 其他普通 Agent。KMRAG 分支执行 `_showKmragKnowledgeIntro()`；默认分支仍只对 `default` 调用 `_showDefaultAssistantIntro()`。

输入提示使用：

```javascript
dom.input.placeholder = state.currentAgentId === KMRAG_AGENT_ID
  ? '例如：查询公司的供应商准入流程'
  : '例如：读取当前BOF';
```

不得清空 `state.agentLogSnapshots`、改变 `state.sessionId` 或调用 `resetSession()`。

- [ ] **Step 7: 运行前端测试**

Run:

```powershell
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_default_assistant_ui_boundaries tests.test_chat_input_placeholder -v
Pop-Location
python -B -m unittest tests.test_frontend_assets -v
```

Expected: 全部通过；默认助手现有介绍卡和提示仍通过原测试。

- [ ] **Step 8: 检查任务差异，不提交**

Run:

```powershell
git diff --check -- KmMpsMcpServer/frontend/assets/modules KmMpsMcpServer/tests/test_default_assistant_ui_boundaries.py KmMpsMcpServer/tests/test_chat_input_placeholder.py tests/test_frontend_assets.py
```

Expected: 没有引入构建产物、依赖或与 KMRAG 无关的 UI 重排。

---

### Task 6: 文档、集成验证、运行验证和迁移检查

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-13-kmrag-knowledge-agent-design.md` only if implementation revealed an approved contract correction
- Verify: all files changed by Tasks 1-5

**Interfaces:**
- Consumes: Tasks 1-5 的完整功能。
- Produces: 可复现的配置/使用/排障说明和验证记录。

- [ ] **Step 1: 更新 README，不写真实部署信息**

增加以下章节：

1. 从助手下拉框选择“KMRAG 知识助手”。
2. `[KMRAG]` 各字段说明，强调 Base URL 是 API 根地址。
3. KMRAG 助手需要同时启用现有 `[LLM]`；KMRAG 只检索，LLM 负责组织自然语言答案。
4. 无命中、401/403、连接失败、超时的排障含义。
5. `/api/health` 只提供静态安全状态；真实连通性通过授权的 `/api/tool` 非敏感测试查询验证。
6. 内网迁移必须携带内置 Skill 和 `config.example.ini`，不得携带 `config.ini`、日志、缓存或外部目录联接。
7. 已在对话或截图中暴露的凭据必须撤销并轮换。

- [ ] **Step 2: 运行所有针对性测试**

Run:

```powershell
python -B -m unittest tests.test_kmrag_config tests.test_tool_allowlist tests.test_tool_compatibility tests.test_skill_runtime_diagnostics tests.test_skill_runner_stderr_pipe tests.test_python_runtime_diagnostics tests.test_frontend_assets -v
Push-Location KmMpsMcpServer
python -B -m unittest tests.test_kmrag_skill tests.test_agent_profiles tests.test_agent_boundaries tests.test_agent_core_decomposition tests.test_default_assistant_ui_boundaries tests.test_chat_input_placeholder tests.test_http_api_security -v
Pop-Location
```

Expected: 全部通过。若失败，先区分本次修改和工作区已有问题，再修复本次回归。

- [ ] **Step 3: 运行编译和完整项目测试**

Run:

```powershell
python -B -m compileall -q KmMpsMcpServer tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1
```

Expected: 编译检查和两套 unittest discovery 均通过。

- [ ] **Step 4: 做静态凭据与迁移边界检查**

仅扫描将要发布的源码；命令只输出命中文件名，不输出秘密内容：

```powershell
$publishFiles = git ls-files -- KmMpsMcpServer tests README.md config.example.ini .gitignore docs
$suspicious = $publishFiles | Select-String -Pattern 'config\.ini$|settings\.env$|\.log$|__pycache__|\.pyc$'
$suspicious
rg -l "kmrag_sk_[A-Za-z0-9_-]+|Authorization:\s*Bearer\s+[A-Za-z0-9._-]+|X-API-Key\s*[:=]\s*[A-Za-z0-9_-]{16,}" KmMpsMcpServer tests README.md config.example.ini docs
```

Expected: 第二条无真实凭据命中。若尚未获得 Git 索引操作授权，第一条允许且只允许出现当前遗留的 `config.ini`，并将其记录为发布阻断项；完成 `git rm --cached -- config.ini` 后，第一条不得包含任何运行时文件。文档中的占位符和字段名可以存在，但不能带实值。

- [ ] **Step 5: 验证健康接口和前端助手切换**

先检查 9095 是否已被当前项目服务占用；若被占用，使用 9097。启动后必须记录 PID、监听端口和 `/api/health` 状态，并在验证完成后只停止本次启动的进程。

验证内容：

- `/api/agents` 包含 `kmrag-knowledge-agent`。
- `/api/health.kmrag` 只含 `enabled`、`configured`、`auth_mode`。
- KMRAG 未配置时其他助手仍可打开并对话。
- 在 1024x807 CEF/浏览器视口切换三个助手，介绍区、输入框、聊天记录无重叠或串线。
- 切换回默认助手和工艺助手后原界面恢复。

不要在截图、终端输出或测试请求中使用真实凭据。

- [ ] **Step 6: 在有授权的新凭据时做真实 KMRAG 联调**

该步骤只有用户提供已轮换且允许使用的本机配置后执行；否则明确标记“未做真实 KMRAG 联调”，不能宣称功能已端到端通过。

依次验证：

1. 知识库确定存在的问题 -> 有记录、自然语言答案、实际来源。
2. 确定不存在的问题 -> 固定无命中文案。
3. 无权限测试凭据 -> `KMRAG_AUTH_FAILED`，不回显凭据。
4. 不可达测试地址或停止测试服务 -> `KMRAG_UNREACHABLE`/`KMRAG_TIMEOUT`，其他助手不受影响。

- [ ] **Step 7: 最终差异和 Git 状态检查**

Run:

```powershell
git diff --check
git status --short --branch
git diff --stat
git diff --name-only
```

Expected: 只包含本功能文件和用户原有改动；没有日志、缓存、截图、运行时二进制或真实配置值。

如果 `config.ini` 仍由 Git 跟踪，在交付报告中列为发布阻断项。只有用户明确要求 staging/commit 时，才执行：

```powershell
git rm --cached -- config.ini
git add .gitignore config.example.ini
```

执行后确认本机 `config.ini` 仍存在且未被删除，并且只 stage 本任务文件。不要提交或推送，除非用户进一步明确要求。

---

## 完成定义

- KMRAG Agent 能被动态发现，且提示词不声明 3DMPS 能力。
- 模型可见工具层和 dispatcher 执行层都实施 Agent 权限隔离。
- KMRAG Skill 只接收查询文本，使用固定混合检索策略，输出经过字段白名单和长度限制的证据。
- KMRAG 空命中和所有约定错误均有确定行为，不会降级到模型常识、默认助手或 3DMPS 工具。
- 前后端会话、聊天记录、介绍区和输入提示按 Agent 隔离。
- 健康接口、日志、测试和发布源码不泄露地址或凭据。
- 所有针对性测试、编译检查和完整测试已实际运行并报告结果。
- 未取得新凭据时，真实 KMRAG 联调明确标记为未验证。
- `config.ini` 的 Git 跟踪状态在发布前得到处理；未经 Git 授权不擅自修改索引。
