param(
    [string]$ApiUrl = ""
)

$ErrorActionPreference = "Stop"
$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory

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

    & .\android\gradlew.bat -p android assembleDebug --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "Android build failed." }

    $sourceApk = "$mobileDirectory\android\app\build\outputs\apk\debug\app-debug.apk"
    $outputDirectory = "$projectDirectory\outputs\mobile"
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    $outputApk = "$outputDirectory\Solarna-android-debug.apk"
    Copy-Item -LiteralPath $sourceApk -Destination $outputApk -Force
    Write-Output "Android APK: $outputApk"
} finally {
    Pop-Location
}
