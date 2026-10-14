# 相似零件自动索引验证记录

验证日期：2026-10-14。改动基于母体项目 `KmAi_ProMax` 的 `1944137`，工作树未提交。

## 已实现行为

- 相对运行时索引路径在启动脚本提供 `KMAI_RUNTIME_DIR` 时落到用户运行目录；绝对路径和无环境变量回退保持兼容。
- 支持可选预置 SQLite，已有运行时索引不会被覆盖；损坏的运行时索引保留 `.corrupt-*` 副本后重建，不修改安装包种子。
- 缺失或不完整索引通过唯一后台任务增量补建。HTTP ensure/status 返回进度，建库中的直接 query 返回结构化 409。
- 页面显示准备进度、完成后自动继续查询；关闭后重新打开可恢复未完成查询，失败可重试。
- 未知内部异常转换为稳定错误，不向响应返回路径或上游正文。

## 自动检查

本机 `python` 指向 WindowsApps 占位程序，`run_tests.ps1` 未能启动测试；以下使用已确认的 `py -3`（Python 3.14.5），并设置 `PYTHONUTF8=1`。服务端测试同时设置 `PYTHONPATH=KmMpsMcpServer;.` 以满足既有两种 import 方式。

| 检查 | 结果 |
|---|---|
| `py -3 -B -m unittest discover -s tests -p "test_*.py"` | 72 项，成功，2 项跳过 |
| `py -3 -B -m unittest discover -s KmMpsMcpServer\tests -p "test_*.py"` | 201 项，196 项通过，2 项断言失败、3 项错误，见下方原有问题 |
| 七个直接相关模块：manager、matcher、config、service、HTTP、frontend、HTTP security | 90 项全部通过 |
| `py -3 -m compileall -q KmMpsMcpServer tests` | 通过 |
| `git diff --check` | 通过 |

相关模块命令：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'KmMpsMcpServer;.'
py -3 -B -m unittest KmMpsMcpServer.tests.test_feature_index_manager KmMpsMcpServer.tests.test_feature_vector_matching KmMpsMcpServer.tests.test_similar_parts_config KmMpsMcpServer.tests.test_similar_parts_service KmMpsMcpServer.tests.test_similar_parts_http_api KmMpsMcpServer.tests.test_similar_parts_frontend KmMpsMcpServer.tests.test_http_api_security
```

全量测试中的原有问题与本次改动无关，对应测试及读取的聊天源码均与基线相同：

- `test_chat_input_placeholder` 有一项仍断言旧 KMRAG 示例文案，实际源码使用新的帮助示例。
- `test_win7_compat_package` 四项依赖仓库外的 `win7-compat` 交付目录，本机缺失该目录，产生一项子进程断言失败和三项文件不存在错误。

未修改这些测试、聊天源码或测试断言。测试输出仍有既有 HTTPError 和 audit 日志资源未关闭警告。

## 隔离链路与浏览器验证

使用临时 XML 库、本地模拟特征 HTTP 服务、真实 `FeatureIndexManager` 和 SQLite：首次缺索引进入 building，重复请求共享任务；部分失败保留成功条目，重试只上传失败条目，随后 query 成功。另使用两个线程和 barrier 同时请求 ensure，确认只启动一个 worker。

Chrome 实际页面连接隔离 Agent，使用临时 XML、STEP 占位及生成的测试 GLB：

1. 点击第一步，页面显示“正在准备相似件索引 0/2”。
2. 放行本地模拟特征服务后，自动展示 Top 2 候选，加载当前/候选模型并启用模板应用按钮。
3. 在另一轮全新缺索引场景中，准备期间关闭面板，再点击第一步重开，进度恢复；建库结束后同样自动展示候选。

浏览器控制台仅有测试服务未提供 favicon 的 404。未点击模板应用按钮，未向真实 3DMPS 主程序发送操作。临时服务和浏览器已关闭。

## 生效与未验证范围

部署本次源码后需要重启 Agent 并刷新/重开客户端。修改特征模型部署标签也需要重启，旧进程不会自动重载配置；重启后首次使用会补建新命名空间索引。

本次没有提供真实预置 SQLite，也没有验证生产特征服务、真实零件库上传、CEF 打包运行或目标机权限。管理员仍需在本机配置允许访问的服务地址、模型标签和数据路径；普通用户使用时不需要执行建库脚本。
