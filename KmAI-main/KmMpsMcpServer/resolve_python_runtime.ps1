param(
    [int]$MinMajor = 3,
    [int]$MinMinor = 10
)

$ErrorActionPreference = "SilentlyContinue"

function Test-PythonCandidate {
    param(
        [string]$Exe,
        [string[]]$ExtraArgs = @()
    )

    if ([string]::IsNullOrWhiteSpace($Exe)) {
        return $null
    }
    if (($Exe -like "*\*" -or $Exe -like "*/*") -and -not (Test-Path -LiteralPath $Exe)) {
        return $null
    }

    $code = "import sys; print(sys.executable if sys.version_info[:2] >= ($MinMajor, $MinMinor) else '')"
    try {
        $output = & $Exe @ExtraArgs -c $code 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    foreach ($line in @($output)) {
        $value = [string]$line
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
    }
    return $null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyInferenceDir = Join-Path $scriptDir "..\..\PyInference"

$candidates = @()
if ($env:KMAI_PYTHON_EXE) {
    $candidates += ,@($env:KMAI_PYTHON_EXE)
}
if ($env:KMAI_SKILL_PYTHON) {
    $candidates += ,@($env:KMAI_SKILL_PYTHON)
}
$candidates += ,@(Join-Path $pyInferenceDir "Python3.12_win32\python.exe")
$candidates += ,@(Join-Path $pyInferenceDir "Python3.11_win32\python.exe")
$candidates += ,@(Join-Path $pyInferenceDir "Python3.10_win32\python.exe")
$candidates += ,@("py", "-3.12")
$candidates += ,@("py", "-3.11")
$candidates += ,@("py", "-3.10")
$candidates += ,@("py", "-3")
$candidates += ,@("python")

foreach ($candidate in $candidates) {
    $exe = [string]$candidate[0]
    $extraArgs = @()
    if ($candidate.Count -gt 1) {
        $extraArgs = @($candidate[1..($candidate.Count - 1)])
    }
    $resolved = Test-PythonCandidate -Exe $exe -ExtraArgs $extraArgs
    if ($resolved) {
        Write-Output $resolved
        exit 0
    }
}

exit 1
