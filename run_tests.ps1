$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"
$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw "需要 py -3 或 python 执行测试"
}
if ($pythonCommand.Name -eq "py.exe" -or $pythonCommand.Name -eq "py") {
    & $pythonCommand.Source -3 -B -m unittest discover -s tests -v
} else {
    & $pythonCommand.Source -B -m unittest discover -s tests -v
}
$rootTestsExitCode = $LASTEXITCODE
$serverRoot = Join-Path $PSScriptRoot "KmMpsMcpServer"
$existingPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = "$PSScriptRoot;$serverRoot"
} else {
    $env:PYTHONPATH = "$PSScriptRoot;$serverRoot;$existingPythonPath"
}
Push-Location -LiteralPath $serverRoot
try {
    if ($pythonCommand.Name -eq "py.exe" -or $pythonCommand.Name -eq "py") {
        & $pythonCommand.Source -3 -B -m unittest discover -s tests -v
    } else {
        & $pythonCommand.Source -B -m unittest discover -s tests -v
    }
    $serverTestsExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($rootTestsExitCode -ne 0) {
    exit $rootTestsExitCode
}
exit $serverTestsExitCode
