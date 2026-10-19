param(
    [Parameter(Mandatory = $true)][string]$PlaintextSource,
    [Parameter(Mandatory = $true)][string]$ProjectResources,
    [Parameter(Mandatory = $true)][string]$ToolsRoot,
    [Parameter(Mandatory = $true)][string]$QCefRoot,
    [Parameter(Mandatory = $true)][string]$UcrtRoot,
    [Parameter(Mandatory = $true)][string]$BuildRoot,
    [Parameter(Mandatory = $true)][string]$RuntimeOutput
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$plainRoot = (Resolve-Path -LiteralPath $PlaintextSource).Path
$resourceRoot = (Resolve-Path -LiteralPath $ProjectResources).Path
$toolRoot = (Resolve-Path -LiteralPath $ToolsRoot).Path
$qcefSdk = (Resolve-Path -LiteralPath $QCefRoot).Path
$ucrtDir = (Resolve-Path -LiteralPath $UcrtRoot).Path
$buildDir = [IO.Path]::GetFullPath($BuildRoot)
$runtimeDir = [IO.Path]::GetFullPath($RuntimeOutput)
foreach ($destination in @($buildDir, $runtimeDir)) {
    if (Test-Path -LiteralPath $destination) {
        throw "Output already exists: $destination"
    }
    foreach ($inputPath in @($repoRoot, $plainRoot, $resourceRoot, $toolRoot, $qcefSdk, $ucrtDir)) {
        if ($destination.Equals($inputPath, [StringComparison]::OrdinalIgnoreCase) -or
            $destination.StartsWith($inputPath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Build and runtime outputs must be outside all source/SDK directories.'
        }
    }
}
if ($buildDir.StartsWith($runtimeDir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $runtimeDir.StartsWith($buildDir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $buildDir.Equals($runtimeDir, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build and runtime outputs must be separate directories.'
}

$vcRoot = Join-Path $toolRoot 'msvc\VC\Tools\MSVC\14.29.30133'
$sdkRoot = Join-Path $toolRoot 'msvc\Windows Kits\10'
$sdkVersion = '10.0.19041.0'
$qtRoot = Join-Path $toolRoot 'Qt\5.15.2\msvc2019_64'
$vcBin = Join-Path $vcRoot 'bin\Hostx64\x64'
foreach ($required in @("$qtRoot\bin\qmake.exe", "$vcBin\nmake.exe", "$qcefSdk\lib\QCefView.lib", "$ucrtDir\ucrtbase.dll")) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing build input: $required" }
}
$env:QTDIR = $qtRoot
$env:KMAI_QCEF_ROOT = $qcefSdk
$env:VSCMD_ARG_HOST_ARCH = 'x64'
$env:VSCMD_ARG_TGT_ARCH = 'x64'
$env:VCToolsVersion = '14.29.30133'
$env:VCToolsInstallDir = "$vcRoot\"
$env:WindowsSDKVersion = "$sdkVersion\"
$env:WindowsSdkDir = "$sdkRoot\"
$env:PATH = "$vcBin;$sdkRoot\bin\$sdkVersion\x64;$qtRoot\bin;$env:PATH"
$env:INCLUDE = "$vcRoot\include;$sdkRoot\Include\$sdkVersion\ucrt;$sdkRoot\Include\$sdkVersion\shared;$sdkRoot\Include\$sdkVersion\um;$sdkRoot\Include\$sdkVersion\winrt;$sdkRoot\Include\$sdkVersion\cppwinrt"
$env:LIB = "$vcRoot\lib\x64;$sdkRoot\Lib\$sdkVersion\ucrt\x64;$sdkRoot\Lib\$sdkVersion\um\x64"

$sourceDir = Join-Path $buildDir 'source'
$objectDir = Join-Path $buildDir 'build'
New-Item -ItemType Directory -Path $sourceDir, $objectDir | Out-Null
$encoding = [Text.UTF8Encoding]::new($false)
$sourceFiles = Get-ChildItem -LiteralPath $plainRoot -File | Where-Object { $_.Extension -in '.cpp', '.h' }
if ($sourceFiles.Count -ne 18) { throw 'Expected the 18 authorized plaintext C++ source files.' }
foreach ($sourceFile in $sourceFiles) {
    $raw = [IO.File]::ReadAllBytes($sourceFile.FullName)
    $text = $encoding.GetString($raw)
    if ($text.Contains('E-SafeNet') -or $text.Contains('LOCK') -or ($raw -contains 0)) {
        throw "Source is not plaintext: $($sourceFile.Name)"
    }
    # Omit obsolete private-network examples from the portable source copy.
    $text = [regex]::Replace($text,
        '(?m)^([ \t]*)//[^\r\n]*https?://(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)[^\r\n]*\r?$',
        '${1}// Legacy remote UI example omitted.')
    if ($sourceFile.Name -eq 'KmAiChatManager.cpp') {
        $pattern = '(?m)^    webUrlRequest = "https?://[^"\r\n]+";\r?$'
        if ([regex]::Matches($text, $pattern).Count -ne 1) { throw 'Unexpected legacy URL assignment count.' }
        $text = [regex]::Replace($text, $pattern, '    webUrlRequest = m_sWebUrl;')
    }
    [IO.File]::WriteAllText((Join-Path $sourceDir $sourceFile.Name), $text, $encoding)
}
Copy-Item -LiteralPath "$resourceRoot\KmAiChatCef.pro", "$resourceRoot\KmAiChatCef.qrc" -Destination $sourceDir
New-Item -ItemType Directory -Path "$sourceDir\resource" | Out-Null
Copy-Item -LiteralPath "$resourceRoot\resource\logo.png" -Destination "$sourceDir\resource\logo.png"
$patch = Join-Path $repoRoot 'deploy\win7-compat\kmai-client-cef109.patch'
Push-Location $sourceDir
try {
    & git apply --check --ignore-space-change $patch
    if ($LASTEXITCODE -ne 0) { throw 'Client adaptation patch does not match the supplied source.' }
    & git apply --ignore-space-change $patch
    if ($LASTEXITCODE -ne 0) { throw 'Client adaptation patch failed.' }
} finally { Pop-Location }
Push-Location $objectDir
try {
    & "$qtRoot\bin\qmake.exe" "$sourceDir\KmAiChatCef.pro" -spec win32-msvc 'CONFIG+=release' 'CONFIG-=debug_and_release'
    if ($LASTEXITCODE -ne 0) { throw 'qmake failed.' }
    & "$vcBin\nmake.exe" /NOLOGO
    if ($LASTEXITCODE -ne 0) { throw 'Client compilation failed.' }
} finally { Pop-Location }
$executable = Join-Path $objectDir 'KmAiChatCef.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw 'Client executable was not produced.' }
New-Item -ItemType Directory -Path $runtimeDir | Out-Null
Copy-Item -LiteralPath $executable -Destination $runtimeDir
foreach ($name in @('QCefView.dll', 'CefViewWing.exe', 'CefViewWing.exe.manifest',
    'libcef.dll', 'chrome_elf.dll', 'd3dcompiler_47.dll', 'icudtl.dat', 'libEGL.dll',
    'libGLESv2.dll', 'snapshot_blob.bin', 'v8_context_snapshot.bin',
    'vk_swiftshader.dll', 'vk_swiftshader_icd.json', 'vulkan-1.dll')) {
    Copy-Item -LiteralPath "$qcefSdk\bin\$name" -Destination $runtimeDir
}
Copy-Item -LiteralPath "$qcefSdk\bin\resources" -Destination "$runtimeDir\resources" -Recurse
& "$qtRoot\bin\windeployqt.exe" --release --no-translations --no-compiler-runtime `
    --no-opengl-sw --no-system-d3d-compiler --dir $runtimeDir "$runtimeDir\KmAiChatCef.exe"
if ($LASTEXITCODE -ne 0) { throw 'Qt deployment failed.' }
foreach ($name in @('msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    Copy-Item -LiteralPath "$vcBin\$name" -Destination $runtimeDir
}
Get-ChildItem -LiteralPath $ucrtDir -Filter '*.dll' -File | Copy-Item -Destination $runtimeDir
$cefVersion = '109.1.18+gf1c41e4+chromium-109.0.5414.120'
$manifest = [ordered]@{
    version = $cefVersion; chromium_version = '109.0.5414.120'; qt_version = '5.15.2'
    client_version = 'KmAiChatCef-win7-1'; client_abi = $cefVersion
    architecture = 'x64'; win7_supported = $true; win7_vm_validated = $false
    vc_runtime_version = '14.29.30159.0'
    ucrt_version = (Get-Item -LiteralPath "$ucrtDir\ucrtbase.dll").VersionInfo.FileVersion
    client_files = [ordered]@{
        main_executable = 'KmAiChatCef.exe'; wrapper_library = 'QCefView.dll'
        subprocess_executable = 'CefViewWing.exe'
    }
    source_patch_sha256 = (Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText("$runtimeDir\cef.manifest.json", ($manifest | ConvertTo-Json -Depth 5) + "`n", $encoding)
Write-Output "Built client runtime: $runtimeDir"
