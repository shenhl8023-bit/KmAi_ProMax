# KmAI Windows 7 SP1 x64 部署包

解压到本地可写安装目录，双击 `start_client_win7.bat` 启动客户端。首次启动会从
`config.example.ini` 创建 `config.ini`；已有配置不会被覆盖。客户端自动启动本地
Agent，默认地址为 `http://127.0.0.1:9095/`。客户端和完整 CEF/Qt 运行时位于
KmAI 包根目录，直接启动 `KmAiChatCef.exe` 前，请先准备好配置文件。

包内包含 CPython 3.8.10 x64、Node.js 12.22.12 x64、CEF 109、Qt 5.15.2、
匹配的 VC++ 14.29/UCRT 发布库，以及 XML、STEP、模板和种子特征索引。目标机
不需要安装 Python/Node，也不执行联网安装。使用构建器的 `--win7-kb` 参数时，
包内还会生成 `prerequisites/`，其中包含 KB2533623 x64 离线文件、中文说明和
管理员安装脚本；运行脚本并重启后再启动客户端。未提供该参数时，Win7 仍应先
安装 SP1 和 Python 3.8 所需的 KB2533623（或包含该修复的后续更新）。

配置文件中的 LLM、KMRAG 和特征服务地址及凭据需按目标环境填写；模板不包含
真实凭据。LLM 未配置时使用现有关键词模式。SimilarParts 的相似度计算需要特征
服务：填写获批的 `feature_api_base_url`、`feature_model_version` 后将其
`enabled` 设为 `true`。修改配置后须重启 Agent 才会生效。

与 3DMPS 集成时，固定使用 `C:/tmp/3dmps-data/AIBasicInfo.xml` 和
`C:/tmp/3dmps-data/stepModel.stp`；`current_part_dir` 保持为空。样本库使用包内
`Resources/SimilarParts`。种子索引只在
内容摘要和服务/模型命名空间匹配时复用，否则由现有自动建库流程重新准备。

实时模型显示保留原 STEP 逻辑，`win7_lite_mode = false`。包内转换器
`cascadio 0.0.17`、`numpy 1.24.4`、`trimesh 3.23.5` 在目标机实时读取 STEP，
生成供前端显示的 GLB。无需预生成 GLB，源 STEP 不会被改写。

`kmsoft-group-template` Node Skill 保留 `propose`/`confirm` 的 stdin/stdout
JSON、中文路径和 GB2312 XML 契约。Win7 配置固定使用包内 Node，缺失运行时
会报错。CEF 主程序、包装库、子进程均按同一个 CEF 109 ABI 编译。

3DMPS 原有的 `KmMpsMcpServer\start_agent.bat` 和 `stop_agent.bat` 调用路径也保留：
包内这两个脚本会转发到 Win7-safe launcher，并保留第一个端口参数。因此 3DMPS
启动时可以继续调用 `start_agent.bat [port]`，关闭时继续调用
`stop_agent.bat [port]`，不需要修改原有生命周期逻辑。包根目录也提供同名别名，
兼容调用方把安装目录作为当前目录的情况。你的 3DMPS 调用路径是
`3DMPS\KmAI\KmMpsMcpServer\start_agent.bat` 和 `stop_agent.bat`，因此只需完整
替换 `KmAI` 包；包内脚本会从上一级定位 `KmAI` 根目录，确保 3DMPS 和 CEF
客户端使用同一个 Agent、端口和运行状态目录。

日志、会话、CEF 缓存、临时文件和运行时索引写入 `KMAI_RUNTIME_DIR`；未设置时依次
使用 `%LOCALAPPDATA%\KmAI`、`%TEMP%\KmAI`、`%TMP%\KmAI` 和
`%USERPROFILE%\AppData\Local\KmAI`。
可用 `KMAI_RUNTIME_DIR` 指定安装目录之外的可写目录。退出窗口后 Agent 继续
供本地程序使用；关闭客户端后运行 `stop_win7.bat` 停止 Agent。仅启动服务可用
`start_win7.bat [port]`；若调整端口，同时修改 `[WebView] url`，停止时传同一端口。

包内 `package-manifest.json` 记录版本，`package-SHA256.txt` 记录逐文件校验值。
CPython 嵌入式目录无需 pip；构建机已离线准备锁定依赖，构建门禁检查 Python 3.8
语法、导入、Node 12 脚本语法和 Skill 契约。

当前构建机验证不能替代 Windows 7 SP1 x64 实机验收。目标机还需验证实际显卡
驱动、授权特征服务、x64 3DMPS 主程序、窗口消息及 `\\.\pipe\3dmps_service`
命名管道联调。
