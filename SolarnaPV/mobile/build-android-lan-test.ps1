param(
    [Parameter(Mandatory = $true)]
    [string]$ApiUrl,
    [string]$OutputName = "Solarna-android-LAN-test.apk"
)

$ErrorActionPreference = "Stop"
$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory

$parsedApiUrl = [Uri]$ApiUrl
if ($parsedApiUrl.Scheme -ne "http" -or
    $parsedApiUrl.AbsolutePath -ne "/" -or
    $parsedApiUrl.Query -or
    $parsedApiUrl.Fragment -or
    $parsedApiUrl.UserInfo) {
    throw "ApiUrl must be a private LAN origin such as http://192.168.1.20:8766."
}

$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($parsedApiUrl.Host, [ref]$parsedAddress) -or
    $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "ApiUrl must use a private IPv4 address."
}
$bytes = $parsedAddress.GetAddressBytes()
$privateAddress = (
    $bytes[0] -eq 10 -or
    ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
    ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
)
if (-not $privateAddress) {
    throw "ApiUrl must use a private IPv4 address."
}
$apiOrigin = $parsedApiUrl.GetLeftPart([System.UriPartial]::Authority)
if ($OutputName -notmatch '^[A-Za-z0-9._-]+\.apk$') {
    throw "OutputName must be a safe .apk filename."
}

$health = Invoke-RestMethod -Uri "$apiOrigin/api/health" `
    -TimeoutSec 10
if ($health.status -ne "ok" -or $health.service -ne "solarna") {
    throw "The Solarna LAN server health check failed."
}

if (-not $env:JAVA_HOME) {
    $localJdk = Get-ChildItem -LiteralPath "$projectDirectory\.tooling\jdk" -Directory |
        Select-Object -First 1
    if (-not $localJdk) {
        throw "JDK 21 was not found. Set JAVA_HOME or install the local Android toolchain."
    }
    $env:JAVA_HOME = $localJdk.FullName
}

if (-not $env:ANDROID_HOME) {
    $localSdk = "$projectDirectory\.tooling\android-sdk"
    if (-not (Test-Path -LiteralPath $localSdk)) {
        throw "Android SDK was not found. Set ANDROID_HOME or install the local Android toolchain."
    }
    $env:ANDROID_HOME = $localSdk
}
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME

$previousDevelopmentHttp = $env:SOLARNA_MOBILE_DEV_HTTP
$previousAllowHttp = $env:SOLARNA_ALLOW_HTTP

Push-Location $mobileDirectory
try {
    $env:SOLARNA_MOBILE_DEV_HTTP = "1"
    $env:SOLARNA_ALLOW_HTTP = "1"

    & npm.cmd run prepare:web -- --api-url $apiOrigin --allow-http
    if ($LASTEXITCODE -ne 0) { throw "Mobile web preparation failed." }

    & npx.cmd cap sync android
    if ($LASTEXITCODE -ne 0) { throw "Capacitor synchronization failed." }

    & .\android\gradlew.bat -p android assembleDebug --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "Android build failed." }

    $sourceApk = "$mobileDirectory\android\app\build\outputs\apk\debug\app-debug.apk"
    $outputDirectory = "$projectDirectory\outputs\deliverables"
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    $outputApk = Join-Path $outputDirectory $OutputName
    Copy-Item -LiteralPath $sourceApk -Destination $outputApk -Force
    $installNotes = @(
        "Solarna Systems Android LAN test",
        "",
        "1. Connect the Android phone to the same Wi-Fi as this computer.",
        "2. Download and install the APK:",
        "   $apiOrigin/downloads/solarna-android.apk",
        "3. Keep the Solarna LAN server running on this computer.",
        "",
        "This build is limited to the current private network.",
        "Use the HTTPS release build for production."
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath "$outputDirectory\INSTALL-ANDROID-LAN.txt" `
        -Value $installNotes -Encoding utf8
    Write-Output "LAN Android APK: $outputApk"
} finally {
    if ($null -eq $previousDevelopmentHttp) {
        Remove-Item Env:SOLARNA_MOBILE_DEV_HTTP -ErrorAction SilentlyContinue
    } else {
        $env:SOLARNA_MOBILE_DEV_HTTP = $previousDevelopmentHttp
    }
    if ($null -eq $previousAllowHttp) {
        Remove-Item Env:SOLARNA_ALLOW_HTTP -ErrorAction SilentlyContinue
    } else {
        $env:SOLARNA_ALLOW_HTTP = $previousAllowHttp
    }

    & npm.cmd run prepare:web
    if ($LASTEXITCODE -eq 0) {
        & npx.cmd cap sync android
    }
    Pop-Location
}
