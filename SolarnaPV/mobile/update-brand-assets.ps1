$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$mobileDirectory = $PSScriptRoot
$projectDirectory = Split-Path -Parent $mobileDirectory
$sourceIcon = Join-Path $mobileDirectory "assets\solarna-mark-source.png"
$transparentMark = Join-Path $mobileDirectory "assets\solarna-mark-transparent.png"
$webDirectory = Join-Path $projectDirectory "solarna\web"

if (-not (Test-Path -LiteralPath $sourceIcon -PathType Leaf) -or
    -not (Test-Path -LiteralPath $transparentMark -PathType Leaf)) {
    throw "Solarna Systems source branding assets are missing."
}

function New-BitmapSurface {
    param(
        [int]$Width,
        [int]$Height,
        [System.Drawing.Imaging.PixelFormat]$PixelFormat
    )

    for ($attempt = 1; $attempt -le 2; $attempt++) {
        try {
            return [System.Drawing.Bitmap]::new(
                $Width, $Height, $PixelFormat)
        } catch {
            if ($attempt -eq 2) {
                throw
            }
            [GC]::Collect()
            [GC]::WaitForPendingFinalizers()
        }
    }
}

function New-Bitmap {
    param(
        [string]$Source,
        [string]$Destination,
        [int]$Width,
        [int]$Height
    )

    $sourceImage = [System.Drawing.Image]::FromFile($Source)
    try {
        $bitmap = New-BitmapSurface -Width $Width -Height $Height `
            -PixelFormat ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.CompositingQuality =
                    [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode =
                    [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode =
                    [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.SmoothingMode =
                    [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $graphics.DrawImage($sourceImage, 0, 0, $Width, $Height)
            } finally {
                $graphics.Dispose()
            }
            $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $bitmap.Dispose()
        }
    } finally {
        $sourceImage.Dispose()
    }
}

function New-OpaqueBitmap {
    param(
        [string]$Source,
        [string]$Destination,
        [int]$Width,
        [int]$Height
    )

    $sourceImage = [System.Drawing.Bitmap]::FromFile($Source)
    try {
        $sample = $sourceImage.GetPixel(0, 0)
        $background = [System.Drawing.Color]::FromArgb(
            255, $sample.R, $sample.G, $sample.B)
        $bitmap = New-BitmapSurface -Width $Width -Height $Height `
            -PixelFormat ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.Clear($background)
                $graphics.CompositingQuality =
                    [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode =
                    [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode =
                    [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.SmoothingMode =
                    [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $graphics.DrawImage($sourceImage, 0, 0, $Width, $Height)
            } finally {
                $graphics.Dispose()
            }
            $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $bitmap.Dispose()
        }
    } finally {
        $sourceImage.Dispose()
    }
}

function New-Canvas {
    param(
        [string]$Destination,
        [int]$Width,
        [int]$Height,
        [System.Drawing.Color]$Background,
        [double]$LogoScale,
        [bool]$Transparent = $false
    )

    $logo = [System.Drawing.Image]::FromFile($transparentMark)
    try {
        $bitmap = New-BitmapSurface -Width $Width -Height $Height `
            -PixelFormat ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                if ($Transparent) {
                    $graphics.Clear([System.Drawing.Color]::Transparent)
                } else {
                    $graphics.Clear($Background)
                }
                $graphics.CompositingQuality =
                    [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode =
                    [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode =
                    [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.SmoothingMode =
                    [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                if ($LogoScale -gt 0) {
                    $logoSize = [Math]::Max(
                        1, [int]([Math]::Min($Width, $Height) * $LogoScale))
                    $x = [int](($Width - $logoSize) / 2)
                    $y = [int](($Height - $logoSize) / 2)
                    $graphics.DrawImage($logo, $x, $y, $logoSize, $logoSize)
                }
            } finally {
                $graphics.Dispose()
            }
            $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $bitmap.Dispose()
        }
    } finally {
        $logo.Dispose()
    }
}

foreach ($size in 180, 192, 512) {
    New-Bitmap -Source $sourceIcon `
        -Destination (Join-Path $webDirectory "icon-$size.png") `
        -Width $size -Height $size
}

New-Bitmap -Source $sourceIcon `
    -Destination (Join-Path $mobileDirectory "assets\icon.png") `
    -Width 1024 -Height 1024
New-Canvas -Destination (Join-Path $mobileDirectory "assets\splash.png") `
    -Width 2732 -Height 2732 -Background ([System.Drawing.ColorTranslator]::FromHtml("#073b41")) `
    -LogoScale 0.34

$iosIcon = Join-Path $mobileDirectory `
    "ios\App\App\Assets.xcassets\AppIcon.appiconset\AppIcon-512@2x.png"
New-OpaqueBitmap -Source $sourceIcon -Destination $iosIcon -Width 1024 -Height 1024

$iosSplashDirectory = Join-Path $mobileDirectory `
    "ios\App\App\Assets.xcassets\Splash.imageset"
Get-ChildItem -LiteralPath $iosSplashDirectory -Filter "*.png" | ForEach-Object {
    New-Canvas -Destination $_.FullName -Width 2732 -Height 2732 `
        -Background ([System.Drawing.ColorTranslator]::FromHtml("#073b41")) `
        -LogoScale 0.34
}

$densitySizes = @{
    "mipmap-ldpi" = 36
    "mipmap-mdpi" = 48
    "mipmap-hdpi" = 72
    "mipmap-xhdpi" = 96
    "mipmap-xxhdpi" = 144
    "mipmap-xxxhdpi" = 192
}
$adaptiveSizes = @{
    "mipmap-ldpi" = 81
    "mipmap-mdpi" = 108
    "mipmap-hdpi" = 162
    "mipmap-xhdpi" = 216
    "mipmap-xxhdpi" = 324
    "mipmap-xxxhdpi" = 432
}
$androidResources = Join-Path $mobileDirectory "android\app\src\main\res"
$masterImage = [System.Drawing.Bitmap]::FromFile($sourceIcon)
try {
    $iconBackground = $masterImage.GetPixel(0, 0)
} finally {
    $masterImage.Dispose()
}

foreach ($density in $densitySizes.Keys) {
    $directory = Join-Path $androidResources $density
    $size = $densitySizes[$density]
    New-Bitmap -Source $sourceIcon -Destination (Join-Path $directory "ic_launcher.png") `
        -Width $size -Height $size
    New-Bitmap -Source $sourceIcon -Destination (Join-Path $directory "ic_launcher_round.png") `
        -Width $size -Height $size

    $adaptiveSize = $adaptiveSizes[$density]
    New-Canvas -Destination (Join-Path $directory "ic_launcher_background.png") `
        -Width $adaptiveSize -Height $adaptiveSize -Background $iconBackground -LogoScale 0
    New-Canvas -Destination (Join-Path $directory "ic_launcher_foreground.png") `
        -Width $adaptiveSize -Height $adaptiveSize -Background $iconBackground `
        -LogoScale 0.76 -Transparent $true
}

Get-ChildItem -LiteralPath $androidResources -Recurse -File -Filter "splash.png" |
    ForEach-Object {
        $existing = [System.Drawing.Image]::FromFile($_.FullName)
        try {
            $width = $existing.Width
            $height = $existing.Height
        } finally {
            $existing.Dispose()
        }
        New-Canvas -Destination $_.FullName -Width $width -Height $height `
            -Background ([System.Drawing.ColorTranslator]::FromHtml("#073b41")) `
            -LogoScale 0.34
    }

Write-Output "Solarna Systems branding assets updated."
