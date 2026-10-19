# 相似零件与分组模板匹配

KMAI 普通 HTTP 查询使用远程 XML 特征服务提取 256 维向量，在本地 SQLite 缓存向量并计算余弦相似度。不再调用原 XML 结构指纹分类算法，也不在远程服务故障时回退到旧算法。MCP 工具实现没有改动。

## 配置

在本机 `config.ini` 的 `[SimilarParts]` 中设置：

```ini
matching_backend = feature_vector
feature_api_base_url =
feature_api_timeout_seconds = 120
feature_model_version =
feature_index_file = cache/similar_parts_features.sqlite3
# 可选的预置索引；运行时复制到用户缓存目录，不覆盖已有索引。
feature_index_seed_file = Resources/SimilarParts/similar_parts_features.sqlite3
top_k = 5
xml_library_dir =
step_library_dir =
current_xml_file =
current_step_file =
template_map_file =
```

`feature_api_base_url` 填当前部署的特征服务地址，不包含 `/api/feature/extract`。真实地址只保存在本机配置，不应进入源代码发布包。

`feature_model_version` 是管理员填写的部署标签。服务目前没有提供可验证的模型权重版本，KMAI 不会自动检测权重更新。服务更换模型、预处理或权重时必须更新这个标签并重启 KMAI；重启后首次使用相似零件功能时会按新命名空间自动补建索引，否则旧向量可能无法与新向量正确比较。

`feature_index_file` 的绝对路径按原样使用；启动脚本提供 `KMAI_RUNTIME_DIR` 时，相对路径会解析到用户可写的运行目录（例如 `%LOCALAPPDATA%\KmAI\cache`），没有该变量时回退到 `config.ini` 所在目录。`feature_index_seed_file` 始终相对配置文件所在目录解析。`top_k` 支持 1 到 1000，有效零件不足时展示实际数量；无效配置回退为 5。候选库 XML 必须有同名 STEP，模板通过 `template_map_file` 映射取得，不要求模板与零件同名。

## 自动建库和管理员预热

普通用户不需要运行命令行脚本。启动 KMAI 后点击“匹配分组模板”，系统会先调用本地 Agent 的索引准备接口：

1. 如果交付包中的 `feature_index_seed_file` 可用，先把它复制到用户运行目录；已有运行时索引不会被覆盖。
2. 如果当前 XML 库已经完整索引，直接开始查询。
3. 如果索引缺失、不完整或模型版本变化，在后台逐条补建；界面显示进度，完成后自动继续查询。
4. 单个 XML 或特征服务失败时保留已成功条目，显示稳定错误并提供重试；重试会继续缺失部分。

索引和日志写入用户运行目录，源代码发布包不应携带运行时 SQLite。预置索引是可选交付制品；没有预置索引时仍可由首次使用自动建库。

管理员可在部署前预热或排查问题时运行：

```powershell
python KmMpsMcpServer/build_feature_index.py --config config.ini
```

脚本使用 `/api/feature/extract` 的单件接口逐个处理库内 XML，上传 multipart 字段 `file_id` 与 `xml_file`。当前库规模不需要批量任务下载 NPZ，也无需增加 NumPy 或 HTTP 客户端依赖。

每件成功立即保存；再次运行只提取内容变化或没有缓存的零件。进度输出在 stderr，stdout 输出 JSON 统计。部分失败会列出文件名与错误码，并返回非零退出码；修复 XML 或服务后再次运行即可续跑。自动流程遇到损坏的索引时会先保留 `.corrupt-*` 备份，再创建新的运行时索引。

缓存由 XML 原始字节 SHA256、服务地址与部署标签共同确定。自动准备和管理员脚本都会重新检查库内文件：新增或改变的 XML 只补建缺失向量；删除的文件立即退出查询结果。索引和模型转换缓存属于本机生成数据，应排除在源代码发布包之外。

## 使用与验证

启动 KMAI 后，点击“匹配分组模板”。左侧模型仍读取固定 `current_step_file`，当前特征读取固定 `current_xml_file`；右侧按候选 XML 同名 STEP 展示。切换候选后可编辑或应用它映射的分组模板。

与库中 XML 内容完全相同的输入会优先显示自身，改名不影响识别；同名不同内容不会强制得到 100%。展示百分比是截断到 0 到 1 的余弦相似度，不是分类置信度，也不是经标定的匹配概率。向量服务没有返回分类标签，因此界面不再猜测零件类别。

远程接口错误、网络中断、超时、非 256 维向量、非有限数或零向量都会明确报错，不写入索引。客户端超时不能延长远程服务内部的单件处理超时。

实现仅使用 Python 标准库，保持 Python 3.8 语法兼容。Win7 默认通过包内
`step_viewer` 和 CPython 3.8 转换依赖实时读取 STEP；显式 Lite 模式才依赖预生成
GLB。这一接入不替代 Win7 系统、TLS、CEF 和 3DMPS 的目标机验证。

本次联调和全量测试结果见 [验证记录](feature-vector-verification-2026-10-13.md)。

自动建库、失败续建和面板关闭重开的验证见 [自动索引验证记录](similar-parts-auto-index-verification-2026-10-14.md)。
