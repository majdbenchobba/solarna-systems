param(
    [string]$RuntimeDirectory = "",
    [string]$SecretsDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
if (-not $RuntimeDirectory) {
    $localApplicationData = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::LocalApplicationData)
    if (-not $localApplicationData) {
        exit 1
    }
    $RuntimeDirectory = Join-Path $localApplicationData "SolarnaPV"
}
$logDirectory = Join-Path $runtimeDirectory "logs"
$statusLog = Join-Path $logDirectory "launcher-status.log"
$errorLog = Join-Path $logDirectory "launcher-error.log"
if (-not $SecretsDirectory) {
    $SecretsDirectory = Join-Path $projectDirectory "secrets"
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
[System.IO.File]::WriteAllText(
    $statusLog,
    (
        "Starting " + [DateTime]::UtcNow.ToString("o") +
        [Environment]::NewLine +
        "User: " + [Environment]::UserDomainName + "\" +
        [Environment]::UserName +
        [Environment]::NewLine +
        "Runtime: " + $RuntimeDirectory +
        [Environment]::NewLine +
        "Runtime present: " +
        (Test-Path -LiteralPath $RuntimeDirectory -PathType Container) +
        [Environment]::NewLine +
        "Supabase files present: " +
        ((Test-Path -LiteralPath (
            Join-Path $SecretsDirectory "supabase-url.txt") -PathType Leaf) -and
         (Test-Path -LiteralPath (
            Join-Path $SecretsDirectory "supabase-publishable-key.txt") -PathType Leaf) -and
         (Test-Path -LiteralPath (
            Join-Path $SecretsDirectory "authorized-emails.txt") -PathType Leaf)) +
        [Environment]::NewLine +
        "Tunnel token present: " +
        (Test-Path -LiteralPath (
            Join-Path $SecretsDirectory "cloudflared-token.txt") -PathType Leaf)
    ),
    [System.Text.UTF8Encoding]::new($false))

try {
    & (Join-Path $PSScriptRoot "start-solarna-production.ps1") `
        -RuntimeDirectory $RuntimeDirectory `
        -SecretsDirectory $SecretsDirectory
} catch {
    $details = (
        [DateTime]::UtcNow.ToString("o") + [Environment]::NewLine +
        $_.Exception.ToString() + [Environment]::NewLine)
    [System.IO.File]::AppendAllText(
        $errorLog, $details, [System.Text.UTF8Encoding]::new($false))
    exit 1
}
