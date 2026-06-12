param(
    [switch]$VerifyOnly,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ManifestPath = Join-Path $RepoRoot "build_assets_manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "build_assets_manifest.json was not found: $ManifestPath"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
# Allow TLS 1.2 and, when the runtime supports it, TLS 1.3 (older .NET
# Framework builds do not define the Tls13 enum value).
$SecurityProtocols = [Net.SecurityProtocolType]::Tls12
try {
    $SecurityProtocols = $SecurityProtocols -bor [Net.SecurityProtocolType]::Tls13
}
catch {
}
[Net.ServicePointManager]::SecurityProtocol = $SecurityProtocols

function Test-AssetHash([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $ActualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    return $ActualHash -eq $ExpectedHash.ToUpperInvariant()
}

foreach ($Asset in $Manifest.assets) {
    $Target = Join-Path $RepoRoot $Asset.file_name
    $ExpectedHash = [string]$Asset.sha256
    $ExpectedSize = [int64]$Asset.size_bytes
    $Url = [string]$Asset.url

    if ((Test-Path -LiteralPath $Target -PathType Leaf) -and -not $Force) {
        $Item = Get-Item -LiteralPath $Target
        if ($Item.Length -eq $ExpectedSize -and (Test-AssetHash $Target $ExpectedHash)) {
            Write-Host "Verified existing asset: $($Asset.file_name)"
            continue
        }
        if ($VerifyOnly) {
            throw "Asset exists but failed size/hash validation: $($Asset.file_name)"
        }
        Write-Warning "Existing asset failed validation and will be replaced: $($Asset.file_name)"
    }
    elseif ($VerifyOnly) {
        throw "Missing required build asset: $($Asset.file_name)"
    }

    $TempTarget = "$Target.download"
    if (Test-Path -LiteralPath $TempTarget) {
        Remove-Item -LiteralPath $TempTarget -Force
    }
    Write-Host "Downloading $Url"
    # Suppress the per-chunk progress bar: under Windows PowerShell 5.1 it
    # slows large downloads by an order of magnitude. -UseBasicParsing keeps
    # 5.1 working without the IE engine (it is a harmless no-op on PowerShell 7).
    $PreviousProgressPreference = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $TempTarget -UseBasicParsing
    }
    finally {
        $ProgressPreference = $PreviousProgressPreference
    }
    $Item = Get-Item -LiteralPath $TempTarget
    if ($Item.Length -ne $ExpectedSize) {
        Remove-Item -LiteralPath $TempTarget -Force
        throw "Downloaded asset size mismatch for $($Asset.file_name): $($Item.Length) != $ExpectedSize"
    }
    if (-not (Test-AssetHash $TempTarget $ExpectedHash)) {
        Remove-Item -LiteralPath $TempTarget -Force
        throw "Downloaded asset hash mismatch for $($Asset.file_name)"
    }
    Move-Item -LiteralPath $TempTarget -Destination $Target -Force
    Write-Host "Downloaded and verified: $($Asset.file_name)"
}