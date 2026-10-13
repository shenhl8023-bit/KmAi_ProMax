$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -B -m unittest discover -s tests -v
$rootTestsExitCode = $LASTEXITCODE
$serverRoot = Join-Path $PSScriptRoot "KmMpsMcpServer"
Push-Location -LiteralPath $serverRoot
try {
    python -B -m unittest discover -s tests -v
    $serverTestsExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($rootTestsExitCode -ne 0) {
    exit $rootTestsExitCode
}
exit $serverTestsExitCode
