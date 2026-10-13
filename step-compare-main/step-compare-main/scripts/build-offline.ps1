[CmdletBinding()]
param(
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$config = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "offline-package.json") | ConvertFrom-Json
$requirements = Join-Path $root "requirements.txt"
$buildRoot = Join-Path $root ".offline-build"
$downloads = Join-Path $buildRoot "downloads"
$wheelhouse = Join-Path $buildRoot "wheelhouse"
$stageRoot = Join-Path $buildRoot "stage"
$packageRoot = Join-Path $stageRoot "STEP-Compare"
$runtimeRoot = Join-Path $packageRoot "runtime\python"
$outputRoot = Join-Path $root $OutputDirectory
$pythonArchive = Join-Path $downloads $config.python.archive
$zipName = "STEP-Compare-win-x64-$($config.version).zip"
$zipPath = Join-Path $outputRoot $zipName

function Assert-LastExitCode([string]$Action) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "The offline package can only be built on 64-bit Windows."
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Runtime lock file is missing: $requirements"
}
if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw "The Windows Python launcher (py.exe) is required on the build machine."
}

New-Item -ItemType Directory -Force -Path $downloads, $wheelhouse, $outputRoot | Out-Null
if (-not (Test-Path -LiteralPath $pythonArchive -PathType Leaf)) {
    & curl.exe -fL --retry 3 --retry-delay 2 -o $pythonArchive $config.python.url
    Assert-LastExitCode "Downloading embedded Python"
}
if ((Get-Sha256 $pythonArchive) -ne $config.python.sha256) {
    throw "Embedded Python SHA-256 does not match scripts/offline-package.json."
}

& py.exe -3 -m pip download --require-hashes --no-index --find-links $wheelhouse --only-binary=:all: --platform win_amd64 --implementation cp --python-version 3.12 --abi cp312 --dest $wheelhouse -r $requirements
if ($LASTEXITCODE -ne 0) {
    & py.exe -3 -m pip download --require-hashes --only-binary=:all: --platform win_amd64 --implementation cp --python-version 3.12 --abi cp312 --dest $wheelhouse -r $requirements
    Assert-LastExitCode "Downloading locked wheels"
}

Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
Expand-Archive -LiteralPath $pythonArchive -DestinationPath $runtimeRoot -Force
$pth = Get-ChildItem -LiteralPath $runtimeRoot -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) {
    throw "Embedded Python path configuration was not found."
}
Set-Content -LiteralPath $pth.FullName -Encoding ascii -NoNewline -Value "python312.zip`r`n.`r`n..\..`r`nsite-packages`r`nimport site`r`n"

$sitePackages = Join-Path $runtimeRoot "site-packages"
& py.exe -3 -m pip install --require-hashes --no-index --find-links $wheelhouse --only-binary=:all: --platform win_amd64 --implementation cp --python-version 3.12 --abi cp312 --target $sitePackages --no-compile -r $requirements
Assert-LastExitCode "Installing locked wheels into embedded Python"

$applicationPackage = Join-Path $packageRoot "step_viewer"
New-Item -ItemType Directory -Force -Path $applicationPackage | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root "step_viewer") -Filter "*.py" -File | Copy-Item -Destination $applicationPackage
Copy-Item -LiteralPath (Join-Path $root "web") -Destination $packageRoot -Recurse
Copy-Item -LiteralPath (Join-Path $root "README.md"), (Join-Path $root "S-DEMO-02.stp"), (Join-Path $root "start.bat") -Destination $packageRoot
New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "start-portable.ps1"), (Join-Path $PSScriptRoot "offline-package.json") -Destination (Join-Path $packageRoot "scripts")

$wheelManifest = Get-ChildItem -LiteralPath $wheelhouse -File | Sort-Object Name | ForEach-Object {
    [ordered]@{
        file = $_.Name
        source = "https://files.pythonhosted.org/"
        sha256 = Get-Sha256 $_.FullName
    }
}
$buildManifest = [ordered]@{
    product = $config.product
    version = $config.version
    target = $config.target
    builtAtUtc = [DateTime]::UtcNow.ToString("o")
    wheelIndex = "https://pypi.org/simple/"
    python = [ordered]@{
        version = $config.python.version
        source = $config.python.url
        archive = $config.python.archive
        sha256 = $config.python.sha256
    }
    wheels = @($wheelManifest)
}
$buildManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $packageRoot "BUILD-MANIFEST.json") -Encoding utf8

Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
"$(Get-Sha256 $zipPath) *$zipName" | Set-Content -LiteralPath "$zipPath.sha256" -Encoding ascii
Write-Host "Created $zipPath"
