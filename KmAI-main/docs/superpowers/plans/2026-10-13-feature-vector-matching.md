# Feature vector matching implementation plan

**Goal:** Replace KmAI's local XML similarity classifier with the remote 256-dimensional encoder and local cosine ranking.

**Approved design:** The user's approved conversation design is authoritative. Preserve model viewing, template mapping/editing/application, fixed current STEP selection and Win7 Lite GLB loading. Do not edit MCP functions or the independent PartClassification project.

**Architecture:** A standard-library HTTP client validates remote feature responses. A SQLite cache stores vectors by XML SHA256 and an encoder namespace derived from endpoint plus operator-supplied model revision. An incremental command-line index builder extracts library vectors. Queries scan current library files and require matching cached vectors, so deleted/changed files cannot silently use stale data. An identical content hash identifies self regardless of filename. Similarity is clamped cosine in [0,1], matching the existing frontend contract.

**Constraints:** Python 3.8 compatible; no new required packages; real service address only in local config.ini; no automatic old-algorithm fallback. Top N must be a positive integer (bounded at 1000 to the upstream batch scale); fewer library items return available items. Unknown model revision must be documented as a manual deployment label, not a verified model weights version.

## Tasks

- [x] Add backend/feature_vector_matching.py and tests: actual multipart HTTP contract via local HTTP fixture, finite/nonzero 256 dimensions, invalid response/error mapping, persistent cache, hash and revision invalidation, content self-match, incremental build failures and deleted files.
- [x] Replace production classifier import and XML validation dependency in similar_parts_service.py. Keep candidate/template/model response contract. Extend configuration and positive Top N, update corresponding tests and neutral frontend query/category text.
- [x] Add build_feature_index.py CLI and usage guide, enable the real endpoint in local config, build the existing library, validate query/model/template HTTP paths and Python 3.8 syntax. Run required test discovery and report platform/unrelated failures accurately.

## Review focus

Chinese GB2312 and UTF-8 XML; identical names with different XML; index files missing or externally corrupted; upstream errors must not expose internal paths; model/template resources must remain bounded to configured roots. No classification labels are inferred from feature vectors.

## Progress

Initial inspection complete. Win7 release scripts mentioned in previous context are absent from the current workspace; preserve Lite code in the active backend and document missing package separately.

Tasks 1 and 2 implemented. RED: feature tests failed with the absent module; service/config tests failed with absent matcher injection/config fields and the old Top 5 limit. GREEN: 44 focused tests passed, exercising a real local multipart HTTP fixture, SQLite persistence and actual cosine ranking through the service.

Ruling: use the existing non-Git workspace and retain this plan as the ledger — Git-backed skill bookkeeping cannot run here. No changes to MCP tools or independent projects are required.

Ruling: use the single-file extraction API for incremental indexing — the current library has 20 XML files; per-item transactions avoid NPZ dependencies and permit resuming partial failures. The result is still remote learned-vector matching, not the previous XML algorithm.

Task 3 runtime evidence: all 20 library XML files indexed successfully; a second CLI run reused all 20 with zero requests/extractions. The fixed current XML query returns five candidates; every current/candidate GLB request returned HTTP 200 with glTF headers and distinct geometry, and every candidate template is readable via its private mapping. The ordinary HTTP health probe now tolerates non-Windows pipe stubs; six runtime diagnostic tests pass after an observed RED test for the absent availability method. No MCP implementation changed.

Final review: external reviewer attempts were unavailable (upstream model service errors). Author performed the boundary review; malformed/truncated response JSON remains covered by stable error handling. Desktop browser shows both models; WebGL pixel assertions confirm rendered model pixels in both viewports. No algorithm accuracy benchmark is claimed.

Ruling: fix the ordinary HTTP health probe fallback for non-Windows development — its crash prevented the local browser from reporting service health. Windows pipe detection remains called when available; no pipe or tool implementation was changed.

Ruling: correct camera fitting to account for the narrower of the horizontal and vertical field of view — mobile verification exposed the pre-existing fixed-distance crop. The new bounding-sphere distance preserves the shared camera, orientation and scale modes, with a focused RED/GREEN regression test.

Final verification: 59 related tests pass; full project discovery 72 tests (3 unrelated Windows-path failures, 2 skips); full backend discovery 183 tests (4 absent-Win7-package issues, 1 existing chat placeholder failure). compileall, frontend Node checks and five-file Python 3.8 syntax checks pass. Real Top 1000 returns 20 and three renamed real inputs match themselves. Desktop/mobile screenshots and canvas pixel checks pass; dragging changes both viewports, and cycling candidates then opening the editor again works. See [verification record](../../feature-vector-verification-2026-10-13.md) for the complete result and limitations.
