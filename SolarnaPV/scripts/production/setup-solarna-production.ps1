param(
    [Parameter(Mandatory)]
    [string]$SupabaseUrl,
    [Parameter(Mandatory)]
    [string]$SupabasePublishableKey,
    [string]$AuthorizedEmails = "majd@solarnasystems.com",
    [string]$TunnelTokenSource = "",
    [string]$SecretsDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
if (-not $SecretsDirectory) {
    $SecretsDirectory = Join-Path $projectDirectory "secrets"
}
if (-not $TunnelTokenSource) {
    $localApplicationData = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::LocalApplicationData)
    $TunnelTokenSource = Join-Path (
        Join-Path $localApplicationData "SolarnaPV") "cloudflared-token.txt"
}

$parsedSupabaseUrl = [Uri]$SupabaseUrl
if ($parsedSupabaseUrl.Scheme -ne "https" -or
    -not $parsedSupabaseUrl.Host -or
    $parsedSupabaseUrl.AbsolutePath -ne "/") {
    throw "SupabaseUrl must be an HTTPS origin."
}
if (-not $SupabasePublishableKey.StartsWith("sb_publishable_") -or
    $SupabasePublishableKey.Length -lt 24) {
    throw "SupabasePublishableKey is invalid."
}
if (-not $AuthorizedEmails.Trim()) {
    throw "AuthorizedEmails must contain at least one email address."
}
if (-not (Test-Path -LiteralPath $TunnelTokenSource -PathType Leaf)) {
    throw "The Cloudflare tunnel token source was not found."
}

New-Item -ItemType Directory -Force -Path $SecretsDirectory | Out-Null
Copy-Item -LiteralPath $TunnelTokenSource -Destination (
    Join-Path $SecretsDirectory "cloudflared-token.txt") -Force
[System.IO.File]::WriteAllText(
    (Join-Path $SecretsDirectory "supabase-url.txt"),
    $SupabaseUrl.TrimEnd("/"),
    [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText(
    (Join-Path $SecretsDirectory "supabase-publishable-key.txt"),
    $SupabasePublishableKey,
    [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText(
    (Join-Path $SecretsDirectory "authorized-emails.txt"),
    $AuthorizedEmails,
    [System.Text.UTF8Encoding]::new($false))

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $SecretsDirectory /inheritance:r `
    /grant:r "${identity}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not restrict the production secret directory permissions."
}

Write-Output "Solarna Supabase and tunnel configuration is ready."
