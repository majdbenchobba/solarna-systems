param(
    [string]$DestinationPath = "outputs\deliverables\Solarna-server.zip"
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$deliverableDirectory = Join-Path $projectDirectory "outputs\deliverables"

if (-not [IO.Path]::IsPathRooted($DestinationPath)) {
    $DestinationPath = Join-Path $projectDirectory $DestinationPath
}
$DestinationPath = [IO.Path]::GetFullPath($DestinationPath)
New-Item -ItemType Directory -Force -Path (
    Split-Path -Parent $DestinationPath) | Out-Null

$stageDirectory = Join-Path $deliverableDirectory (
    ".server-package-" + [guid]::NewGuid().ToString("N"))
$resolvedDeliverables = [IO.Path]::GetFullPath(
    $deliverableDirectory).TrimEnd('\')
$resolvedStage = [IO.Path]::GetFullPath($stageDirectory)
if (-not $resolvedStage.StartsWith(
        $resolvedDeliverables + '\',
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Invalid server package staging path."
}

$files = @(
    ".dockerignore",
    ".env.tunnel.example",
    "compose.tunnel.yaml",
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    "scripts\build\package-server-release.ps1",
    "scripts\production\run-solarna-production.ps1",
    "scripts\production\setup-solarna-production.ps1",
    "scripts\production\start-solarna-production.ps1",
    "outputs\sfax.json",
    "outputs\deliverables\Solarna-android.apk",
    "outputs\deliverables\Solarna-iOS-project.zip",
    "outputs\deliverables\Solarna-Android-Store-Submission.md",
    "outputs\deliverables\Solarna-iOS-App-Store-Submission.md"
)
$directories = @(
    "deploy\aws",
    "deploy\cloudflare-tunnel",
    "solarna"
)

try {
    New-Item -ItemType Directory -Force -Path $stageDirectory | Out-Null
    foreach ($relativePath in $files) {
        $source = Join-Path $projectDirectory $relativePath
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Required server release file is missing: $relativePath"
        }
        $target = Join-Path $stageDirectory $relativePath
        New-Item -ItemType Directory -Force -Path (
            Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
    foreach ($relativePath in $directories) {
        $source = Join-Path $projectDirectory $relativePath
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Required server release directory is missing: $relativePath"
        }
        $targetParent = Split-Path -Parent (
            Join-Path $stageDirectory $relativePath)
        New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        Copy-Item -LiteralPath $source -Destination $targetParent `
            -Recurse -Force
    }

    $stagePrefix = $resolvedStage.TrimEnd('\') + '\'
    $generatedDirectories = Get-ChildItem -LiteralPath $resolvedStage `
        -Directory -Recurse -Filter "__pycache__"
    foreach ($directory in $generatedDirectories) {
        $candidate = [IO.Path]::GetFullPath($directory.FullName)
        if (-not $candidate.StartsWith(
                $stagePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Invalid generated directory path."
        }
        Remove-Item -LiteralPath $candidate -Recurse -Force
    }
    $generatedFiles = Get-ChildItem -LiteralPath $resolvedStage `
        -File -Recurse | Where-Object {
            $_.Extension -in @(".pyc", ".pyo")
        }
    foreach ($file in $generatedFiles) {
        $candidate = [IO.Path]::GetFullPath($file.FullName)
        if (-not $candidate.StartsWith(
                $stagePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Invalid generated file path."
        }
        Remove-Item -LiteralPath $candidate -Force
    }

    Compress-Archive -Path (Join-Path $stageDirectory "*") `
        -DestinationPath $DestinationPath -CompressionLevel Optimal -Force
    if (-not (Test-Path -LiteralPath $DestinationPath -PathType Leaf)) {
        throw "Server release package was not created."
    }
} finally {
    if (Test-Path -LiteralPath $resolvedStage -PathType Container) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}

Write-Output $DestinationPath
