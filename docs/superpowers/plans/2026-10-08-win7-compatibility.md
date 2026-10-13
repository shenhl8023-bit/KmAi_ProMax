# Win7 SP1 x64 Compatibility Package Implementation Plan

> **For agentic workers:** This plan is implemented in the current workspace.

**Goal:** Ship a parallel Win7 SP1 x64 Lite package that uses prebuilt GLB
models while preserving the current KMAI and MCP behavior.

**Architecture:** Add a guarded GLB adapter to `SimilarPartsService`, parse two
new `[SimilarParts]` settings, and assemble a clean package under
`win7-compat/`. The package launcher uses bundled Python and Python socket
probes; STEP conversion is performed on the build machine by
`build_glb_cache.py`.

**Tech Stack:** Python 3.8 x64 runtime contract, existing Python HTTP agent,
PowerShell build script, batch launchers, JSON/GLB cache.

## Tasks

- [x] Add `win7_lite_mode` and `prebuilt_model_dir` configuration with relative
  path resolution.
- [x] Add prebuilt GLB loading, optional metadata sidecars, bounded caching,
  validation, and explicit missing-file errors.
- [x] Add Win7 package manifest, safe config template, requirements note,
  README, launcher, start/stop scripts, and build script.
- [x] Add build-machine GLB cache generation utility.
- [x] Add regression tests for Lite mode, fixed `stepModel` fallback, config
  loading, package exclusions, and launcher compatibility.
- [ ] Validate the assembled package in a real Win7 SP1 x64 VM with 3DMPS.
