param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [string]$Domain = "pv.solarnasystems.com",
    [string]$RuntimeDirectory = "",
    [string]$SecretsDirectory = "",
    [string]$SupabaseUrlFile = "",
    [string]$SupabasePublishableKeyFile = "",
    [string]$AuthorizedEmailsFile = "",
    [string]$AccessTokenFile = "",
    [string]$TunnelTokenFile = "",
    [ValidateRange(10, 120)]
    [int]$ReadyTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$python = Join-Path $projectDirectory ".venv\Scripts\python.exe"
if (-not $RuntimeDirectory) {
    $localApplicationData = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::LocalApplicationData)
    if (-not $localApplicationData) {
        throw "The current user's local application-data directory was not found."
    }
    $RuntimeDirectory = Join-Path $localApplicationData "SolarnaPV"
}
$logDirectory = Join-Path $runtimeDirectory "logs"
$serverOut = Join-Path $logDirectory "server.out.log"
$serverErr = Join-Path $logDirectory "server.err.log"
$tunnelOut = Join-Path $logDirectory "tunnel.out.log"
$tunnelErr = Join-Path $logDirectory "tunnel.err.log"
$serverProcess = $null
$tunnelProcess = $null

if (-not $SecretsDirectory) {
    $SecretsDirectory = Join-Path $projectDirectory "secrets"
}
if (-not $SupabaseUrlFile) {
    $SupabaseUrlFile = Join-Path $SecretsDirectory "supabase-url.txt"
}
if (-not $SupabasePublishableKeyFile) {
    $SupabasePublishableKeyFile = Join-Path (
        $SecretsDirectory) "supabase-publishable-key.txt"
}
if (-not $AuthorizedEmailsFile) {
    $AuthorizedEmailsFile = Join-Path $SecretsDirectory "authorized-emails.txt"
}
if (-not $AccessTokenFile) {
    $AccessTokenFile = Join-Path $SecretsDirectory "access-token.txt"
}
if (-not $TunnelTokenFile) {
    $TunnelTokenFile = Join-Path $SecretsDirectory "cloudflared-token.txt"
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Solarna's Python environment was not found."
}
if (-not (Test-Path -LiteralPath $SupabaseUrlFile -PathType Leaf)) {
    throw "The Supabase URL file was not found."
}
if (-not (Test-Path -LiteralPath $SupabasePublishableKeyFile -PathType Leaf)) {
    throw "The Supabase publishable-key file was not found."
}
if (-not (Test-Path -LiteralPath $AuthorizedEmailsFile -PathType Leaf)) {
    throw "The authorized-emails file was not found."
}
if (-not (Test-Path -LiteralPath $TunnelTokenFile -PathType Leaf)) {
    throw "The Cloudflare tunnel-token file was not found."
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}

$cloudflared = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $cloudflaredCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
        (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe")
    )
    $cloudflaredPath = $cloudflaredCandidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
    if ($cloudflaredPath) {
        $cloudflared = Get-Item -LiteralPath $cloudflaredPath
    }
}
if (-not $cloudflared) {
    throw "cloudflared was not found."
}
$supabaseUrl = [System.IO.File]::ReadAllText($SupabaseUrlFile).Trim()
$supabasePublishableKey = [System.IO.File]::ReadAllText(
    $SupabasePublishableKeyFile).Trim()
$parsedSupabaseUrl = [Uri]$supabaseUrl
if ($parsedSupabaseUrl.Scheme -ne "https" -or
    -not $parsedSupabaseUrl.Host -or
    $parsedSupabaseUrl.AbsolutePath -ne "/") {
    throw "The Supabase URL must be an HTTPS origin."
}
if (-not $supabasePublishableKey.StartsWith("sb_publishable_") -or
    $supabasePublishableKey.Length -lt 24) {
    throw "The Supabase publishable key is invalid."
}
$authorizedEmails = [System.IO.File]::ReadAllText(
    $AuthorizedEmailsFile).Trim()
if (-not $authorizedEmails) {
    throw "At least one authorized email is required."
}
$accessToken = ""
if (Test-Path -LiteralPath $AccessTokenFile -PathType Leaf) {
    $accessToken = [System.IO.File]::ReadAllText($AccessTokenFile).Trim()
    if ($accessToken -and $accessToken.Length -lt 16) {
        throw "The optional legacy access token must contain at least 16 characters."
    }
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$androidApk = Join-Path $projectDirectory "outputs\deliverables\Solarna-android.apk"
$iosProject = Join-Path $projectDirectory "outputs\deliverables\Solarna-iOS-project.zip"
$serverArguments = @(
    "-m", "solarna.app",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--cache-dir", (Join-Path $projectDirectory ".cache\pvgis"),
    "--output-dir", (Join-Path $projectDirectory "outputs\app"),
    "--android-apk", $androidApk,
    "--ios-project", $iosProject,
    "--allowed-origin", "https://$Domain",
    "--allowed-origin", "capacitor://localhost",
    "--allowed-origin", "https://localhost"
)

function Stop-SolarnaChild {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $Process.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}

try {
    $previousSupabaseUrl = $env:SOLARNA_SUPABASE_URL
    $previousSupabasePublishableKey = $env:SOLARNA_SUPABASE_PUBLISHABLE_KEY
    $previousAuthorizedEmails = $env:SOLARNA_AUTHORIZED_EMAILS
    $previousLoginEmail = $env:SOLARNA_LOGIN_EMAIL
    $previousLoginPassword = $env:SOLARNA_LOGIN_PASSWORD
    $previousAccessToken = $env:SOLARNA_ACCESS_TOKEN
    try {
        $env:SOLARNA_SUPABASE_URL = $supabaseUrl
        $env:SOLARNA_SUPABASE_PUBLISHABLE_KEY = $supabasePublishableKey
        $env:SOLARNA_AUTHORIZED_EMAILS = $authorizedEmails
        Remove-Item Env:SOLARNA_LOGIN_EMAIL -ErrorAction SilentlyContinue
        Remove-Item Env:SOLARNA_LOGIN_PASSWORD -ErrorAction SilentlyContinue
        if ($accessToken) {
            $env:SOLARNA_ACCESS_TOKEN = $accessToken
        } else {
            Remove-Item Env:SOLARNA_ACCESS_TOKEN -ErrorAction SilentlyContinue
        }
        $serverProcess = Start-Process `
            -FilePath $python `
            -ArgumentList $serverArguments `
            -WorkingDirectory $projectDirectory `
            -WindowStyle Hidden `
            -RedirectStandardOutput $serverOut `
            -RedirectStandardError $serverErr `
            -PassThru
    } finally {
        if ($null -eq $previousSupabaseUrl) {
            Remove-Item Env:SOLARNA_SUPABASE_URL -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_SUPABASE_URL = $previousSupabaseUrl
        }
        if ($null -eq $previousSupabasePublishableKey) {
            Remove-Item Env:SOLARNA_SUPABASE_PUBLISHABLE_KEY `
                -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_SUPABASE_PUBLISHABLE_KEY = (
                $previousSupabasePublishableKey)
        }
        if ($null -eq $previousAuthorizedEmails) {
            Remove-Item Env:SOLARNA_AUTHORIZED_EMAILS -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_AUTHORIZED_EMAILS = $previousAuthorizedEmails
        }
        if ($null -eq $previousLoginEmail) {
            Remove-Item Env:SOLARNA_LOGIN_EMAIL -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_LOGIN_EMAIL = $previousLoginEmail
        }
        if ($null -eq $previousLoginPassword) {
            Remove-Item Env:SOLARNA_LOGIN_PASSWORD -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_LOGIN_PASSWORD = $previousLoginPassword
        }
        if ($null -eq $previousAccessToken) {
            Remove-Item Env:SOLARNA_ACCESS_TOKEN -ErrorAction SilentlyContinue
        } else {
            $env:SOLARNA_ACCESS_TOKEN = $previousAccessToken
        }
    }

    $localOrigin = "http://127.0.0.1:$Port"
    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    $serverReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($serverProcess.HasExited) {
            throw "Solarna stopped before becoming ready."
        }
        try {
            $health = Invoke-RestMethod -Uri "$localOrigin/api/health" `
                -TimeoutSec 2
            if ($health.status -eq "ok" -and
                $health.authentication_required -eq $true -and
                $health.authentication_mode -eq "supabase") {
                $serverReady = $true
                break
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $serverReady) {
        throw "Solarna did not become ready within $ReadyTimeoutSeconds seconds."
    }

    $tunnelProcess = Start-Process `
        -FilePath $cloudflared.Source `
        -ArgumentList @(
            "tunnel", "--no-autoupdate", "--protocol", "http2",
            "run", "--token-file", $TunnelTokenFile
        ) `
        -WorkingDirectory $projectDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $tunnelOut `
        -RedirectStandardError $tunnelErr `
        -PassThru

    while (-not $serverProcess.HasExited -and -not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($serverProcess.HasExited) {
        throw "Solarna stopped unexpectedly."
    }
    throw "Cloudflare Tunnel stopped unexpectedly."
} finally {
    Stop-SolarnaChild $tunnelProcess
    Stop-SolarnaChild $serverProcess
}
