# Similar Part Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an XML-driven Top 3 similar-part search to KMAI with side-by-side STEP rendering and one-click application of the selected candidate's group template.

**Architecture:** KMAI gains a standalone ordinary-HTTP orchestration service that lazily reuses `part_classification` for XML similarity and `step_viewer.tessellate` for STEP-to-GLB conversion. The existing five-step workflow opens a dedicated native ES-module comparison panel for step 1; template application calls the existing `apply_group_template` tool without changing MCP definitions or implementations.

**Tech Stack:** Python 3.10+, `http.server`, existing PartClassification package, existing cascadio/trimesh STEP conversion, vanilla ES modules, Three.js.

**Spec:** `docs/superpowers/specs/2026-09-29-similar-part-query-design.md`

## Global Constraints

- Do not modify MCP function definitions, `tool_dispatcher.py`, named-pipe calls, or the existing `apply_group_template` implementation.
- Keep KMAI's frontend build-free and offline; load Three.js only from the configured local `step-compare` tree.
- XML is GB2312/GBK Kmsoft input; browser responses are UTF-8 and must not expose absolute paths or tracebacks.
- XML, STEP/STP, and template mappings use the extensionless XML sample name as the part identifier.
- The database is expected to be complete; missing resources are explicit data/configuration errors and do not alter similarity ranking.
- The workspace has no Git metadata, so implementation records verification commands but omits commit steps.

## Review Focus

- An uploaded XML filename containing Chinese characters must survive Base64 upload and resolve the same-named STEP.
- An expired or forged upload/candidate/model ID must return a stable public error without path leakage.
- A Top 3 candidate with a missing STEP or template must fail as a database error rather than silently changing rank.
- Repeated model requests must use the bounded GLB cache and never allow arbitrary filesystem reads.
- Template application failure must leave workflow step 1 incomplete and retryable.

---

### Task 1: Similar-part configuration and orchestration service

**Files:**
- Create: `KmAI-main/KmAI-main/KmMpsMcpServer/backend/similar_parts_service.py`
- Modify: `KmAI-main/KmAI-main/KmMpsMcpServer/backend/agent_config.py`
- Modify: `KmAI-main/KmAI-main/config.example.ini`
- Test: `KmAI-main/KmAI-main/KmMpsMcpServer/tests/test_similar_parts_service.py`

**Interfaces:**
- Produces: `SimilarPartsService(config, classifier=None, tessellator=None, clock=None)`.
- Produces: `upload_xml(filename: str, content: bytes) -> dict`, `query(upload_id: str, top_k: int = 3) -> dict`, `get_model(model_id: str) -> tuple[bytes, dict]`, and `prepare_template(upload_id: str, candidate_id: str, destination_dir: str) -> dict`.
- Produces: `SimilarPartsError(code: str, message: str, http_status: int)` with only public messages.

- [ ] Write tests for configuration defaults/relative-path resolution, valid GB2312 upload, invalid extension/XML, size limit, TTL expiry, Top 3 ordering, Chinese same-name STEP resolution, missing resource errors, forged IDs, bounded GLB caching, and safe template preparation.
- [ ] Run `python -m unittest KmMpsMcpServer.tests.test_similar_parts_service -v` and confirm the new tests fail because the service/config fields do not exist.
- [ ] Implement `[SimilarParts]` parsing for `enabled`, `part_classification_root`, `step_viewer_root`, `xml_library_dir`, `step_library_dir`, `template_map_file`, `upload_max_bytes`, `cache_ttl_seconds`, `model_cache_entries`, and `model_cache_bytes`; resolve relative paths against `config.ini`.
- [ ] Implement thread-safe, bounded in-memory upload/query/model registries; lazy dependency imports; resource resolution; sanitized public result objects; direct reuse of the current similarity and tessellation functions; and safe GB2312 template copying.
- [ ] Re-run the task test and confirm all cases pass.

### Task 2: Ordinary KMAI HTTP endpoints and local Three.js assets

**Files:**
- Modify: `KmAI-main/KmAI-main/KmMpsMcpServer/backend/http_api.py`
- Test: `KmAI-main/KmAI-main/KmMpsMcpServer/tests/test_similar_parts_http_api.py`

**Interfaces:**
- Consumes: Task 1 `SimilarPartsService` methods and `SimilarPartsError`.
- Produces: `POST /api/similar-parts/upload`, `POST /api/similar-parts/query`, `GET /api/similar-parts/models/{modelId}.glb`, `POST /api/similar-parts/apply-template`, and `/similar-assets/three/*`.

- [ ] Write handler-level tests with stub service/agent for successful upload/query/model/apply, request size limits, invalid Base64, stable error mapping, auth/origin preservation, no absolute paths, and rejection of `..` in local Three.js paths.
- [ ] Run the new HTTP test module and confirm failures for missing routes.
- [ ] Add a larger request-body allowance only for the XML upload route; decode `{filename, contentBase64}` and route all similar-part operations through the service.
- [ ] Implement the local Three.js static route rooted at `<step_viewer_root>/web/vendor`, using normalized-path and `commonpath` checks.
- [ ] Implement apply as: resolve candidate server-side, copy its template to `GROUP_TEMPLATE_SAVE_DIR`, then call existing `AGENT.tool("apply_group_template", {"template_name": <stem>}, timeout=120)`; never change MCP code.
- [ ] Run HTTP security, request-limit, and new similar-parts HTTP tests; confirm they pass.

### Task 3: KMAI comparison panel and workflow integration

**Files:**
- Create: `KmAI-main/KmAI-main/KmMpsMcpServer/frontend/assets/modules/similar_parts.js`
- Create: `KmAI-main/KmAI-main/KmMpsMcpServer/frontend/assets/css/similar_parts.css`
- Modify: `KmAI-main/KmAI-main/KmMpsMcpServer/frontend/assets/modules/workflow.js`
- Modify: `KmAI-main/KmAI-main/KmMpsMcpServer/frontend/assets/index.html`
- Modify: `KmAI-main/KmAI-main/KmMpsMcpServer/frontend/web_page.py`
- Test: `KmAI-main/KmAI-main/KmMpsMcpServer/tests/test_similar_parts_frontend.py`

**Interfaces:**
- Consumes: Task 2 HTTP responses and `/similar-assets/three/*` modules.
- Produces: `openSimilarPartsPanel({ autoContinue?: boolean })`, an accessible upload/query/candidate/apply panel, and workflow-step completion after successful application.

- [ ] Write frontend contract tests for the renamed step, disabled-before-upload query button, XML-only file input, Top 3 controls, two canvas viewports, model disposal, request race guards, selected-template application, retry behavior, and no external URLs.
- [ ] Run the frontend contract test and confirm it fails for missing assets/markup.
- [ ] Add a local Three.js import map and implement a focused industrial workbench panel: upload/status row, current/candidate split viewer, three rank cards plus previous/next controls, similarity/template metadata, fit-view, close, and apply button.
- [ ] Implement FileReader Base64 upload, explicit query click, GLB fetching/parsing, synchronized orbit controls, resource disposal, stale-request cancellation, candidate switching, and user-safe errors.
- [ ] Rename workflow step 1 to “查询相似零件”; replace both manual and run-all step-1 entrypoints with the comparison panel; on apply success call `markProcessWorkflowStepDone('select_group_template')` so step 2 remains unchanged.
- [ ] Add responsive CSS and include it through `web_page.py`; run the frontend and existing workflow contract tests and confirm they pass.

### Task 4: End-to-end verification and operator instructions

**Files:**
- Modify: `KmAI-main/KmAI-main/README.md`
- Modify: `docs/superpowers/specs/2026-09-29-similar-part-query-design.md` only if implementation rulings require a documented correction.

**Interfaces:**
- Consumes: Tasks 1-3 complete feature.
- Produces: exact configuration/start/use instructions and verified test evidence.

- [ ] Document the `[SimilarParts]` configuration, required offline Python packages, database naming convention, and user flow from XML upload through template application.
- [ ] Run `python -m compileall -q KmMpsMcpServer tests` from the KMAI project.
- [ ] Run the focused new backend/frontend tests plus existing workflow, HTTP security, request-limit, frontend-assets, and template-application contract tests.
- [ ] Run PartClassification similarity tests and step-compare conversion/frontend tests when their dependencies are available; record platform/dependency limitations precisely.
- [ ] Launch a local preview or open the implemented frontend artifact; visually inspect upload, split-view, candidate controls, disabled/error states, and responsive layout. Real STEP conversion and MCP application remain Windows acceptance items if unavailable on the current macOS host.
