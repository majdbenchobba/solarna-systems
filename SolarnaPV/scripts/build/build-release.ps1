param(
    [string]$ApiUrl = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$mobileDirectory = Join-Path $projectDirectory "mobile"
$python = Join-Path $projectDirectory ".venv\Scripts\python.exe"
$deliverableDirectory = Join-Path $projectDirectory "outputs\deliverables"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Solarna's Python environment was not found."
}

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

$projectConfig = Get-Content -LiteralPath (
    Join-Path $projectDirectory "pyproject.toml") -Raw
$versionMatch = [regex]::Match(
    $projectConfig, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "The Solarna version was not found."
}
$version = $versionMatch.Groups[1].Value
$mobilePackage = Get-Content -LiteralPath (
    Join-Path $mobileDirectory "package.json") -Raw | ConvertFrom-Json
$androidProject = Get-Content -LiteralPath (
    Join-Path $mobileDirectory "android\app\build.gradle") -Raw
$iosProject = Get-Content -LiteralPath (
    Join-Path $mobileDirectory "ios\App\App.xcodeproj\project.pbxproj") -Raw
if ($mobilePackage.version -ne $version -or
    $androidProject -notmatch (
        'versionName\s+"' + [regex]::Escape($version) + '"') -or
    $iosProject -notmatch (
        'MARKETING_VERSION\s*=\s*' + [regex]::Escape($version) + ';')) {
    throw "Python, mobile, Android and iOS versions must match."
}

& (Join-Path $mobileDirectory "update-brand-assets.ps1")

Push-Location $mobileDirectory
try {
    & npm.cmd run prepare:web
    if ($LASTEXITCODE -ne 0) {
        throw "Mobile web preparation failed."
    }
    & npx.cmd cap sync android
    if ($LASTEXITCODE -ne 0) {
        throw "Android project synchronization failed."
    }
    & npx.cmd cap sync ios
    if ($LASTEXITCODE -ne 0) {
        throw "iOS project synchronization failed."
    }
} finally {
    Pop-Location
}

if (-not $SkipTests) {
    Push-Location $projectDirectory
    try {
        & $python -m unittest discover -s tests -q
        if ($LASTEXITCODE -ne 0) {
            throw "Python tests failed."
        }
    } finally {
        Pop-Location
    }
    Push-Location $mobileDirectory
    try {
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) {
            throw "Mobile tests failed."
        }
    } finally {
        Pop-Location
    }
}

$androidArguments = @{}
if ($ApiUrl) {
    $androidArguments["ApiUrl"] = $ApiUrl
}
try {
    & (Join-Path $mobileDirectory "build-android.ps1") @androidArguments

    New-Item -ItemType Directory -Force -Path $deliverableDirectory | Out-Null
    $androidSource = Join-Path $projectDirectory `
        "outputs\mobile\Solarna-android-debug.apk"
    $androidTarget = Join-Path $deliverableDirectory "Solarna-android.apk"
    Copy-Item -LiteralPath $androidSource -Destination $androidTarget -Force

    if (-not $env:ANDROID_HOME) {
        $env:ANDROID_HOME = Join-Path $projectDirectory ".tooling\android-sdk"
    }
    $buildTools = Get-ChildItem -LiteralPath (
        Join-Path $env:ANDROID_HOME "build-tools") -Directory |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1
    if (-not $buildTools) {
        throw "Android build tools were not found."
    }
    $apkSigner = Join-Path $buildTools.FullName "apksigner.bat"
    & $apkSigner verify --verbose $androidTarget
    if ($LASTEXITCODE -ne 0) {
        throw "Android APK signature verification failed."
    }

    & (Join-Path $mobileDirectory "package-ios-project.ps1")
    Copy-Item -LiteralPath (
        Join-Path $mobileDirectory "ANDROID-STORE-SUBMISSION.md") `
        -Destination (
            Join-Path $deliverableDirectory `
                "Solarna-Android-Store-Submission.md") -Force
    Copy-Item -LiteralPath (
        Join-Path $mobileDirectory "ios\APP-STORE-SUBMISSION.md") `
        -Destination (
            Join-Path $deliverableDirectory `
                "Solarna-iOS-App-Store-Submission.md") -Force
} finally {
    Push-Location $mobileDirectory
    try {
        & npm.cmd run prepare:web
        if ($LASTEXITCODE -ne 0) {
            throw "Mobile web restore failed."
        }
        & npx.cmd cap sync android
        if ($LASTEXITCODE -ne 0) {
            throw "Android project restore failed."
        }
    } finally {
        Pop-Location
    }
}

$iosTarget = Join-Path $deliverableDirectory "Solarna-iOS-project.zip"
$serverTarget = Join-Path $deliverableDirectory "Solarna-server.zip"
& (Join-Path $PSScriptRoot "package-server-release.ps1") `
    -DestinationPath $serverTarget
$artifacts = @(
    [ordered]@{
        platform = "android"
        file = "Solarna-android.apk"
        bytes = (Get-Item -LiteralPath $androidTarget).Length
        sha256 = (Get-FileHash -LiteralPath $androidTarget -Algorithm SHA256).Hash
        installable = $true
        signed = "Android debug signing"
    },
    [ordered]@{
        platform = "ios"
        file = "Solarna-iOS-project.zip"
        bytes = (Get-Item -LiteralPath $iosTarget).Length
        sha256 = (Get-FileHash -LiteralPath $iosTarget -Algorithm SHA256).Hash
        installable = $false
        signed = $false
    },
    [ordered]@{
        platform = "server"
        file = "Solarna-server.zip"
        bytes = (Get-Item -LiteralPath $serverTarget).Length
        sha256 = (Get-FileHash -LiteralPath $serverTarget -Algorithm SHA256).Hash
        installable = $false
        signed = $false
    }
)
$documentation = @(
    "Solarna-Android-Store-Submission.md",
    "Solarna-iOS-App-Store-Submission.md"
) | ForEach-Object {
    $path = Join-Path $deliverableDirectory $_
    [ordered]@{
        file = $_
        bytes = (Get-Item -LiteralPath $path).Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    }
}
$manifest = [ordered]@{
    schema_version = 1
    product = "Solarna PV"
    company = "Solarna Systems"
    version = $version
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    android_api_url = $(if ($ApiUrl) { $ApiUrl } else { $null })
    validation = [ordered]@{
        python_tests = $(if ($SkipTests) { "skipped" } else { "passed" })
        mobile_tests = $(if ($SkipTests) { "skipped" } else { "passed" })
        android_signature = "verified"
        ios_project = "verified"
        server_package = "verified"
    }
    artifacts = $artifacts
    documentation = $documentation
}
$manifestPath = Join-Path $deliverableDirectory "release-manifest.json"
$manifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM

Write-Output ""
Write-Output "Solarna Systems release $version"
Write-Output "Android: $androidTarget"
Write-Output "iOS project: $iosTarget"
Write-Output "Server: $serverTarget"
Write-Output "Manifest: $manifestPath"
