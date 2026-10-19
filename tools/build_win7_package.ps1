param(
    [Parameter(Mandatory = $true)][string]$PythonRuntime,
    [Parameter(Mandatory = $true)][string]$NodeRuntime,
    [Parameter(Mandatory = $true)][string]$CefRoot,
    [Parameter(Mandatory = $true)][string]$SimilarPartsDataRoot,
    [string]$ModelsRoot = "",
    [string]$Win7Kb = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path (Split-Path $sourceRoot -Parent) "KmAI-win7-x64-package"
}
$builderArgs = @(
    "--source-root", $sourceRoot,
    "--output", $Output,
    "--python-runtime", $PythonRuntime,
    "--node-runtime", $NodeRuntime,
    "--cef-root", $CefRoot,
    "--similar-parts-data-root", $SimilarPartsDataRoot
)
if (-not [string]::IsNullOrWhiteSpace($ModelsRoot)) {
    $builderArgs += @("--models-root", $ModelsRoot)
}
if (-not [string]::IsNullOrWhiteSpace($Win7Kb)) {
    $builderArgs += @("--win7-kb", $Win7Kb)
}
& py -3 (Join-Path $PSScriptRoot "build_win7_package.py") @builderArgs
exit $LASTEXITCODE
