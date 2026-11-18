param(
    [string]$ApiUrl = "http://10.0.2.2:8766"
)

$ErrorActionPreference = "Stop"
$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory

$parsedApiUrl = [Uri]$ApiUrl
if ($parsedApiUrl.Scheme -ne "http" -or
    $parsedApiUrl.Host -ne "10.0.2.2" -or
    $parsedApiUrl.AbsolutePath -ne "/" -or
    $parsedApiUrl.Query -or
    $parsedApiUrl.Fragment) {
    throw "The emulator test URL must be an origin such as http://10.0.2.2:8766."
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

    & npm.cmd run prepare:web -- --api-url $ApiUrl --allow-http
    if ($LASTEXITCODE -ne 0) { throw "Mobile web preparation failed." }

    & npx.cmd cap sync android
    if ($LASTEXITCODE -ne 0) { throw "Capacitor synchronization failed." }

    & .\android\gradlew.bat -p android assembleDebug --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "Android build failed." }

    $sourceApk = "$mobileDirectory\android\app\build\outputs\apk\debug\app-debug.apk"
    $outputDirectory = "$projectDirectory\outputs\mobile"
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    $outputApk = "$outputDirectory\Solarna-android-emulator-e2e.apk"
    Copy-Item -LiteralPath $sourceApk -Destination $outputApk -Force
    Write-Output "Android emulator APK: $outputApk"
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
