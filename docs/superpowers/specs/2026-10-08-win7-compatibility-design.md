# KmAI Win7 SP1 x64 Lite Compatibility Package

Date: 2026-10-08

## Goal

Provide a parallel Windows 7 SP1 x64 package for the current KMAI workflow.
The first package targets CPython 3.8 x64 and the x64 3DMPS build. An x86
variant is intentionally deferred until the installed 3DMPS bitness is
confirmed.

## Design

- Keep `KmAI-main` MCP definitions, dispatch, named-pipe calls, and existing
  template application unchanged.
- Add an opt-in `SimilarParts.win7_lite_mode` switch. When enabled,
  `SimilarPartsService.get_model()` reads a same-stem prebuilt GLB from
  `prebuilt_model_dir`; the existing STEP-to-GLB path remains the default.
- Preserve the fixed current-part mapping. For a fixed `AIBasicInfo.xml` and
  `stepModel.stp`, current model lookup tries the XML stem first and the STEP
  stem second.
- Build the package from source plus local Three.js assets, PartClassification
  source, a portable Python 3.8 x64 runtime, data directories, and prebuilt
  GLBs. Do not package `config.ini`, credentials, logs, caches, or bytecode.
- Use a Python launcher and `taskkill` for process lifecycle so the Win7
  scripts do not depend on newer PowerShell networking/process cmdlets.

## Acceptance

The package must pass local service, XML similarity, Top 5 selection, GLB
display, template editing/application, and existing workflow checks. Final
acceptance requires a Win7 SP1 x64 VM with the matching 3DMPS installation and
named-pipe service. STEP conversion remains a build-machine concern.
