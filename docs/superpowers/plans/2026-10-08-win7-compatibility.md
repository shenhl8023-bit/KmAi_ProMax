# KmAI Windows 7 SP1 x64 全面兼容改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个保留现有 Agent、3DMPS 命名管道、相似零件实时 STEP 预览和 Node Skill 的 Windows 7 SP1 x64 离线兼容包。

**Architecture:** 普通 Win10/11 入口保持不变，Win7 使用独立的 `deploy/win7-compat` 包模板和项目目录外的构建输出。Skill Runner 根据兼容 profile 选择包内 CPython 3.8 与 Node 12.22.12，启动器使用 Python socket、`subprocess` 和 `taskkill`，相似零件在目标机通过包内 `step_viewer` 和 Win7-capable cascadio 实时读取 STEP；预生成 GLB 仅作可选缓存。CEF/Qt/3DMPS 二进制作为带版本和哈希的外部构建输入，构建脚本拒绝缺失或未锁定的输入。

**Tech Stack:** Python 3.8 x64、Node.js 12.22.12 x64、Windows batch、Python 标准库、现有原生 ES Module 前端、JSON/INI/GLB、Windows 命名管道。

**Spec:** `docs/superpowers/specs/2026-10-08-win7-compatibility-design.md`

## Global Constraints

- 目标固定为 Windows 7 SP1 x64 和 x64 版本 3DMPS。
- Win7 包内置完整 CPython 3.8 x64 运行目录（入口为 `runtime\\python.exe`）和 `runtime\\node.exe`（Node 12.22.12 x64 候选版本）。`KMAI_RUNTIME_DIR` 只存放可写状态、索引和日志，不作为程序安装目录。
- `kmsoft-group-template` 的 `propose`、`confirm`、stdin/stdout JSON、XML 和 handoff payload 契约必须保留。
- Win7 启停路径不得使用 `Get-NetTCPConnection`、`Start-Process` 或运行时联网安装依赖。
- `SimilarParts.win7_lite_mode=false` 时目标机实时执行 STEP 解析和网格化；Lite 模式只作为显式配置的 GLB 缓存回退。
- CEF/Qt/3DMPS 二进制不从当前仓库伪造；构建必须接收显式外部输入并记录版本、架构和 SHA-256。
- 不修改原始工作区，不丢弃无关修改，不提交或推送；提交仅在用户另行明确要求时进行。
- 不把 `config.ini`、凭据、日志、缓存、上传文件、`__pycache__` 或 `*.pyc` 放入发布输出。

## Review Focus

- Win7 profile 下包内 Node 路径必须优先于 PATH，缺失时要返回可诊断错误；由 Task 1/2 的 Runner 解析和诊断测试覆盖。
- 普通环境的 Python 3.10 最低版本不能被 Win7 的 3.8 profile 静默降低；由 Task 1 的 profile 隔离测试覆盖。
- 中文路径、中文 stdin/stdout 和 GB2312 XML 必须在 Node Skill 中保持完整；由 Task 2 的 propose/confirm 契约测试覆盖。
- PID 被复用、状态文件缺失或命令行不匹配时，stop 不能误杀其他进程；由 Task 4 的 launcher 安全测试覆盖。
- 缺少 CEF/Node/Python/相似零件数据外部输入、打包文本或 manifest 含凭据值/开发机用户路径时，构建必须失败；由 Task 5 的 manifest/build gate 测试覆盖。
- Lite 模式中的 GLB 缺失、损坏、路径越界和 XML stem/STEP stem 回退必须返回结构化结果；由 Task 3 的相似零件测试覆盖。

---

### Task 1: 为 Skill Runner 增加 Win7 runtime profile

**Files:**
- Modify: `KmMpsMcpServer/skills/runner.py`
- Modify: `KmMpsMcpServer/skills/__init__.py`
- Modify: `KmMpsMcpServer/skills/process-route-generator.json`
- Modify: `KmMpsMcpServer/skills/technical-requirements-generator.json`
- Modify: `KmMpsMcpServer/skills/kmrag-search.json`
- Test: `tests/test_skill_runtime_resolution.py`
- Test: `tests/test_skill_runtime_diagnostics.py`

**Interfaces:**
- `SkillRunner._resolve_node_command() -> list[str]`：按 `KMAI_NODE_EXE`、从 Runner 文件位置推导的包根 `runtime\\node.exe`、PATH `node` 顺序返回命令数组。
- `SkillRunner._minimum_python_version() -> tuple[int, int]`：`KMAI_WIN7_COMPAT=1` 时读取动作的 `python_min_version_win7`，否则保持现有 `python_min_version`；普通 profile 默认下限仍为 3.10。初始化保留两种配置值，执行与诊断都调用此方法。
- `SkillRunner._build_cmdline(request) -> list[str]`：`node` 动作使用 `_resolve_node_command()`，`python-auto` 使用 profile 选择后的 Python 命令。
- `skills._diagnose_runner_runtime(runner) -> dict`：返回 `resolved_command`、`resolved_version`、`ok` 和不含凭据的错误码。

- [x] **Step 1: Write the failing tests**

  在 `tests/test_skill_runtime_resolution.py` 中增加：

  - `test_win7_node_env_executable_has_priority_over_path`：设置 `KMAI_WIN7_COMPAT=1` 和临时 `KMAI_NODE_EXE`，断言 `_build_cmdline({})[0]` 为该路径。
  - `test_node_falls_back_to_package_runtime_before_path`：清除 `KMAI_NODE_EXE`，在临时包根创建 `runtime\\node.exe`，断言不调用 PATH 中的 Node；另断言 `KMAI_RUNTIME_DIR` 不会被当作安装目录。
  - `test_win7_python_profile_accepts_38_but_default_keeps_310`：同一 action 在 Win7 profile 下最低版本为 `(3, 8)`，普通 profile 下仍为 `(3, 10)`。
  - `test_missing_win7_node_reports_structured_error`：没有 Node 时断言 `NODE_NOT_FOUND`，且错误不包含环境变量全文。

- [x] **Step 2: Run tests to verify they fail**

  Run: `py -3 -m unittest tests.test_skill_runtime_resolution tests.test_skill_runtime_diagnostics -v`

  Expected: FAIL because Node command resolution and Win7 Python profile do not exist.

- [x] **Step 3: Implement the runtime profile**

  在 `SkillRunner` 中增加 Node 命令解析、Node 版本探测和 Python profile 选择，并在初始化时解析普通/Win7 两种最低版本；在三个 Python Skill action 中增加 `python_min_version_win7: "3.8"`。更新 `skills.__init__` 的诊断路径，使 Node 和 Python 都使用 Runner 的解析结果，并保留现有普通环境行为。

- [x] **Step 4: Run the focused tests**

  Run: `py -3 -m unittest tests.test_skill_runtime_resolution tests.test_skill_runtime_diagnostics -v`

  Expected: PASS, including the existing Node diagnostic tests.

### Task 2: 让 kmsoft-group-template 在锁定 Node runtime 下运行

**Files:**
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/template_core.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/select_group_template.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/validate_template.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/parse_template.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/build_template.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/apply_operations.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/list_features.js`
- Modify: `KmMpsMcpServer/skills/kmsoft-group-template/scripts/recommend_template.js`
- Test: `tests/test_node_skill_compatibility.py`
- Test: `KmMpsMcpServer/tests/test_group_template_response_contract.py`

**Interfaces:**
- 保留现有 `select_group_template.js propose --stdin` 和 `confirm --stdin` 输入输出，不增加 npm 或网络依赖。
- 测试辅助函数 `_run_node_skill(action, payload, node_exe=None) -> dict` 使用 `KMAI_NODE_EXE` 或显式 Node 路径。

- [x] **Step 1: Write the failing compatibility tests**

  增加 Node runtime 测试：遍历所有 Node Skill `.js` 文件执行 `--check`；使用中文零件描述执行 `propose`，从候选中选择 `templateId` 执行 `confirm`，断言 `ok=true`、`xml` 含 GB2312 声明、`handoff.completed=true`，并断言 stderr 不含绝对用户路径或凭据字段。

- [x] **Step 2: Run tests to establish the compatibility failure**

  Run: `py -3 -m unittest tests.test_node_skill_compatibility KmMpsMcpServer.tests.test_group_template_response_contract -v`

  Expected: tests require explicit Node 12.22.12 for compatibility claims. If it is absent locally, record that the local run cannot establish Node 12 compatibility; the final package build gate must fail closed when the runtime input is absent.

- [x] **Step 3: Apply the smallest Node 12 source changes**

  将 `require('node:fs')`、`require('node:path')`、`require('node:crypto')`、`require('node:child_process')` 等替换为 Node 12 可用的标准模块写法；根据锁定 Node 的 `--check` 和动作结果，逐项下调不支持的语法/API，不改变排序、模板选择、XML 编码和 schema 行为。

- [x] **Step 4: Run syntax and behavior checks**

  Run with `$Node12Exe` set to the approved Node 12.22.12 executable: `& $Node12Exe --check KmMpsMcpServer/skills/kmsoft-group-template/scripts/select_group_template.js` and `py -3 -m unittest tests.test_node_skill_compatibility KmMpsMcpServer.tests.test_group_template_response_contract -v`.

  Expected: all scripts parse and propose/confirm contract tests pass. The final package build repeats these checks with the bundled Node 12 runtime.

### Task 3: 固化 Python 3.8 兼容边界和 GLB Lite 行为

**Files:**
- Create: `tools/check_python_compat.py`
- Create: `tools/build_glb_cache.py`
- Modify if the Python 3.8 gate identifies incompatibilities: `KmMpsMcpServer/**/*.py` and `KmMpsMcpServer/skills/*/scripts/*.py`
- Modify: `KmMpsMcpServer/backend/similar_parts_service.py` only where the focused tests identify a missing guard
- Test: `tests/test_python_compatibility_gate.py`
- Test: `tests/test_build_glb_cache.py`
- Test: `KmMpsMcpServer/tests/test_similar_parts_service.py`
- Test: `KmMpsMcpServer/tests/test_similar_parts_config.py`

**Interfaces:**
- `tools/check_python_compat.py --python-exe <path> --source <path> [<path> ...]`：用显式解释器确认 CPython 3.8 x64 并编译指定文件/目录中的运行时代码，不做广泛 import，避免触发命名管道、NXOpen 或服务启动副作用；返回非零表示不兼容。
- Python 3.8 运行门禁另执行 root 与 Agent unittest suites；如果技能脚本使用不兼容的运行时 API，修复后再通过门禁，不以编译成功替代行为验证。
- `tools/build_glb_cache.py --step-viewer-root <path> --input-dir <path> --output-dir <path>`：在构建机调用现有 `step_viewer.tessellate.tessellate_step`，生成 `<stem>.glb` 和可选 `<stem>.json` sidecar，目标包不携带 STEP 转换器。
- `SimilarPartsService.get_model(model_id) -> (bytes, dict)`：Lite 模式继续绕过 tessellator，错误使用现有 `SimilarPartsError.code`。

- [x] **Step 1: Add failing tests for the compatibility/build gates**

  测试 Python gate 能接收显式 CPython 3.8 x64 并扫描最终将打包的 Agent、Skill 和 launcher Python 文件；测试 GLB builder 用隔离转换器 fixture 对有效 STEP 生成 `glTF` 头和 metadata、对无效 STEP 返回非零；补充 Lite 模式的损坏 GLB、绝对路径/越界路径、XML stem 优先和 STEP stem 兜底断言。`PartClassification-main` 的包声明要求 Python 3.10+，其 Python 代码不纳入 Win7 运行包，只将经批准的样本和模板数据作为独立输入。

- [x] **Step 2: Run the focused tests**

  Run: `py -3 -m unittest tests.test_python_compatibility_gate tests.test_build_glb_cache KmMpsMcpServer.tests.test_similar_parts_service KmMpsMcpServer.tests.test_similar_parts_config -v`

  Expected: new gate/builder tests fail before implementation; existing Lite tests remain the behavior baseline.

- [x] **Step 3: Implement the build-machine-only tools and guards**

  `check_python_compat.py` 只使用显式 CPython 3.8 解释器，不自动下载依赖；它扫描最终包中 Agent、Skill、launcher 和实时 STEP viewer Python 文件。`build_glb_cache.py` 可在构建机当前 Python 环境预热 GLB，仅写入指定输出目录并拒绝输出目录逃逸。Win7 包保留 `step_viewer` 转换运行时，Lite 缓存只作可选回退。

- [x] **Step 4: Run the focused tests**

  Run: `py -3 -m unittest tests.test_python_compatibility_gate tests.test_build_glb_cache KmMpsMcpServer.tests.test_similar_parts_service KmMpsMcpServer.tests.test_similar_parts_config -v`

  Expected: fixture tests pass on the current interpreter; the package compatibility gate must run using explicit CPython 3.8 x64. Do not claim Python 3.8 compatibility without that executable.

### Task 4: 创建不依赖新 PowerShell 命令的 Win7 launcher

**Files:**
- Create: `deploy/win7-compat/launcher.py`
- Create: `deploy/win7-compat/start_win7.bat`
- Create: `deploy/win7-compat/stop_win7.bat`
- Create: `deploy/win7-compat/config.example.ini`
- Create: `deploy/win7-compat/requirements-win7-x64.txt`
- Test: `tests/test_win7_launcher.py`

**Interfaces:**
- `launcher.py check-port --host 127.0.0.1 --port <int> -> exit code`：socket 探测，不启动进程。
- `launcher.py start --port <int> -> exit code`：启动包内 Agent，写入运行时状态。
- `launcher.py health --port <int> -> exit code`：检查 `/api/health`。
- `launcher.py stop --port <int> -> exit code`：校验状态和命令行后执行 `taskkill /PID <pid> /T /F`。
- 状态文件包含 `pid`、`port`、`agent_script`、`package_root`，存放在可写的 `KMAI_RUNTIME_DIR` 或 `%LOCALAPPDATA%\\KmAI`；两者均不可用时启动失败，不写入安装包目录。

- [x] **Step 1: Write failing launcher tests**

  测试 `check-port` 在未监听端口返回 0；测试 start 生成状态并传递 `KMAI_WIN7_COMPAT=1`、`KMAI_PYTHON_EXE`、`KMAI_SKILL_PYTHON`、`KMAI_NODE_EXE` 和独立的可写数据目录；测试 stop 通过 `wmic process where ProcessId=<pid> get CommandLine /value` 读取命令行，只对包含包内 Python、精确 Agent 脚本路径和相同端口的进程调用 `taskkill`，对查询失败、PID 复用或路径/端口不匹配拒绝调用；读取 batch 文件并断言不含 `Get-NetTCPConnection`、`Start-Process`，且调用 `runtime\\python.exe launcher.py`。

- [x] **Step 2: Run tests to verify they fail**

  Run: `py -3 -m unittest tests.test_win7_launcher -v`

  Expected: FAIL because the deployment templates and launcher do not exist.

- [x] **Step 3: Implement launcher and batch wrappers**

  使用 Python 标准库 socket、urllib、subprocess、JSON 和临时日志文件；进程命令行校验使用 Win7 自带 WMIC 并严格比较 PID、包内 Python、Agent 脚本和端口，查询失败/不匹配时不执行 kill。batch 只设置包根、可写数据/日志目录、Python/Node runtime 环境并转调 launcher。

- [x] **Step 4: Run launcher tests**

  Run: `py -3 -m unittest tests.test_win7_launcher -v`

  Expected: PASS, including safe stop and forbidden-command assertions.

### Task 5: 构建干净的外部 Win7 包输出

**Files:**
- Create: `tools/build_win7_package.py`
- Create: `tools/build_win7_package.ps1`
- Create: `deploy/win7-compat/package-manifest.json`
- Create: `deploy/win7-compat/README.md`
- Test: `tests/test_win7_package_builder.py`
- Modify: `KmMpsMcpServer/tests/test_win7_compat_package.py`

**Interfaces:**
- `build_package(source_root, output_root, python_runtime, node_runtime, cef_root, similar_parts_data_root, models_root=None) -> dict`：复制白名单源代码、实时 STEP viewer 和显式批准的相似零件数据，复制外部 runtime/CEF，生成 manifest 和 `package-SHA256.txt`，可选复制 GLB 缓存。
- CLI：`py -3 tools/build_win7_package.py --source-root <repo> --output <dir> --python-runtime <python.exe> --node-runtime <node.exe> --cef-root <dir> --similar-parts-data-root <dir> [--models-root <dir>]`。`--python-runtime` 指向隔离 CPython 分发目录中的 `python.exe`，builder 复制其完整父目录并排除相邻版本元数据。
- 默认输出为 `<workspace-parent>\\KmAI-win7-x64-package`，不污染 Git 工作树；缺失任何显式输入、架构/版本未锁定、绝对用户路径或秘密扫描命中时返回非零。

- [x] **Step 1: Write failing package tests**

  使用临时 fixture 验证 builder 复制 `KmMpsMcpServer` 运行时代码、完整 CPython 目录（exe、DLL、标准库配置，排除版本元数据）、`Resources/SimilarParts` 预置索引、经批准的 XML/STEP/模板数据和 `step-compare/step_viewer`；排除 `config.ini`、日志、缓存、`__pycache__`、`*.pyc` 和整个开发工程；验证 manifest 含 Python/Node/CEF/数据版本和哈希；缺少或未锁定输入时失败，并拒绝输出落入源码或外部输入目录。

- [x] **Step 2: Run tests to verify they fail**

  Run: `py -3 -m unittest tests.test_win7_package_builder KmMpsMcpServer.tests.test_win7_compat_package -v`

  Expected: FAIL because the builder and package templates do not exist; the existing contract test is changed to read the in-repository package template, while builder integration tests use a temporary output directory.

- [x] **Step 3: Implement the whitelist builder and manifest**

  构建器只复制明确白名单，使用 SHA-256 生成清单；将 CEF、经批准的相似零件数据、Python 和 Node 视为显式输入；对 CPython 3.8 执行 cascadio/numpy/trimesh 导入门禁；输出包内 Node Skill 运行时变量指向 `runtime\\node.exe`，并只复制 `step_viewer` 转换源代码。修改 `KmMpsMcpServer/tests/test_win7_compat_package.py`，使其校验仓库内模板路径而不是假设外部 sibling 包已存在；真实 builder 输出由临时目录集成测试验证。

- [x] **Step 4: Run package tests and a dry build**

  Run: `py -3 -m unittest tests.test_win7_package_builder KmMpsMcpServer.tests.test_win7_compat_package -v`.

  Expected: PASS with test fixtures. A real build additionally requires approved CPython 3.8 (with STEP wheels), Node 12.22.12, Win7-capable CEF and SimilarParts data; GLB models are optional.

### Task 6: 更新文档、运行全量验证并保留未验证边界

**Files:**
- Modify: `README.md`
- Create: `docs/deployment-win7.md`
- Modify: `docs/superpowers/plans/2026-10-08-win7-compatibility.md` only for task checkboxes and evidence
- Test: existing root and Agent test suites
- Manual acceptance: authorized Windows 7 SP1 x64 VM with x64 3DMPS and matching 3DMPS named pipe

**Interfaces:**
- 文档必须给出构建机输入、离线安装步骤、`config.ini` 创建步骤、Node Skill 保留说明、实时 STEP 转换与可选 GLB 预生成步骤和 Win7 VM 验收表。

- [x] **Step 1: Write deployment documentation from implemented interfaces**

  只记录实际存在的命令和路径，明确 Python 3.8/Node 12 的 EOL 风险、CEF 外部输入边界和“当前环境未完成 Win7 VM 验收”的状态。

- [x] **Step 2: Run repository verification**

  Run sequentially from the worktree root:

  ```powershell
  git diff --check
  py -3 -m compileall -q KmMpsMcpServer tests tools
  py -3 -m unittest discover -s tests -p "test_*.py"
  .\run_tests.ps1
  ```

  当前结果：`git diff --check`、`compileall`、根套件 98 项通过（4 项因环境缺少 Node 12/Win7 输入跳过）。`run_tests.ps1` 的 Agent 套件 204 项中有 1 项既有占位符断言失败；基线提交中的 `chat.js` 已使用“自动识别怎么使用”，测试却要求“查询公司的供应商准入流程”，因此不归因于本次改造。显式 CPython 3.8、Node 12 和 Win7 输入仍须在授权构建/验收环境执行，不能由当前主机替代。

- [x] **Step 3: Run package contract verification**

  Run the builder fixture tests and, when approved runtime inputs are available, build the external package and execute `launcher.py check-port`, Python health check, Node `--check`, `propose`, and `confirm` from the extracted output.

- [ ] **Step 4: Record manual Win7 acceptance as evidence**

  On an authorized Windows 7 SP1 x64 VM with matching 3DMPS, record system/runtime versions, SHA-256 manifest match, startup/stop, `/api/health`, CEF UI, GLB display, template application, Node Skill propose/confirm, and named-pipe calls. If no VM or CEF inputs are supplied, leave this checkbox unchecked and report the exact boundary.

## Latest verification after compatibility review

- Launcher now requires an external writable runtime directory, verifies the state package root and exact Python/script/port command-line tokens before accepting or stopping a process, and rejects a healthy unrelated listener.
- Win7 Skill Python and Node resolution fail closed when the packaged runtimes are unavailable; the builder validates the CPython directory layout and scans staged text/manifest files for credentials, private keys, developer paths, metadata sidecars, and oversized text.
- Focused compatibility tests: 43 tests passed, 2 skipped (Node 12.22.12/explicit external runtime unavailable).
- Root suite: 112 tests passed, 4 skipped because Node 12/Win7 external inputs are unavailable.
- `run_tests.ps1` under execution-policy bypass: root suite passed; Agent suite has 204 tests with one pre-existing `chat.js` placeholder assertion failure and three existing Node subprocess/console-encoding errors on this host (the tests use text-mode decoding while Node emits UTF-8).
- `git diff --check` and `py -3 -m compileall -q KmMpsMcpServer tests tools` passed. Actual CPython 3.8, Node 12.22.12, Win7 CEF/Qt, 3DMPS named pipe, and Windows 7 VM acceptance remain pending external authorized inputs.
