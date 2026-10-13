# 特征向量匹配验证记录

验证日期：2026-10-13。环境：macOS、Python 3.13、本地 KMAI HTTP 服务与当前配置的远程特征服务。真实服务地址仅保存在本机 `config.ini`。

## 结果

| 要求 | 验证证据 |
| --- | --- |
| 远程提取 256 维特征，本地余弦排序 | 20 个真实库内 XML 首次建库全部成功；当前零件查询返回五件，第一名余弦相似度 0.9591594682 |
| 增量建库与持久缓存 | 第二次 CLI 建库：total=20、cached=20、extracted=0、failed=[] |
| 内容识别自身，避免同名误置顶 | 三个真实库内 XML 改名后均返回自身第一名、similarity=1；同名不同内容的回归测试通过 |
| 可配置 Top N | 真实 Top 1000 请求返回现有的 20 件，全部有同名 STEP 和映射模板；1..1000 参数边界测试通过 |
| 当前固定 STEP 与候选同名 STEP | HTTP 查询后的当前模型和五个候选模型均返回 200、有效 glTF 头和各自不同的几何数据 |
| 映射模板读取与编辑衔接 | 五件候选模板读取均返回成功；浏览器循环切换五件后再次打开编辑器成功；编辑后暂存、候选权限和应用 HTTP 调用合同测试通过 |
| 显示与交互 | 桌面 1454×708、窄窗口 390×844 截图确认两侧模型完整显示；WebGL 采样均非空；拖动后左右视口像素摘要均变化 |
| 相机适配 | 新增窄视口回归测试先失败后通过；按包围球、水平/垂直视角调整距离，保留同步相机和形状/真实尺寸模式 |
| 无旧算法回退 | 生产查询模块没有 PartClassification 导入或 classifier 调用；服务故障、失效索引明确返回错误 |
| 不改 MCP | 改动仅涉及普通 HTTP 服务、配置、前端、建库脚本、测试和说明；工具与命名管道实现未修改 |
| 语法与静态检查 | Python compileall、两个前端模块的 Node 语法检查通过；五个涉及的 Python 运行文件通过 Python 3.8 语法解析 |

普通 HTTP 健康检查增加了非 Windows 管道占位对象的兼容处理，真实 `/api/health` 返回 `status=ok`、`pipe_available=false`，不再因缺少 `is_available` 方法中断。

## 测试命令

本次相关测试：**59 项全部通过**。

```sh
PYTHONPATH=KmMpsMcpServer:. python3 -m unittest \
  KmMpsMcpServer.tests.test_feature_vector_matching \
  KmMpsMcpServer.tests.test_similar_parts_service \
  KmMpsMcpServer.tests.test_similar_parts_config \
  KmMpsMcpServer.tests.test_similar_parts_frontend \
  KmMpsMcpServer.tests.test_similar_parts_http_api \
  tests.test_python_runtime_diagnostics
```

两组全量测试均执行了；全量结果不能表述为全部通过：

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=KmMpsMcpServer:. python3 -m unittest discover -s KmMpsMcpServer/tests -p 'test_*.py'
```

第一组 72 项：67 通过、3 失败、2 跳过。失败项使用 Windows 路径预期，与当前 macOS 路径行为不符，文件为 `tests/test_process_route_state.py`：

- `test_process_route_data_dir_expands_literal_home_env_vars`
- `test_process_route_data_dir_falls_back_to_runtime_dir_for_invalid_home`
- `test_process_route_data_dir_honors_runtime_dir_when_home_is_invalid`

第二组 183 项：178 通过、2 失败、3 错误。四项来自当前工作区缺少独立 `win7-compat` 目录，文件为 `KmMpsMcpServer/tests/test_win7_compat_package.py`：

- `test_build_manifest_forbids_machine_config_and_secrets`
- `test_package_contains_x64_runtime_contract_and_safe_launchers`
- `test_win7_config_uses_relative_prebuilt_model_directory`
- `test_launcher_check_port_action_is_executable`

另一项是已有聊天输入提示的源码断言与当前实现不一致，文件为 `KmMpsMcpServer/tests/test_chat_input_placeholder.py`：

- `test_agent_switch_placeholder_keeps_only_read_current_bof_example`

上述失败没有通过修改无关业务代码或删除测试来掩盖。

## 边界

独立审查服务两次均未能启动，因此最终检查由作者执行，不代表取得了独立审查通过意见。没有实际调用本机不存在的 Windows 3DMPS 命名管道；模板应用验证覆盖 HTTP 参数与既有工具衔接合同、模板暂存行为，真实主程序加载仍需在目标 Windows 环境确认。

本次验证证明服务接入和显示链路运行，不证明模型排序的业务准确率。百分比是余弦相似度，不是匹配概率；`feature_model_version` 是人工维护的部署标签。Python 3.8 语法检查不等于完整 Win7 安装包或目标系统兼容认证。
