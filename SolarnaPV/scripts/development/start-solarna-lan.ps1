param(
    [int]$Port = 8766,
    [string]$Address = ""
)

$ErrorActionPreference = "Stop"
$projectDirectory = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535."
}

function Test-PrivateIPv4([System.Net.IPAddress]$IpAddress) {
    $bytes = $IpAddress.GetAddressBytes()
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
    )
}

if (-not $Address) {
    $addresses = @(
        Get-NetIPConfiguration |
            Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ } |
            Select-Object -Unique
    )
    if ($addresses.Count -ne 1) {
        throw "Specify -Address with the computer's private IPv4 address."
    }
    $Address = $addresses[0]
}

$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsedAddress) -or
    $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    -not (Test-PrivateIPv4 $parsedAddress)) {
    throw "Address must be a private IPv4 address."
}

$python = Join-Path $projectDirectory ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Solarna's Python environment was not found."
}

$url = "http://${Address}:$Port"
$androidApk = Join-Path $projectDirectory "outputs\deliverables\Solarna-android.apk"
$iosProject = Join-Path $projectDirectory "outputs\deliverables\Solarna-iOS-project.zip"
Write-Output "Solarna LAN server: $url/"
Write-Output "Android installer: $url/downloads/solarna-android.apk"
Write-Output "iOS project: $url/downloads/solarna-ios-project.zip"
Write-Output "Keep this window open while using the LAN Android build."

Push-Location $projectDirectory
try {
    $serverArguments = @(
        "-m", "solarna.app",
        "--host", "0.0.0.0",
        "--port", "$Port",
        "--android-apk", $androidApk,
        "--ios-project", $iosProject,
        "--allowed-origin", "http://localhost",
        "--allowed-origin", "capacitor://localhost",
        "--allowed-origin", "https://localhost"
    )
    & $python @serverArguments
} finally {
    Pop-Location
}
