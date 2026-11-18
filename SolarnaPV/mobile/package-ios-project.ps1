param(
    [string]$OutputName = "Solarna-iOS-project.zip"
)

$ErrorActionPreference = "Stop"
$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory
$iosDirectory = Join-Path $mobileDirectory "ios"
$outputDirectory = Join-Path $projectDirectory "outputs\deliverables"

if ($OutputName -notmatch '^[A-Za-z0-9._-]+\.zip$') {
    throw "OutputName must be a safe .zip filename."
}

function Get-BigEndianUInt32 {
    param(
        [byte[]]$Bytes,
        [int]$Offset
    )

    return (
        ([uint32]$Bytes[$Offset] -shl 24) -bor
        ([uint32]$Bytes[$Offset + 1] -shl 16) -bor
        ([uint32]$Bytes[$Offset + 2] -shl 8) -bor
        [uint32]$Bytes[$Offset + 3]
    )
}

function Test-AppStoreIcon {
    param([string]$Path)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $signature = [byte[]](137, 80, 78, 71, 13, 10, 26, 10)
    if ($bytes.Length -lt 26) {
        throw "The iOS App Store icon is not a valid PNG."
    }
    for ($index = 0; $index -lt $signature.Length; $index++) {
        if ($bytes[$index] -ne $signature[$index]) {
            throw "The iOS App Store icon is not a valid PNG."
        }
    }
    $width = Get-BigEndianUInt32 $bytes 16
    $height = Get-BigEndianUInt32 $bytes 20
    $bitDepth = $bytes[24]
    $colorType = $bytes[25]
    if ($width -ne 1024 -or $height -ne 1024 -or
        $bitDepth -ne 8 -or $colorType -ne 2) {
        throw "The iOS App Store icon must be a 1024 x 1024 opaque RGB PNG."
    }
}

Push-Location $mobileDirectory
try {
    & npm.cmd run prepare:web
    if ($LASTEXITCODE -ne 0) {
        throw "Mobile web preparation failed."
    }
    & npx.cmd cap sync ios
    if ($LASTEXITCODE -ne 0) {
        throw "Capacitor iOS synchronization failed."
    }
} finally {
    Pop-Location
}

$iconPath = Join-Path $iosDirectory `
    "App\App\Assets.xcassets\AppIcon.appiconset\AppIcon-512@2x.png"
Test-AppStoreIcon $iconPath

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$targetArchive = Join-Path $outputDirectory $OutputName
$temporaryArchive = Join-Path $outputDirectory (
    "$OutputName." + [Guid]::NewGuid().ToString("N") + ".tmp.zip")
$temporaryRoot = [System.IO.Path]::GetFullPath(
    [System.IO.Path]::GetTempPath()).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar)
$checkDirectory = Join-Path $temporaryRoot (
    "solarna-ios-package-" + [Guid]::NewGuid().ToString("N"))

try {
    & tar.exe -a -c -f $temporaryArchive -C $iosDirectory `
        App capacitor-cordova-ios-plugins .gitignore debug.xcconfig `
        APP-STORE-SUBMISSION.md `
        -C $mobileDirectory build-ios-release.sh
    if ($LASTEXITCODE -ne 0) {
        throw "iOS project archive creation failed."
    }

    $entries = @(& tar.exe -t -f $temporaryArchive)
    if ($LASTEXITCODE -ne 0) {
        throw "iOS project archive listing failed."
    }
    $requiredEntries = @(
        "App/App.xcodeproj/project.pbxproj",
        "App/App/Info.plist",
        "App/App/PrivacyInfo.xcprivacy",
        "App/App/public/index.html",
        "App/App/public/privacy.html",
        "App/CapApp-SPM/Package.swift",
        "App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png",
        "APP-STORE-SUBMISSION.md",
        "build-ios-release.sh"
    )
    $missingEntries = @(
        $requiredEntries | Where-Object { $_ -notin $entries }
    )
    if ($missingEntries.Count) {
        throw "The iOS package is missing: $($missingEntries -join ', ')."
    }

    New-Item -ItemType Directory -Path $checkDirectory | Out-Null
    & tar.exe -x -f $temporaryArchive -C $checkDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "iOS project archive extraction failed."
    }

    $forbiddenFiles = @(
        Get-ChildItem -LiteralPath $checkDirectory -Recurse -Force |
            Where-Object {
                $_.Name -eq "node_modules" -or $_.Name -eq ".DS_Store"
            }
    )
    if ($forbiddenFiles.Count) {
        throw "The iOS package contains generated or platform-specific files."
    }

    $packagedIcon = Join-Path $checkDirectory `
        "App\App\Assets.xcassets\AppIcon.appiconset\AppIcon-512@2x.png"
    Test-AppStoreIcon $packagedIcon

    $capacitorConfig = Get-Content -LiteralPath (
        Join-Path $checkDirectory "App\App\capacitor.config.json") -Raw |
        ConvertFrom-Json
    if ($capacitorConfig.server.url) {
        throw "The iOS project must not embed a temporary server URL."
    }

    Move-Item -LiteralPath $temporaryArchive `
        -Destination $targetArchive -Force
    $item = Get-Item -LiteralPath $targetArchive
    $hash = Get-FileHash -LiteralPath $targetArchive -Algorithm SHA256
    Write-Output "iOS project: $($item.FullName)"
    Write-Output "SHA256: $($hash.Hash)"
} finally {
    if (Test-Path -LiteralPath $temporaryArchive -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryArchive -Force
    }
    $resolvedCheckDirectory = [System.IO.Path]::GetFullPath($checkDirectory)
    $expectedPrefix = $temporaryRoot +
        [System.IO.Path]::DirectorySeparatorChar + "solarna-ios-package-"
    if ($resolvedCheckDirectory.StartsWith(
            $expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedCheckDirectory -PathType Container)) {
        Remove-Item -LiteralPath $resolvedCheckDirectory -Recurse -Force
    }
}
