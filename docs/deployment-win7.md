# Windows 7 SP1 x64 离线包与内网部署

本方案面向 x64 Windows 7 SP1 和 x64 版 3DMPS。2026-10-18 已使用用户提供的
明文客户端源码完成 CEF 109 适配、编译和离线打包。开发机已验证包内 Python、Node、
批处理启动器和根目录 CEF 客户端的启动链路；真实 Windows 7 虚拟机中的 3DMPS
联调仍需按文末步骤验收。

本次交付包位于仓库 `releases/` 目录：
`releases/KmAI-Win7-SP1-x64-20261018-r24.zip`；
大小为 200659330 字节，SHA-256 为
`bf07b1a07e04da88feb85dec1c56233234f74e500f7bc784414fb34e56636bc9`；同目录的
`.zip.sha256` 可用于校验。r24 是本次交付版本，客户端和完整
CEF/Qt 运行时位于 KmAI 包根目录，以匹配 3DMPS 的 `KmAI\\KmAiChatCef.exe`
启动路径；同时保留 legacy
`start_agent.bat/stop_agent.bat` 兼容入口，并保留导入探针和启动器的 `-B` 修复。
本版本同时将分组模板映射固定为包内的
`Resources/SimilarParts/模板/模板映射.json`，避免继续引用被排除的
`PartClassification-main` 路径。

仓库保存源代码、适配补丁、技能、配置模板和构建门禁；运行时、SDK、构建输出和
数据保存在仓库外。包内已包含 Python、Node、CEF/Qt、STEP 转换依赖及 20 组
XML/STEP 样本、模板和种子索引。目标机不需要联网安装，但 SimilarParts 相似度
查询需要获批的内网特征服务，3DMPS 主程序和命名管道服务仍由目标环境提供。

| 组件 | 本次包版本 |
| --- | --- |
| CPython x64 | 3.8.10 |
| Node.js x64 | 12.22.12 |
| CEF / Chromium | 109.1.18+gf1c41e4 / 109.0.5414.120 |
| Qt | 5.15.2 |
| VC++ / UCRT | 14.29.30159.0 / 10.0.19041.5609 |
| STEP 转换 | cascadio 0.0.17、numpy 1.24.4、trimesh 3.23.5 |
| SimilarParts 数据 | resources-snapshot-20261016，20 XML、20 STEP |

## 构建机输入

构建机需要准备以下已批准目录或文件，并保留对应版本元数据：

- 完整、隔离的 CPython 3.8.x x64 可携带运行目录：包含 `python.exe`、对应 DLL、标准库和运行所需文件；将 `python.exe.metadata.json` 放在目录内，内容至少包括 `implementation=CPython`、`version` 和 `architecture=x64`。`--python-runtime` 指向该目录中的 `python.exe`，构建器会复制整个运行目录，不会只复制 exe。
- `node.exe`：Node.js 12.22.12 x64，同时放置 `node.exe.metadata.json`，内容至少包括 `implementation=Node.js`、`version=12.22.12` 和 `architecture=x64`。
- CEF/Qt 运行时目录：放置 `cef.manifest.json` 或 `manifest.json`，包含 `version`、`chromium_version`、`qt_version`、`client_version`、`client_abi`、`win7_supported=true`、`architecture=x64` 和 `client_files`（`main_executable`、`wrapper_library`、`subprocess_executable`）。三个客户端文件必须是与该 CEF `version` 重编译的 x64 PE；只有 `libcef.dll`、Qt DLL 或 CEF 头文件的运行时目录会被构建器拒绝。CEF 109 是当前可用于 Win7 的最后一条 Chromium 主版本线；现有 CEF 126 客户端不能与 CEF 109 DLL 混用。
- SimilarParts 数据目录：放置 `manifest.json`、`similar_parts_features.sqlite3`、`XML样本/*.xml`、`STEP样本/*.stp|*.step` 和 `模板/模板映射.json`。
- STEP 转换运行时：CPython 3.8 目录内离线安装并锁定
  `cascadio==0.0.17`、`numpy==1.24.4`、`trimesh==3.23.5`；该组合提供 Win7
  目标机的实时 STEP 转 GLB 能力。
- `models` 目录：可选的 GLB 缓存；提供时仍需含批准 `version` 和
  `architecture=x64` 的 `manifest.json`，但实时读取 STEP 不依赖它。

嵌入式 CPython 发行版可能没有 `pip`。构建机应从批准的离线 wheel 中解压或用
批准的离线 pip 安装到该运行时的 `site-packages`；构建器会导入并严格校验三个版本，
目标机不执行安装。

构建机可以使用同一转换器预热 GLB 缓存，但这不是目标机实时显示的前置条件：

```powershell
py -3 tools/build_glb_cache.py `
  --step-viewer-root <step_viewer 目录> `
  --input-dir <STEP 输入目录> `
  --output-dir <GLB 输出目录>
```

目标机默认 `win7_lite_mode = false`，从 `step_library_dir` 读取 STEP，并通过包内
`step-compare/step_viewer` 与 CPython 3.8 转换依赖实时生成 GLB。若显式配置
`prebuilt_model_dir` 并打开 Lite 模式，才会绕过转换器读取缓存模型。

## 生成部署包

输出目录必须在仓库和全部输入目录之外；构建器采用白名单复制并生成
`package-manifest.json` 和 `package-SHA256.txt`。缺少运行时、CEF 或数据
版本元数据时会失败；CEF 客户端 ABI 不匹配时也会失败：

```powershell
py -3 tools/build_win7_package.py `
  --source-root <KmAI 源码根目录> `
  --output <发布输出目录>\KmAI-Win7-SP1-x64-20261018-r24 `
  --python-runtime <Python 3.8 x64 运行目录>\python.exe `
  --node-runtime <Node.js 12.22.12 x64 目录>\node.exe `
  --cef-root <CEF/Qt 运行时目录> `
  --similar-parts-data-root <SimilarParts 数据目录> `
  --win7-kb <Win7 KB2533623 文件路径>
```

上面是构建输入变量示例；复建时指定一个尚不存在的输出目录，构建器不会覆盖
已有交付。包内主要目录是 `KmMpsMcpServer/`、`runtime/`、`step-compare/`、
`step-compare/step_viewer/`、`step-compare/web/vendor/three/` 和
`Resources/SimilarParts/`。Three.js、OrbitControls、GLTFLoader 和许可证均离线
随包提供。嵌入式 Python 的 `python38._pth` 包含包根、Agent 和 STEP 转换器
的相对路径；构建门禁还执行真实 `agent_server.py --help`，验证入口可用。
`config.ini`、凭据、
日志、缓存、上传文件、`__pycache__`、`*.pyc` 和开发机用户路径不会进入包。

## 目标机安装与启动

1. 确认系统为 Windows 7 SP1 x64。若 `prerequisites/` 存在且系统尚未满足补丁基线，
   以管理员身份运行 `prerequisites\install-kb2533623.bat`，安装后手动重启；脚本
   不会自动重启，系统已安装该更新时会直接提示并退出。KB2533623 文件的 SHA-256
   为 `58b8b00113fa8b9657d8da5b14bae93f765f29651c81055e3d127d4a22e5c0d6`。
   也可以使用包含该修复的后续更新。
2. 校验 ZIP 后解压到受控的本地可写安装目录，确认文件与 `package-SHA256.txt` 一致；运行时状态默认写到安装目录之外。
3. 双击 `start_client_win7.bat` 启动客户端，首次会从 `config.example.ini` 创建 `config.ini`，已有配置不会被覆盖；客户端自动启动包内 Agent。
4. 在 `config.ini` 中填写目标环境批准的 LLM/KMRAG 值；留空 key 时使用关键词模式。SimilarParts 需填写获批的 `feature_api_base_url` 和 `feature_model_version`，再将 `enabled` 设为 `true`。
5. 与 3DMPS 集成时固定使用 `C:/tmp/3dmps-data/AIBasicInfo.xml` 和 `C:/tmp/3dmps-data/stepModel.stp`，`current_part_dir` 保持为空。样本库使用包内数据。种子特征仅在内容摘要和服务/模型命名空间一致时复用，否则自动重新建库。
6. 修改配置后重启 Agent 才生效。3DMPS 原有的 `KmMpsMcpServer\start_agent.bat`
   和 `stop_agent.bat` 调用路径已经保留：包内脚本会转发到 Win7-safe launcher，
   并继续接受同一个端口参数。重复触发 `start_agent.bat` 会复用同一个状态文件和
   Agent 进程，不会启动第二个服务。关闭 3DMPS 触发 `stop_agent.bat` 时，只停止
   该包、该端口对应的 Agent。手工启动或排查时也可直接使用 `start_win7.bat` 和
   `stop_win7.bat`：

   你的 3DMPS 实际调用路径是包内的 `3DMPS\KmAI\KmMpsMcpServer`，因此完整替换
   `KmAI` 包即可，不需要修改 `3DMPS\KmMpsMcpServer`。r24 的内部入口脚本只
   转发到 `KmAI` 根目录的 Win7 启动器，避免 Win7 `cmd.exe` 解析旧版循环和
   PowerShell 代码时返回 9009；包内 Python、状态目录和 9095 端口保持不变。
    r24 同时为 CEF 显式设置 `CefViewWing.exe`、`resources`、`resources/locales`
   路径，并关闭虚拟机常见的 GPU 合成路径，避免客户端在 CEF 初始化阶段直接退出。

```cmd
start_client_win7.bat
KmMpsMcpServer\start_agent.bat 9095
KmMpsMcpServer\stop_agent.bat 9095
stop_win7.bat 9095

rem 仅启动本地服务
start_win7.bat 9095
```

启动器将 `KMAI_WIN7_COMPAT=1`、`KMAI_PYTHON_EXE`、`KMAI_SKILL_PYTHON` 和
`KMAI_NODE_EXE` 指向包内运行时，并启用 `PYTHONUTF8=1`。日志、会话、CEF 缓存、
状态和运行时索引写入
`KMAI_RUNTIME_DIR`；未设置时依次使用 `%LOCALAPPDATA%\KmAI`、`%TEMP%\KmAI`、
`%TMP%\KmAI` 和 `%USERPROFILE%\AppData\Local\KmAI`。`stop` 通过 Win7
自带 WMIC 核对 PID、包路径、Python 路径、Agent 脚本和端口，匹配失败不会调用
`taskkill`。退出客户端窗口后 Agent 会继续运行。修改服务端口时，也需同步修改
`[WebView] url`，停止时传入同一端口。健康检查为：

```cmd
runtime\python.exe launcher.py health --port 9095
```

启动器通过免 token 的本地 `/api/startup-ping` 严格检查 KmAI Agent 身份；
`/api/health` 继续要求认证，无 token 返回 403，不能把该结果视为启动失败。

构建器在生成清单前扫描可读文本和 manifest；发现凭据样式、私钥、开发机用户目录或无法扫描的超大文本时直接失败。

## Node Skill 保留范围

`kmsoft-group-template` 仍通过 Node 脚本执行 `propose --stdin` 和
`confirm --stdin`，stdin/stdout 是 JSON，中文路径、GB2312 XML 和
`handoff.completed` 结构保持不变。Runner 按 `KMAI_NODE_EXE`、包内
`runtime\node.exe`、系统 PATH 的顺序解析 Node。目标包构建时必须使用包内 Node
12 对全部脚本执行 `--check` 及 propose/confirm 契约测试。本次 r24 包的 Node 12
语法及中文、GB2312 XML、propose/confirm 契约门禁均已通过，契约门禁不允许
跳过；Win7 模式缺少包内 Node 时直接报错。

## 验收记录

本次开发机验证记录：

- r24 ZIP 完整性检查通过，包内 1048 个 `package-SHA256.txt` 项 SHA-256
  全部匹配；`testzip()` 通过。
- r24 清单记录 `prerequisites/kb2533623`，包内 MSU 为 2314805 字节，SHA-256
  为 `58b8b00113fa8b9657d8da5b14bae93f765f29651c81055e3d127d4a22e5c0d6`；
  安装脚本为中文说明、CRLF 换行，并明确要求管理员权限和手动重启。
- 包内 CPython 3.8 的语法、真实入口及依赖导入门禁通过；Node 12 脚本和 Skill 契约门禁通过；CEF x64/ABI 和包内容扫描通过。
- 通过根目录 `KmAiChatCef.exe` 启动真实 KmAI 客户端，客户端自动拉起包内 Agent；9095 的 `/api/startup-ping` 返回 `status=ok/app=KmAI/kind=agent`，并由同目录 `KmMpsMcpServer\stop_agent.bat 9095` 成功停止。
- 用本地特征向量回放服务完成 20 个真实 XML 样本的自动建库和 Top-5 查询；当前及第二候选 STEP 均实时转换并显示，浏览器控制台无错误、无警告。回放只验证集成流程，不代表真实模型准确率验收。
- r24 包使用包内 Python `-B` 启动，启动器 health 和 `startup-ping` 检查通过；启动 Agent 时显式断开标准输入，避免 Win7 CEF 父进程句柄导致 Python 标准流初始化失败。批处理模板统一为 CRLF，内部 legacy 入口已改为无 PowerShell、无循环的直接转发，降低 Win7 `cmd.exe` 解析失败风险。Three.js 及其加载器、控制器和许可证均返回 200。
- r24 客户端在开发机启动后保持运行，并生成多个 `CefViewWing.exe` 子进程；这验证了 CEF 子进程和资源路径配置不会在初始化阶段立即崩溃。Win7 虚拟机仍需实际替换后验收。
- 重新启动实际安装目录的 Agent 后，固定的 `C:/tmp/3dmps-data/AIBasicInfo.xml` 和
  `C:/tmp/3dmps-data/stepModel.stp` 已成功读取，真实 SimilarParts current/query/template 链路将
  `JRT145-13-02计量活门衬套1.xml` 解析为 `套筒类模板.xml` 并成功读取模板内容。
- 相关启动器、打包器、legacy `start_agent/stop_agent` 入口和 SimilarParts HTTP 测试共 91 项通过（跳过 2 项），`compileall` 通过。`git diff --cached --check` 仅报告补丁文件中统一 diff 必需的空白上下文标记；其余源码和文档无空白错误。此前完整测试存在既有断言和本地 Three.js 资源缺失问题，未修改无关代码或断言来隐藏它。

仓库外的 Playwright 验收截图（r2 客户端集成证据）。
交付 ZIP 使用空白配置模板，不包含测试回放服务地址或真实凭据。

在授权的 Windows 7 SP1 x64 VM 或实机上记录以下证据后才可宣称部署验收：

- 系统、3DMPS、CEF、Python、Node 版本及 SHA-256 与清单一致；
- 启动、重复启动、端口冲突、停止和异常退出行为；
- 启动器健康检查、带认证的 `/api/health`、CEF 页面、命名管道 `\\.\pipe\3dmps_service`；
- XML 上传、SimilarParts Top-K、目标机实时 STEP 读取与 GLB 展示、模板编辑与应用；
- Node Skill 的中文 `propose`/`confirm` 和 GB2312 XML；
- 日志、状态、索引路径均在可写运行时目录。

本次没有连接真实 3DMPS、调用真实模板应用管道或访问实际特征模型服务。Win7
内核与显卡驱动、3DMPS 窗口消息和命名管道、真实模型服务仍需在目标环境验收，
不能由开发机或特征回放结果替代；CEF 输入清单中的 `win7_vm_validated` 仍保持 `false`，因为尚未连接真实 3DMPS 和命名管道。

### Windows 7 虚拟机实测记录

- Win7 Pro SP1 x64 已安装 KB2533623 和 KB2999226；安装 KB2533623 前，包内
  Python 导入 `_socket` 会报“参数错误”，安装并重启后导入成功。
- 用户提供的 r20 诊断确认包内 Python 3.8.10、Node.js 12.22.12 和 `_socket`
  均可启动；但 3DMPS 实际调用的 `KmAI\KmMpsMcpServer\start_agent.bat`
  和 `stop_agent.bat` 分别返回 9009，说明 Win7 `cmd.exe` 在旧版嵌套入口解析阶段
  已失败。诊断中端口 9095 的成功响应来自已有进程，不能作为这两个入口启动成功的证据。
- r24 已将这两个嵌套入口改为直接转发到 `KmAI` 根目录的 Win7 启停脚本；r24
  尚未在该虚拟机中重新替换并启动完整 3DMPS，故 `\\.\pipe\3dmps_service`、
  真实特征服务和窗口联调仍需目标环境验收。

## CEF/Qt 实际准备状态

已在仓库外准备 CEF 109 x64 的官方构建输入：
`<CEF 109 x64 构建输入目录>`。归档 SHA-1 为
`338ea5ebea4045405c1fe144d6ac82629120b8aa`，其中 `Release/libcef.dll` 的版本为
`109.1.18+gf1c41e4+chromium-109.0.5414.120`；同目录还保留 CEF 头文件和
`libcef_dll`，供客户端重编译使用。原 KMsoft 目录中的主程序、包装库和子进程仍是
CEF 126 组合，不能直接替换 `libcef.dll`。

2026-10-15 已补齐 Qt 5.15.2 MSVC2019 x64 开发包、MSVC 14.29.30133
（编译器 19.29.30159）和 Windows SDK 10.0.19041.0，均位于仓库外的
`<构建工具目录>`。使用 QCefView v1.1.0
（`b86fece84194f86caf78a94082c02f98df8020af`）及其 CefViewCore
（`e89ecd4f373918570e36a054e3af0604fd9100ee`）编译 CEF 109，构建产物在
`<QCefView CEF 109 构建输出目录>`，包含头文件、导入库、
`bin/QCefView.dll` 和 `bin/CefViewWing.exe`。这组包装库已与 KmAI 自有
客户端明文源码一起编译并验证页面和 JS 桥接；真实主程序联调仍待目标环境验收。

核心适配补丁保存在 `deploy/win7-compat/qcefview-1.1.0-core-cef109.patch`：
允许显式指定离线 `CEF_SDK_DIR`，并修正 CEF 109 已移除 `OnQuotaRequest`
的版本条件。对干净的上述 CefViewCore 提交执行 `git apply`；可选的
`qcefview-1.1.0-offline-demo.patch` 在 QCefView 根目录应用，让测试宿主仅加载
本地资源。构建脚本为仓库外的 `build-tools/build-qcef109.ps1`，按
`-Action Configure`、`-Action Build`、`-Action Install` 顺序执行。

当前 Windows 开发机已实际启动测试宿主，调试接口返回
`Chrome/109.0.5414.120`；Playwright 确认本地页面、iframe 和 JS 桥接对象加载，
并保留截图 `build-tools/output/playwright/qcef109-smoke.png`。PE 检查确认
两个包装层产物是 x64，`CefViewWing.exe` 的子系统版本是 6.1。这些结果不替代
Win7 SP1 x64 实机或 VM 验收。

安装后的测试宿主与实际验证的构建文件 SHA-256 一致，两个包装层产物的哈希
也已核对。构建状态、版本和哈希记录在仓库外的
`<CEF 构建状态文件>`。

2026-10-16 用户补充明文源码：
`<KmAiChatCef 明文源码目录>`，18 个 `.cpp/.h`
已用于主程序构建；Qt 工程、qrc 和图片使用此前归档中的资源，原始输入保持不变。
主程序构建脚本为 `tools/build_win7_client.ps1`，适配补丁为
`deploy/win7-compat/kmai-client-cef109.patch`。脚本显式接收明文源码、工程资源、
工具链、QCef SDK、UCRT、独立构建目录和运行时输出目录，拒绝覆盖现有输出。

适配保留窗口和 `WM_COPYDATA` 1001/1002/1003 入口、`CallBridge`，将 UI 限制为
loopback HTTP，并改为启动包内 Python launcher。包根优先使用
`KMAI_PACKAGE_ROOT`；未配置时，若 exe 同目录包含 `runtime\python.exe` 和
`launcher.py` 就使用该目录，否则回退到历史的 exe 上一级目录。日志和 CEF 用户
数据写入外部状态目录，调试端口默认关闭。

本次构建输出为仓库外的
`<KmAiChatCef 构建输出>\KmAiChatCef.exe`，
部署运行时为 `<CEF 109 客户端运行时目录>`。v9
同时加入包根目录探测、Win7 状态目录兜底、CEF 子进程和资源路径显式配置，避免
3DMPS 启动环境缺少
`LOCALAPPDATA` 或客户端位于历史 `CefView` 子目录时找不到 Agent。
主程序和子进程均为 x64、PE 子系统版本 6.1，包装库为 x64、子系统版本 6.0。
客户端构建有未使用参数及 `qtmain.pdb` 警告，构建成功；完整依赖在 Win7 的加载
结果仍以目标系统实测为准。构建状态文件记录的 CEF 109 包装层与本次主程序构建输入
保持一致。
