# KmAI Windows 7 SP1 x64 全面兼容改造规格

日期：2026-10-14
目标分支：`codex/win7-compat`

## 1. 目标与边界

本改造交付一个与现有 Windows 10/11 版本并行的 Windows 7 SP1 x64
兼容包。兼容包必须保留现有 HTTP Agent、原生前端、3DMPS 命名管道、
模板选择/编辑/应用流程，并保留 `kmsoft-group-template` Node Skill 的
`propose` 和 `confirm` 两个动作。

目标运行环境固定为：

- Windows 7 SP1 x64；
- x64 版本 3DMPS 及 `\\.\pipe\3dmps_service`；
- 离线可安装的本地运行包；
- 不依赖目标机访问公网、npm、PyPI、CDN 或运行时下载。

本阶段不承诺 32 位 Windows 7，也不把当前 Win10/11 CEF、Python 或 Node
二进制直接复制到目标包。兼容包的二进制由构建机提供，并由构建清单和
目标机验收锁定版本与哈希。

## 2. 已确认的现状约束

当前启动脚本要求 Python 3.10+，并使用 `Get-NetTCPConnection`、
`Start-Process`；这些路径不能作为 Win7 启动链。Skill 注册表中的三个
Python Skill 也声明了 3.10 最低版本。Node Skill 当前通过系统 PATH 中的
`node` 启动，脚本使用 `require('node:...')` 等较新的 Node API 形式。

仓库不包含可重新编译的 CEF 源码或当前 CEF 二进制，`CefView/` 只有少量
运行时配置文件。因此 CEF 的 Win7 兼容版本必须作为受控的外部构建输入，
不能在本仓库中伪造一个“已兼容”的二进制。

## 3. 兼容运行时方案

### 3.1 Python Agent

- 兼容包固定使用 CPython 3.8 x64 的完整可携带运行目录，包含解释器、DLL
  和标准库；构建器复制整个目录。目标包不依赖系统
  Python、`py` 启动器或 PowerShell 的 Python 探测。
- Agent、本地 Skill Python 和打包脚本统一经过 Python 3.8 语法/标准库
  审计；不使用 3.9+ 的类型语法、运行时 API 或未锁定的第三方依赖。
- 依赖以离线清单和构建机缓存提供。目标机禁止执行 `pip install`。
- Win10/11 的默认入口继续保留现有 Python 探测行为；Win7 入口通过
  `runtime\\python.exe` 明确指定解释器，避免改变普通版本的部署约定。

### 3.2 Node Skill（必须保留）

- 兼容包内置 x64 Node.js 12.22.12 portable runtime 作为候选锁定版本；
  实际交付前必须在 Win7 SP1 x64 VM 上验证 `node.exe --version`、脚本
  退出码和中文 stdin/stdout。该版本已停止维护，安全风险写入交付文档，
  不得伪装成受支持的长期运行时。
- `kmsoft-group-template` 的 `propose`、`confirm` 仍由 Node 脚本实现，
  不迁移为 Python，也不静默禁用。注册表动作接口、stdin JSON、stdout
  JSON 和 XML 编码契约保持不变。
- Skill Runner 增加显式 Node 解析顺序：`KMAI_NODE_EXE`、Win7 包的
  `runtime\\node.exe`、普通环境的 PATH `node`。诊断接口返回解析后的
  可执行文件、版本和错误原因，但不得返回凭据或完整环境变量。
- 对 Node Skill 脚本做兼容性改造：审计并替换 Node 12 不支持的模块前缀、
  语法和 API；不引入 npm 安装步骤。所有脚本必须在不联网、只读 Skill
  目录和中文路径下完成 propose/confirm。
- 构建时执行 Node 版本门禁：使用打包 runtime 对每个 Node Skill 脚本做
  `--check`/最小动作调用；若出现语法或 API 不兼容则构建失败。

### 3.3 CEF/Qt/3DMPS

- 兼容包要求单独的 Win7-capable CEF/Chromium x64 构建，并与现有 CEF
  客户端重新编译、链接和联调。当前 Chromium 126 运行时不作为兼容包
  输入。
- 构建清单必须记录 CEF 分支/版本、Chromium 版本、客户端版本、Qt 版本、
  x64 架构和 SHA-256；构建脚本从 PE 头确认 EXE/DLL 为 x64，并在 manifest
  缺少版本、发现架构不符或版本未锁定时
  直接失败。
- 本仓库只维护客户端源码所需的配置、启动参数和验证脚本；CEF 二进制、
  Qt DLL、3DMPS 主程序和命名管道服务由授权的内网/构建环境提供。

## 4. 启动、停止与进程生命周期

兼容包提供独立入口，不改变普通版本的 `start_agent.bat` 和
`stop_agent.bat`：

- `start_win7.bat` 和 `stop_win7.bat` 只负责定位包目录并调用
  `runtime\\python.exe launcher.py`；不使用 `Get-NetTCPConnection`、
  `Start-Process` 或 PowerShell 网络模块。
- `launcher.py` 用 Python socket 连接探测本地端口，用 `subprocess` 启动
  Agent，并把 PID、端口、脚本路径写入包外运行时目录。启动前只接受
  同一包目录和同一端口的已有实例；发现其他进程占用端口时拒绝启动。
- 停止时优先读取受保护的 PID 状态并校验命令行/脚本路径，再调用
  `taskkill /PID ... /T /F`；状态缺失或不匹配时不得按端口误杀任意进程。
- 日志放在 `%LOCALAPPDATA%\\KmAI\\logs` 或显式的 `KMAI_RUNTIME_DIR`，
  不写入源代码包；启动错误输出使用 UTF-8 可读文本。
- 启动器提供 `check-port`、`start`、`stop`、`health` 操作，便于自动化
  验收和现场排障。

## 5. Agent 与 Skill 配置

- 增加 Win7 包专用 `config.example.ini`，所有路径相对包根目录或通过
  `KMAI_RUNTIME_DIR` 重定位；不包含真实地址、Key、Token、用户名或密码。
- Win7 默认 `SimilarParts.win7_lite_mode=false`，目标机从配置的 STEP 样本目录实时读取
  STEP，通过包内 `step_viewer` 和 CPython 3.8 兼容的 cascadio 文件式 API 生成临时 GLB；
  可选的 Lite 模式仍可读取同名预生成 GLB，但不再是 Win7 的唯一路径。
- SimilarParts 排序需要获批的内网特征 API 和明确的模型版本；无公网部署不代表
  该功能完全离线。样例配置默认禁用此功能，只有填入批准地址和版本后才启用。
- Win7 包的 `step_viewer_root`、STEP/XML 数据目录使用相对路径；若启用可选 Lite 模式，
  `prebuilt_model_dir` 仍按相对路径查找，当前零件按 XML stem 优先、STEP stem 兜底，
  缺失、损坏或越界路径返回明确的结构化错误。
- Python Skill 的最低版本在兼容包 profile 中降为 3.8，并由打包的
  `runtime\\python.exe` 执行；普通版本仍可使用现有自动探测。所有 Skill
  的 registry、schema、入口脚本和错误输出一起审计。
- `kmsoft-group-template` 维持现有候选卡片、用户确认、XML 生成和
  handoff payload；Node 运行时路径只由 Runner 注入，不泄漏到业务响应。

## 6. 包装与构建布局

源代码仓库只保存可迁移的源代码、规则、模板、脚本和清单。构建机把它
组装为项目目录外的干净输出目录，例如：

```text
<workspace-parent>\\win7-compat\\
  KmMpsMcpServer\\
  runtime\\python.exe             # 同目录保留 CPython DLL、标准库等运行文件
  runtime\\node.exe
  CefView\\                      # 经过 Win7 验证的 CEF 客户端和 DLL
  step-compare\\step_viewer\\    # 目标机实时 STEP 转换代码
  config.example.ini
  launcher.py
  start_win7.bat
  stop_win7.bat
  package-manifest.json
  package-SHA256.txt
```

构建脚本必须：

1. 从干净 checkout 复制源代码和本地前端资源；
2. 接受显式的 Python、Node、CEF、3DMPS 兼容输入目录，不自行联网下载；
3. 复制并门禁 CPython 3.8 的 STEP 转换依赖，校验实时转换入口和相对路径配置；
4. 排除 `config.ini`、密钥、Token、日志、缓存、上传文件、
   `__pycache__`、`*.pyc`、开发机用户目录和未锁定二进制；
5. 生成包含来源、版本、架构、哈希和构建时间的 manifest；
6. 在输出目录中执行 launcher、Python 健康检查和 Node Skill 契约测试，
   任一失败都不生成可交付压缩包。

## 7. 验收标准

### 7.1 构建机验收

- 根目录现有测试、Agent 测试、Python 3.8 compile 检查通过；
- Node 12.22.12 对全部 Node Skill 脚本完成语法检查；
- 使用包内 Node runtime 完成 `propose` 和 `confirm`，验证中文模板、
  GB2312 XML、候选数量、schema 和 handoff payload；
- `launcher.py check-port/start/health/stop` 能在无 PowerShell 新命令的
  环境运行；
- manifest 排除项、哈希、相对路径和无凭据扫描通过；
- Win7 Lite 模式读取成功、缺失 GLB、损坏 GLB、错误路径和当前零件
  stem 回退均有测试。

### 7.2 Windows 7 SP1 x64 验收

必须在真实或授权 VM 上验证，不能用 Win10/11 结果替代：

- 系统、3DMPS、CEF 客户端、Python、Node 均为 x64 且版本与 manifest
  一致；
- 启动/停止/重复启动/端口冲突/异常退出和日志路径行为正确；
- `/api/health`、前端加载、XML 上传、相似零件 Top-K、GLB 展示、模板
  编辑与应用完整跑通；
- Node Skill 的 propose/confirm 在离线状态运行并返回正确中文结果；
- Agent 与真实 `\\.\pipe\3dmps_service` 完成命名管道调用；
- CEF 页面、3DMPS 窗口交互和五步工作流均无启动崩溃或编码错误。

## 8. 风险与明确限制

- Python 3.8 与 Node 12 均已结束上游支持；兼容包只能通过离线锁版本、
  内网制品审批、最小权限和目标机隔离降低风险，不能宣称获得新的安全
  更新。
- CEF/Chromium 是否真正支持目标 Win7 构建，取决于授权构建输入和 VM
  验收；仓库静态检查不能替代该验收。
- 本仓库当前没有 CEF 源码和二进制，因此本次代码改造可以交付兼容入口、
  构建门禁和测试，但不能在当前环境凭空生成最终 CEF 运行时。
- 在 written spec、implementation plan 和相应审批完成前，不修改生产代码、
  不安装运行时、不创建外部发布包。
