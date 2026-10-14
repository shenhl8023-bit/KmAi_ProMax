# 相似零件特征索引自动准备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让普通用户在首次使用相似零件查询时自动准备特征索引，并在预置索引、增量建库、进度展示和失败重试之间形成完整流程。

**Architecture:** 在现有 `FeatureVectorMatcher` 上增加只读索引检查，由新的 `FeatureIndexManager` 负责运行时索引种子复制、单实例后台建库和状态快照。`SimilarPartsService` 暴露 ensure/status 能力，查询期间以稳定错误码保护旧调用方；前端在本地 Agent 内轮询状态，完成后继续现有查询与模板流程。

**Tech Stack:** Python 3.10+、`sqlite3`、`threading`、现有 `http.server` API、原生 ES Module JavaScript、Python `unittest`。

**Spec:** `docs/superpowers/specs/2026-10-14-similar-parts-auto-index-design.md`

**Execution:** 已按用户选择在母体项目 `KmAi_ProMax` 的当前 Git 工作树内执行，未提交或推送。最终检查、原有测试失败和未验证环境详见 [验证记录](../../similar-parts-auto-index-verification-2026-10-14.md)。

## Global Constraints

- 允许首次自动把配置的 XML 零件库发送到配置的特征服务；上传只能由本地 Agent 执行，前端不直接访问特征服务。
- 相对 `feature_index_file` 在 `KMAI_RUNTIME_DIR` 存在时解析到用户运行目录；显式绝对路径和无运行环境时的现有相对路径语义保持不变。
- 预置索引是可选交付制品，不把真实配置、凭据、日志或运行时 SQLite 纳入源代码。
- 建库必须单实例、逐条提交、可断点续建；不能以旧关键词算法掩盖特征服务或索引失败。
- 不修改无关模块、不新增前端构建系统、不提交 Git；仅在用户明确要求时提交或推送。

## Review Focus

- `KMAI_RUNTIME_DIR` 缺失、存在和显式绝对路径三种索引路径必须分别落到预期位置；由 Task 1 的配置测试覆盖。
- 预置索引存在、缺失、已有运行时索引和损坏种子不能互相覆盖或丢失；由 Task 2 的种子安装测试覆盖。
- 两次并发 ensure 只能产生一个 `jobId`，并且不能并发写 SQLite；由 Task 2 的 single-flight 测试覆盖。
- 单条 XML 失败后已成功条目必须保留，重试只补建缺失条目；由 Task 2 的部分失败/续建测试覆盖。
- HTTP 202、查询期间 409 和前端轮询必须保持稳定响应契约；由 Task 3 的路由测试和 Task 4 的前端契约测试覆盖。

---

### Task 1: 配置路径与只读索引检查

**Files:**
- Modify: `KmMpsMcpServer/backend/agent_config.py`
- Modify: `KmMpsMcpServer/backend/feature_vector_matching.py`
- Modify: `config.example.ini`
- Test: `KmMpsMcpServer/tests/test_similar_parts_config.py`
- Test: `KmMpsMcpServer/tests/test_feature_vector_matching.py`

**Interfaces:**
- Produces `CONFIG["similar_parts_feature_index_seed_file"]`, resolved relative to the config/package directory.
- Produces `FeatureVectorMatcher.index_status() -> dict` returning `state` (`ready`, `missing`, `incomplete`, or `invalid`), `total`, `indexed`, and `missing` without uploading XML.

- [x] **Step 1: Write failing configuration tests**

  Add tests that set and restore `KMAI_RUNTIME_DIR`, load a temporary `config.ini`, and assert that a relative `feature_index_file` resolves below the runtime directory when the variable is set, while an absolute value remains unchanged. Add a seed-file parsing assertion and retain the current no-environment relative-path expectation.

- [x] **Step 2: Run the focused configuration tests**

  Run `python -m unittest KmMpsMcpServer.tests.test_similar_parts_config -v`.

  Expected: the new runtime-path assertions fail before implementation, while unrelated existing assertions remain informative.

- [x] **Step 3: Implement runtime-aware config loading**

  Add a small path resolver in `agent_config.py` used only for `feature_index_file`; expand `KMAI_RUNTIME_DIR` before joining a relative value, and use the existing config-base resolver when the variable is absent. Parse and resolve `feature_index_seed_file` with the config-base resolver. Add the corresponding example entry and comments without inserting credentials or a real seed file.

- [x] **Step 4: Write failing matcher status tests**

  Add tests for missing index, complete index, changed/new library XML, and malformed SQLite. Assert the returned state/counts and that the fake feature service receives no request during `index_status()`.

- [x] **Step 5: Implement `FeatureVectorMatcher.index_status()`**

  Reuse `_library`, `client.namespace`, `_database`, `_read_xml`, and `_cached`. Convert only index absence/corruption into status values; preserve existing `FeatureVectorError` behavior for invalid API configuration and XML library errors. Do not mutate the database or extract the current query XML.

- [x] **Step 6: Run the focused matcher and configuration tests**

  Run `python -m unittest KmMpsMcpServer.tests.test_similar_parts_config KmMpsMcpServer.tests.test_feature_vector_matching -v`.

  Expected: PASS, including the existing multipart, namespace, partial-build, corruption, and CLI tests.

### Task 2: Runtime seed installation and single-instance background manager

**Files:**
- Create: `KmMpsMcpServer/backend/feature_index_manager.py`
- Test: `KmMpsMcpServer/tests/test_feature_index_manager.py`

**Interfaces:**
- Consumes: `FeatureVectorMatcher.index_status()`, `FeatureVectorMatcher.build(progress=...)`, `FeatureVectorError`, and the resolved config keys from Task 1.
- Produces `FeatureIndexManager(config, matcher=None, thread_factory=None)`, `.matcher`, `.ensure() -> dict`, and `.status() -> dict`.

- [x] **Step 1: Write failing manager tests**

  Use a deterministic fake matcher and temporary paths to pin these cases: seed copied atomically only when the runtime target is absent; ready index does not start a thread; two ensure calls share one job; progress fields advance; a partial report becomes `failed` while successful entries remain available; a later ensure starts a resumable retry; invalid SQLite is renamed to `.corrupt-*` before rebuilding.

- [x] **Step 2: Run the manager tests to verify the missing implementation**

  Run `python -m unittest KmMpsMcpServer.tests.test_feature_index_manager -v`.

  Expected: import or interface failures before the manager exists.

- [x] **Step 3: Implement `FeatureIndexManager`**

  Protect state transitions with `RLock`, create one daemon worker per active job, install a configured seed with temporary file plus `os.replace`, and quarantine corrupt runtime indexes without deleting them. `ensure()` must inspect before starting work, return the same snapshot/job ID while running, and map unrecoverable `FeatureVectorError` values to stable state data. The build callback updates `completed`, `cached`, `extracted`, `failed`, and `currentFile`; the worker catches unexpected exceptions and records `FEATURE_INDEX_BUILD_FAILED` without traceback or upstream body.

- [x] **Step 4: Run manager tests and the existing feature matcher suite**

  Run `python -m unittest KmMpsMcpServer.tests.test_feature_index_manager KmMpsMcpServer.tests.test_feature_vector_matching -v`.

  Expected: PASS with one worker per job and no regression in the existing matcher behavior.

### Task 3: Service and HTTP lifecycle endpoints

**Files:**
- Modify: `KmMpsMcpServer/backend/similar_parts_service.py`
- Modify: `KmMpsMcpServer/backend/http_api.py`
- Test: `KmMpsMcpServer/tests/test_similar_parts_service.py`
- Test: `KmMpsMcpServer/tests/test_similar_parts_http_api.py`

**Interfaces:**
- Produces `SimilarPartsService(..., index_manager=None)`, `.ensure_feature_index() -> dict`, and `.feature_index_status() -> dict`.
- Adds `POST /api/similar-parts/index/ensure` and `GET /api/similar-parts/index/status`.
- Extends `SimilarPartsError` with optional structured details so `FEATURE_INDEX_BUILDING` can carry only the public status snapshot.

- [x] **Step 1: Write failing service tests**

  Add service tests with an injected manager/fake matcher asserting ready, building, and failed states, and that `query()` refuses to rank while a build is running with `FEATURE_INDEX_BUILDING` and no direct matcher query.

- [x] **Step 2: Write failing HTTP route tests**

  Extend the stub service in `test_similar_parts_http_api.py` with ensure/status methods. Assert authenticated ensure returns 200 for ready and 202 for building, status returns the same public fields, query-in-progress returns 409 with `FEATURE_INDEX_BUILDING`, and unauthenticated status is rejected.

- [x] **Step 3: Implement service lifecycle delegation**

  Construct one manager per `SimilarPartsService` unless the optional `index_manager` test seam is supplied, reuse an injected matcher in the manager, call ensure before the existing matcher query, and translate a non-ready state into a structured 409 error. Keep successful query payloads and template/model handling untouched.

- [x] **Step 4: Implement the HTTP routes and safe error serialization**

  Add the two routes in the existing authenticated POST/GET dispatch. Return 200/202 for ensure as defined by the spec, keep status payloads path-free, and include structured details only for the known feature-index error. Do not expose exception text from unknown failures.

- [x] **Step 5: Run service, HTTP, and security tests**

  Run `python -m unittest KmMpsMcpServer.tests.test_similar_parts_service KmMpsMcpServer.tests.test_similar_parts_http_api KmMpsMcpServer.tests.test_http_api_security -v`.

  Expected: PASS, including existing upload/current/query/template/model behavior and API token/origin checks.

### Task 4: Frontend automatic preparation and progress UX

**Files:**
- Modify: `KmMpsMcpServer/frontend/assets/modules/similar_parts.js`
- Test: `KmMpsMcpServer/tests/test_similar_parts_frontend.py`

**Interfaces:**
- Consumes `POST /api/similar-parts/index/ensure`, `GET /api/similar-parts/index/status`, and the public state fields from Task 3.
- Preserves `openSimilarPartsPanel`, current-part loading, candidate rendering, model cleanup, retry button, and template application contracts.

- [x] **Step 1: Write failing frontend contract assertions**

  Assert that the module calls both index endpoints, contains progress text using `completed/total`, handles `FEATURE_INDEX_BUILDING`, uses recursive `setTimeout` polling, and still contains the existing query/template endpoints without introducing `setInterval`, file upload UI, or absolute local paths.

- [x] **Step 2: Implement the preparation/polling helpers**

  Add local helpers that normalize the response envelope, render “正在准备相似件索引 x/y”, poll with bounded delay and total timeout, stop when the panel is closing, and throw the backend message on failed/timeout states. Keep all requests on the existing `requestJsonPromise` wrapper so API token behavior is unchanged.

- [x] **Step 3: Integrate preparation into `runQuery()`**

  After `loadCurrentPart()` and before `/api/similar-parts/query`, call ensure and wait for ready. Treat a direct `FEATURE_INDEX_BUILDING` query response as the same polling path for compatibility with other callers. Keep the existing retry button visible on failure and automatically continue the existing result/model flow after readiness.

- [x] **Step 4: Run the frontend contract tests**

  Run `python -m unittest KmMpsMcpServer.tests.test_similar_parts_frontend -v`.

  Expected: PASS, with static contract coverage for the new flow and all existing viewer/template assertions.

### Task 5: Full verification and delivery checks

**Files:**
- Review: all files changed by Tasks 1–4
- Optional delivery artifact: `Resources/SimilarParts/similar_parts_features.sqlite3` (only if a validated prebuilt index is supplied; do not create a fake one)

- [x] **Step 1: Run all project tests**

  Run `.\run_tests.ps1`; if the script cannot run on the current host, run both configured unittest discoveries:

  `python -m unittest discover -s tests -p "test_*.py"`  
  `python -m unittest discover -s KmMpsMcpServer\tests -p "test_*.py"`

- [x] **Step 2: Run static and syntax checks**

  Run `python -m compileall -q KmMpsMcpServer tests` and inspect `git diff --check` in the implementation Git worktree. Confirm no changed file contains credentials, absolute user data paths, logs, or generated SQLite.

- [x] **Step 3: Exercise an isolated automatic-build flow**

  Use a temporary XML library and a local fake feature HTTP server to verify missing-index ensure, progress polling, query continuation, partial failure, and retry. Record that this validates the local lifecycle only; it does not claim the external production feature service is healthy.

- [x] **Step 4: Review the final delivery boundary**

  Confirm the shipped `config.example.ini` documents the seed path and runtime index behavior, the normal user path contains no command-line step, and the admin CLI remains documented as a fallback. Preserve unrelated working-tree changes and report any unverified Windows/CEF packaging behavior explicitly.


