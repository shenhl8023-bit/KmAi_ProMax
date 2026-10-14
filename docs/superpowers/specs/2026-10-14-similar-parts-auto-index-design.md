# 相似零件特征索引自动准备设计

**日期：** 2026-10-14  
**范围：** KmAI 相似零件查询的交付与首次使用流程

## 背景

当前相似零件查询依赖 `FeatureVectorMatcher` 读取 SQLite 特征索引。索引可以通过 `build_feature_index.py` 生成，并且已有按 XML 内容摘要和特征模型版本复用缓存、逐条提交和断点续建能力，但普通用户必须先找到脚本并手动运行。索引缺失时，查询直接返回“请先运行 build_feature_index.py”，前端没有进度、重试和恢复流程。

当前启动脚本已经把用户运行目录设置为 `%LOCALAPPDATA%\KmAI`（无 `LOCALAPPDATA` 时有回退目录），而配置中的相对特征索引路径仍解析到项目目录。交付包需要把运行产生的索引和日志放到用户可写目录，同时允许安装包携带一份与标准零件库匹配的预置索引。

## 目标与成功标准

- 普通用户首次打开相似零件功能时，不需要运行 Python 命令即可准备索引并完成查询。
- 允许自动将配置的零件库 XML 批量发送到已配置的特征服务；上传发生在后台任务中，界面显示进度。
- 预置索引存在且匹配时直接复用；零件库新增、文件内容变化或特征模型/服务版本变化时只补建缺失条目。
- 后台同一时刻最多运行一个建库任务；重复点击不会产生并发上传或 SQLite 写入竞争。
- 建库失败保留已成功条目，显示稳定错误码和可重试状态；不会泄漏上游响应正文、绝对路径或凭据。
- 相似零件查询成功响应和现有模板应用流程保持兼容。
- 命令行建库脚本继续可用于管理员预热、批量部署和问题排查。

## 非目标

- 不改变特征服务的 HTTP multipart 协议、256 维向量格式、相似度排序或旧关键词匹配语义。
- 不在启动时无条件上传整个零件库；自动建库只在相似零件功能首次使用、索引不完整或用户重试时触发。
- 不把真实 API Key、Token、内网地址或索引文件提交到源代码；预置索引作为交付制品单独放入发布包。
- 不让前端直接访问特征服务；所有上传仍由本地 Agent 完成。

## 方案选择

### 方案 A：仅首次使用自动建库

索引缺失时由 Agent 后台调用现有 `build()`，前端轮询任务状态。实现改动较小，但每台机器首次使用都要等待完整上传；无法利用标准零件库的预计算结果。

### 方案 B：只交付预置索引

安装包携带 SQLite 索引，运行时只复制并读取。首次体验最好且不需要上传，但零件库或模型版本变化后必须由管理员重新生成索引，用户无法自恢复。

### 方案 C：预置索引 + 首次自动增量建库（选定）

交付包尽量提供预置索引，运行时复制到用户缓存目录；Agent 用现有摘要和命名空间检查缺失条目，仅在需要时后台增量建库。它同时覆盖标准部署和用户零件库变化，且不改变现有断点续建能力。

## 架构设计

### 运行时索引路径

在 `agent_config` 中增加预置索引配置项 `feature_index_seed_file`。`feature_index_file` 的绝对路径继续按原样使用；相对路径在启动脚本提供 `KMAI_RUNTIME_DIR` 时解析到该目录下，例如：

```text
%LOCALAPPDATA%\KmAI\cache\similar_parts_features.sqlite3
```

没有运行时环境变量时保留现有“相对 `config.ini` 目录”的回退语义，保证命令行脚本和现有测试可用。预置索引路径始终相对发布包/config 目录解析，避免把种子文件写回用户缓存。

首次检查时，如果运行时索引不存在且种子文件存在，则通过临时文件和原子替换复制种子；目标已存在时不覆盖。运行时索引损坏时把它重命名为带唯一标识的 `.corrupt-*` 备份，然后创建新索引；损坏的种子只隔离用户目录中的副本，安装包原文件保持不变，隔离后不再次复制同一个种子。

### `FeatureIndexManager`

新增 `backend/feature_index_manager.py`，负责索引生命周期，不承担向量协议或相似度计算。它持有一个 `FeatureVectorMatcher`、一个 `RLock` 和一个守护线程任务，提供以下接口：

```python
ensure() -> dict
status() -> dict
matcher -> FeatureVectorMatcher
```

状态统一包含：

```json
{
  "state": "ready|building|failed|incomplete",
  "jobId": "...",
  "total": 20,
  "completed": 3,
  "cached": 2,
  "extracted": 1,
  "failed": 0,
  "currentFile": "",
  "errorCode": "",
  "message": ""
}
```

`ensure()` 先安装可用种子并调用 matcher 的只读索引检查，不发送网络请求。索引完整时返回 `ready`；索引缺失或不完整时启动唯一后台任务并返回 `building`；配置、零件库或索引不可恢复时返回稳定错误。建库回调逐条更新 `completed/currentFile`，每条成功结果仍由现有 matcher 立即提交，任务被中断后下次可继续。报告包含失败条目时状态为 `failed`，已成功条目保留，用户重试会继续补建。

`FeatureVectorMatcher` 增加只读 `index_status()`，按当前特征服务地址和模型版本命名空间统计零件库总数、已索引数和缺失数。它不提取当前查询零件的向量，因此状态检查不会提前上传当前零件。现有 `build()` 和 `query()` 的排序、错误码和缓存规则保持不变。

### Service 与 HTTP 数据流

`SimilarPartsService` 在初始化时创建 `FeatureIndexManager`。`query()` 在真正排名前调用 `ensure()`；如果状态是 `building`，返回 `FEATURE_INDEX_BUILDING`，避免查询线程等待整个零件库建完。测试注入的 matcher 继续被 manager 复用。

新增两个本地、仍受现有 API token 和 Origin 校验保护的接口：

```text
POST /api/similar-parts/index/ensure
GET  /api/similar-parts/index/status
```

`ensure` 在索引就绪时返回 HTTP 200，在后台任务已启动时返回 HTTP 202，响应示例：

```json
{
  "status": "success",
  "result": {
    "state": "building",
    "jobId": "...",
    "total": 20,
    "completed": 3,
    "cached": 2,
    "extracted": 1,
    "failed": 0,
    "currentFile": ""
  }
}
```

`status` 返回同一状态对象，不返回索引绝对路径。任务失败时返回 `state=failed`、`errorCode` 和面向用户的 `message`；底层异常只写本地日志，不能把上游响应正文或凭据放入响应。

查询接口保留现有成功格式。若其他调用方在建库期间直接调用查询，返回 HTTP 409、`FEATURE_INDEX_BUILDING` 和相同的任务状态；前端使用 `ensure` 流程，普通用户不会看到命令行提示。

### 前端交互

`similar_parts.js` 的 `runQuery()` 在读取当前零件后调用 `POST /index/ensure`：

1. `ready`：立即调用现有 `/api/similar-parts/query`。
2. `building`：使用 `setTimeout` 递归轮询 `/index/status`，每次根据 `completed/total` 更新面板状态，例如“正在准备相似件索引 3/20”；不使用 `setInterval`，避免面板关闭后留下定时器。
3. `failed` 或轮询超时：显示后端稳定消息和现有“重新查询”按钮，用户重试会请求新的/续建任务。
4. 面板关闭时停止后续轮询并保留已有的 AbortController、请求序号和模型清理行为。

查询结果展示、候选切换、模板编辑和应用流程不变。前端只消费状态字段，不显示本机路径。

## 错误与恢复

- 特征服务地址或模型版本未配置：立即返回现有 `FEATURE_API_NOT_CONFIGURED` 或 `FEATURE_MODEL_VERSION_MISSING`。
- 零件库不存在、为空、XML 无效或超限：返回现有稳定错误码，不启动无限重试。
- 网络超时、服务不可用或单个 XML 失败：任务进入 `failed`，记录失败数量和首个稳定错误码；已完成条目保留，重试只处理缺失条目。
- SQLite 文件损坏：先原子改名保留 `.corrupt-*` 文件，再创建新索引；无法改名时返回 `FEATURE_INDEX_INVALID`。
- 当前零件 XML 的向量提取失败：索引可以保持 `ready`，查询按现有错误处理返回，不回退到旧算法。
- 任务线程异常：捕获到 manager 状态并转换为通用 `FEATURE_INDEX_BUILD_FAILED`，不向 HTTP 响应泄漏 traceback。

## 配置与交付

`config.example.ini` 增加：

```ini
feature_index_file = cache/similar_parts_features.sqlite3
feature_index_seed_file = Resources/SimilarParts/similar_parts_features.sqlite3
```

发布包可选地放入 `Resources/SimilarParts/similar_parts_features.sqlite3`。种子缺失时仍可首次自动建库；这使同一套程序既支持带预置索引的标准交付，也支持只有 XML 库的部署。真实 `config.ini`、外部凭据、日志和运行时 SQLite 不进入源代码包。

## 测试与验收

后端测试覆盖：

1. 相对索引路径在 `KMAI_RUNTIME_DIR` 下解析，显式绝对路径保持不变。
2. 种子索引只在运行时索引缺失时原子复制，不覆盖已有索引。
3. 缺失索引触发单一后台任务，重复 `ensure()` 返回同一 `jobId`。
4. 建库进度、成功、部分失败、重试续建和模型版本变更状态正确。
5. 损坏索引会保留 `.corrupt-*` 备份并重建；失败响应不包含上游正文或绝对路径。
6. HTTP `ensure/status` 的 200/202/错误码、鉴权和查询建库中的 409 行为。
7. 既有特征 matcher、相似零件 service、模板和安全测试继续通过。

前端测试覆盖：

1. 包含 `index/ensure`、`index/status` 和进度文案；使用 `setTimeout` 轮询且没有 `setInterval`。
2. `ready` 直接查询，`building` 轮询后自动继续，`failed` 显示重试入口。
3. 不向页面输出本机绝对路径，不改变现有面板、模型和模板交互契约。

验收时使用项目现有测试脚本、Python 编译检查和一次隔离临时目录的自动建库流程；真实外部特征服务的上传成功率属于部署环境验证范围，不在离线单元测试中伪造为通过。


