param(
    [string]$ApiUrl = "",
    [string]$OutputName = "Solarna-android-release.aab"
)

$ErrorActionPreference = "Stop"
$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory

if ($ApiUrl) {
    $parsedApiUrl = [Uri]$ApiUrl
    if ($parsedApiUrl.Scheme -ne "https" -or
        -not $parsedApiUrl.Host -or
        $parsedApiUrl.AbsolutePath -ne "/" -or
        $parsedApiUrl.Query -or
        $parsedApiUrl.Fragment -or
        $parsedApiUrl.UserInfo) {
        throw "ApiUrl must be an HTTPS origin such as https://solarna.example.com."
    }
    $ApiUrl = $ApiUrl.TrimEnd("/")
}
if ($OutputName -notmatch '^[A-Za-z0-9._-]+\.aab$') {
    throw "OutputName must be a safe .aab filename."
}

$requiredSigningVariables = @(
    "SOLARNA_ANDROID_KEYSTORE_PATH",
    "SOLARNA_ANDROID_KEYSTORE_PASSWORD",
    "SOLARNA_ANDROID_KEY_ALIAS",
    "SOLARNA_ANDROID_KEY_PASSWORD"
)
$missingSigningVariables = $requiredSigningVariables |
    Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missingSigningVariables) {
    throw "Set the required release signing variables: $($missingSigningVariables -join ', ')."
}

$keystorePath = [System.IO.Path]::GetFullPath($env:SOLARNA_ANDROID_KEYSTORE_PATH)
if (-not (Test-Path -LiteralPath $keystorePath -PathType Leaf)) {
    throw "The release keystore file does not exist."
}
$env:SOLARNA_ANDROID_KEYSTORE_PATH = $keystorePath

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

Push-Location $mobileDirectory
try {
    $prepareArguments = @("run", "prepare:web")
    if ($ApiUrl) {
        $prepareArguments += @("--", "--api-url", $ApiUrl)
    }
    & npm.cmd @prepareArguments
    if ($LASTEXITCODE -ne 0) { throw "Mobile web preparation failed." }

    & npx.cmd cap sync android
    if ($LASTEXITCODE -ne 0) { throw "Capacitor synchronization failed." }

    & .\android\gradlew.bat -p android bundleRelease --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "Android release build failed." }

    $sourceBundle = "$mobileDirectory\android\app\build\outputs\bundle\release\app-release.aab"
    $verification = (
        & "$env:JAVA_HOME\bin\jarsigner.exe" -verify $sourceBundle 2>&1
    ) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or
        $verification -notmatch '(?im)^jar verified' -or
        $verification -match '(?im)jar is unsigned') {
        throw "Android release signature verification failed."
    }
    Write-Output "Android release signature verified."

    $outputDirectory = "$projectDirectory\outputs\deliverables"
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    $outputBundle = Join-Path $outputDirectory $OutputName
    Copy-Item -LiteralPath $sourceBundle -Destination $outputBundle -Force
    Write-Output "Signed Android App Bundle: $outputBundle"
} finally {
    & npm.cmd run prepare:web
    if ($LASTEXITCODE -eq 0) {
        & npx.cmd cap sync android
    }
    Pop-Location
}
