param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8768,
    [string]$LoginEmail = "majd@solarnasystems.com",
    [string]$LoginPassword = "",
    [switch]$BuildAndroid,
    [ValidateRange(10, 120)]
    [int]$ReadyTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$python = Join-Path $projectDirectory ".venv\Scripts\python.exe"
$androidRelease = Join-Path $projectDirectory `
    "outputs\deliverables\Solarna-android.apk"
$androidDeliverable = Join-Path $projectDirectory `
    "outputs\deliverables\Solarna-android-HTTPS-test.apk"
$iosProject = Join-Path $projectDirectory `
    "outputs\deliverables\Solarna-iOS-project.zip"
$serverProcess = $null
$tunnelProcess = $null
$restoreAndroid = $false

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Solarna's Python environment was not found."
}

$cloudflared = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    throw "cloudflared was not found."
}

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}

if (-not $LoginPassword) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $LoginPassword = [Convert]::ToHexString($bytes)
}
$parsedLoginEmail = [System.Net.Mail.MailAddress]::new($LoginEmail)
if ($parsedLoginEmail.Address -ne $LoginEmail) {
    throw "LoginEmail must be a valid email address."
}
if ($LoginPassword.Length -lt 12 -or
    $LoginPassword -ne $LoginPassword.Trim()) {
    throw "LoginPassword must contain at least 12 characters without surrounding spaces."
}

$temporaryRoot = [System.IO.Path]::GetFullPath(
    [System.IO.Path]::GetTempPath()).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar)
$logDirectory = Join-Path $temporaryRoot (
    "solarna-https-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $logDirectory | Out-Null
$serverOut = Join-Path $logDirectory "server.out.log"
$serverErr = Join-Path $logDirectory "server.err.log"
$tunnelOut = Join-Path $logDirectory "tunnel.out.log"
$tunnelErr = Join-Path $logDirectory "tunnel.err.log"
$servedAndroidApk = Join-Path $logDirectory "Solarna-android.apk"
$hasAndroidRelease = Test-Path -LiteralPath $androidRelease -PathType Leaf
if ($hasAndroidRelease) {
    Copy-Item -LiteralPath $androidRelease -Destination $servedAndroidApk
}

function Read-ProcessLogs {
    param([string[]]$Paths)
    return ($Paths | ForEach-Object {
        if (Test-Path -LiteralPath $_ -PathType Leaf) {
            Get-Content -LiteralPath $_ -Raw
        }
    }) -join [Environment]::NewLine
}

function Stop-ChildProcess {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $Process.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}

function Restore-AndroidProject {
    $mobileDirectory = Join-Path $projectDirectory "mobile"
    Push-Location $mobileDirectory
    try {
        & npm.cmd run prepare:web
        if ($LASTEXITCODE -ne 0) {
            throw "Mobile web restore failed."
        }
        & npx.cmd cap sync android
        if ($LASTEXITCODE -ne 0) {
            throw "Android restore sync failed."
        }
    } finally {
        Pop-Location
    }
}

try {
    $previousLoginEmail = $env:SOLARNA_LOGIN_EMAIL
    $previousLoginPassword = $env:SOLARNA_LOGIN_PASSWORD
    try {
        $env:SOLARNA_LOGIN_EMAIL = $LoginEmail
        $env:SOLARNA_LOGIN_PASSWORD = $LoginPassword
        $serverArguments = @(
            "-m", "solarna.app",
            "--host", "127.0.0.1",
            "--port", "$Port",
            "--android-apk", $servedAndroidApk,
            "--ios-project", $iosProject,
            "--allowed-origin", "capacitor://localhost",
            "--allowed-origin", "https://localhost"
        )
        $serverProcess = Start-Process `
            -FilePath $python `
            -ArgumentList $serverArguments `
            -WorkingDirectory $projectDirectory `
            -WindowStyle Hidden `
            -RedirectStandardOutput $serverOut `
            -RedirectStandardError $serverErr `
            -PassThru
    } finally {
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
    }

    $localOrigin = "http://127.0.0.1:$Port"
    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    $serverReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($serverProcess.HasExited) {
            $logs = Read-ProcessLogs @($serverOut, $serverErr)
            throw "Solarna server stopped before becoming ready.`n$logs"
        }
        try {
            $health = Invoke-RestMethod -Uri "$localOrigin/api/health" `
                -TimeoutSec 2
            if ($health.status -eq "ok" -and
                $health.authentication_required -eq $true -and
                $health.authentication_mode -eq "login") {
                $serverReady = $true
                break
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $serverReady) {
        throw "Solarna server did not become ready within $ReadyTimeoutSeconds seconds."
    }

    $tunnelArguments = @(
        "tunnel",
        "--url", $localOrigin,
        "--protocol", "http2",
        "--no-autoupdate"
    )
    $tunnelProcess = Start-Process `
        -FilePath $cloudflared.Source `
        -ArgumentList $tunnelArguments `
        -WorkingDirectory $projectDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $tunnelOut `
        -RedirectStandardError $tunnelErr `
        -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    $publicUrl = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($tunnelProcess.HasExited) {
            $logs = Read-ProcessLogs @($tunnelOut, $tunnelErr)
            throw "Cloudflare Tunnel stopped before becoming ready.`n$logs"
        }
        $logs = Read-ProcessLogs @($tunnelOut, $tunnelErr)
        $match = [regex]::Match(
            $logs, "https://[a-z0-9-]+\.trycloudflare\.com")
        if ($match.Success) {
            $publicUrl = $match.Value
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $publicUrl) {
        throw "Cloudflare Tunnel did not provide a public URL within $ReadyTimeoutSeconds seconds."
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    $publicHealth = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($tunnelProcess.HasExited) {
            $logs = Read-ProcessLogs @($tunnelOut, $tunnelErr)
            throw "Cloudflare Tunnel stopped before its public health check.`n$logs"
        }
        try {
            $candidateHealth = Invoke-RestMethod `
                -Uri "$publicUrl/api/health" `
                -TimeoutSec 5
            if ($candidateHealth.status -eq "ok") {
                $publicHealth = $candidateHealth
                break
            }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }
    if ($publicHealth.status -ne "ok" -or
        $publicHealth.authentication_required -ne $true -or
        $publicHealth.authentication_mode -ne "login" -or
        $publicHealth.ios_project_download_url -ne
            "/downloads/solarna-ios-project.zip" -or
        ($hasAndroidRelease -and
            $publicHealth.android_download_url -ne
                "/downloads/solarna-android.apk")) {
        $healthDetails = $publicHealth | ConvertTo-Json -Compress
        throw "The public Solarna health check failed: $healthDetails"
    }

    if ($BuildAndroid) {
        $restoreAndroid = $true
        & (Join-Path $projectDirectory "mobile\build-android.ps1") `
            -ApiUrl $publicUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Android HTTPS build failed."
        }
        Copy-Item `
            -LiteralPath (Join-Path $projectDirectory `
                "outputs\mobile\Solarna-android-debug.apk") `
            -Destination $androidDeliverable `
            -Force
        Restore-AndroidProject
        $restoreAndroid = $false
    }

    Write-Output ""
    Write-Output "Solarna HTTPS preview"
    Write-Output "Web / iPhone: $publicUrl/"
    Write-Output "Email: $LoginEmail"
    Write-Output "Password: $LoginPassword"
    if ($hasAndroidRelease) {
        Write-Output "Android: $publicUrl/downloads/solarna-android.apk"
    }
    if ($BuildAndroid) {
        Write-Output "HTTPS test APK: $androidDeliverable"
    }
    Write-Output "iOS project: $publicUrl/downloads/solarna-ios-project.zip"
    Write-Output ""
    Write-Output "On iPhone: open the URL in Safari, then Share > Add to Home Screen."
    Write-Output "This temporary preview has no uptime guarantee."
    Write-Output "Keep this window open. Press Ctrl+C to stop."

    while (-not $serverProcess.HasExited -and -not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($serverProcess.HasExited) {
        $logs = Read-ProcessLogs @($serverOut, $serverErr)
        throw "Solarna server stopped unexpectedly.`n$logs"
    }
    $logs = Read-ProcessLogs @($tunnelOut, $tunnelErr)
    throw "Cloudflare Tunnel stopped unexpectedly.`n$logs"
} finally {
    Stop-ChildProcess $tunnelProcess
    Stop-ChildProcess $serverProcess
    if ($restoreAndroid) {
        try {
            Restore-AndroidProject
        } catch {
            Write-Warning $_.Exception.Message
        }
    }
    $resolvedLogDirectory = [System.IO.Path]::GetFullPath($logDirectory)
    $expectedPrefix = $temporaryRoot +
        [System.IO.Path]::DirectorySeparatorChar + "solarna-https-"
    if ($resolvedLogDirectory.StartsWith(
            $expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedLogDirectory -PathType Container)) {
        Remove-Item -LiteralPath $resolvedLogDirectory -Recurse -Force
    }
}
