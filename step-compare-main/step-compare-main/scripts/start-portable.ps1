[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Python,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$Port
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$healthUrl = "http://127.0.0.1:$Port/api/health"
$appUrl = "http://127.0.0.1:$Port/"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Embedded Python runtime is missing: $Python"
}

try {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is already in use. Run start.bat with a different port."
    }

    $process = Start-Process -FilePath $Python -ArgumentList @("-m", "step_viewer", "--port", $Port, "--no-browser") -WorkingDirectory $root -NoNewWindow -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
            if ($health.status -eq "ok") {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }

    if (-not $ready) {
        throw "STEP Compare did not become ready within 20 seconds."
    }

    Start-Process $appUrl
    Write-Host "STEP Compare is running at $appUrl"
    Write-Host "Press Ctrl+C or close this window to stop the local service."
    Wait-Process -Id $process.Id
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}
