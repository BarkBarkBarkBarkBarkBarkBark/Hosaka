# hosaka - one-line installer for windows
#
#   iwr https://install.hosaka.xyz/windows | iex
#
# What this does:
#   1. Checks for Docker Desktop.
#   2. Drops hosaka.cmd + hosaka.ps1 into %LOCALAPPDATA%\Hosaka\bin
#      and adds that folder to the user PATH.
#   3. Pulls the container image and checks for download failures.
#
# Env overrides (PowerShell):
#   $env:HOSAKA_IMAGE       container image
#   $env:HOSAKA_VERSION     launcher version (default: latest)
#   $env:HOSAKA_NO_PULL     set to 1 to skip the image pull
#   $env:HOSAKA_INSTALL_BASE installer host (default: https://install.hosaka.xyz)

$ErrorActionPreference = "Stop"

function Note($m)  { Write-Host "  > $m" -ForegroundColor Cyan }
function OK($m)    { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)   { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

$Version  = $env:HOSAKA_VERSION; if (-not $Version) { $Version = "latest" }
$Image    = $env:HOSAKA_IMAGE;   if (-not $Image)   { $Image   = "ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest" }
$Base     = $env:HOSAKA_INSTALL_BASE; if (-not $Base) { $Base = "https://install.hosaka.xyz" }
$Base     = $Base.TrimEnd('/')
$CmdUrl   = if ($Version -eq "latest") { "$Base/bin/hosaka.cmd" } else { "$Base/bin/hosaka.cmd@$Version" }
$Ps1Url   = if ($Version -eq "latest") { "$Base/bin/hosaka.ps1" } else { "$Base/bin/hosaka.ps1@$Version" }

Write-Host ""
Write-Host "  hosaka client installer (windows)" -ForegroundColor Cyan
Write-Host ""

# -- docker check -------------------------------------------------------------
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Warn "docker not found - hosaka needs Docker Desktop as the runtime"
    Write-Host "    install with:  winget install Docker.DockerDesktop" -ForegroundColor Cyan
    Write-Host "           or:    https://www.docker.com/products/docker-desktop"
    Write-Host ""
    Write-Host "    re-run this installer after docker is on PATH."
    exit 1
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Die "docker installed but daemon not running - start Docker Desktop and re-run" }
OK "docker present"

# -- tailscale (optional) -----------------------------------------------------
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    OK "tailscale present - you can link a remote node with: hosaka link <hostname>"
} else {
    Note "tailscale not detected (optional) - install from https://tailscale.com/download to link clients"
}

# -- install dir --------------------------------------------------------------
$InstallDir = Join-Path $env:LOCALAPPDATA "Hosaka\bin"
$Existing = Get-Command hosaka -ErrorAction SilentlyContinue
if ($Existing -and $Existing.Source -ne (Join-Path $InstallDir "hosaka.cmd")) {
    Die "existing Hosaka at $($Existing.Source) - this installer will not replace a different installation"
}
if (Test-Path (Join-Path $InstallDir "hosaka.cmd")) {
    if ((Get-Content (Join-Path $InstallDir "hosaka.cmd") -Raw) -notmatch '%~dp0hosaka\.ps1') {
        Die "refusing to overwrite a non-Docker command shim"
    }
}
if (Test-Path (Join-Path $InstallDir "hosaka.ps1")) {
    if ((Get-Content (Join-Path $InstallDir "hosaka.ps1") -Raw) -notmatch 'hosaka - windows launcher') {
        Die "refusing to overwrite a non-Docker launcher"
    }
}

Note "fetching launcher -> $InstallDir"
$Stage = Join-Path ([IO.Path]::GetTempPath()) ("hosaka-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $Stage | Out-Null
try {
    Invoke-WebRequest -Uri $CmdUrl -OutFile (Join-Path $Stage "hosaka.cmd") -UseBasicParsing
    Invoke-WebRequest -Uri $Ps1Url -OutFile (Join-Path $Stage "hosaka.ps1") -UseBasicParsing
    if ((Get-Content (Join-Path $Stage "hosaka.cmd") -Raw) -notmatch '%~dp0hosaka\.ps1') {
        throw "download is not a Hosaka command shim"
    }
    if ((Get-Content (Join-Path $Stage "hosaka.ps1") -Raw) -notmatch 'hosaka - windows launcher') {
        throw "download is not a Hosaka Docker launcher"
    }
    $ParseErrors = $null
    $Tokens = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Stage "hosaka.ps1"), [ref]$Tokens, [ref]$ParseErrors) | Out-Null
    if ($ParseErrors.Count -gt 0) { throw "downloaded launcher has invalid PowerShell syntax" }
    if ($env:HOSAKA_NO_PULL -ne "1") {
        Note "downloading container image ($Image)"
        & docker pull $Image
        if ($LASTEXITCODE -ne 0) { throw "image download failed - existing launcher was not changed" }
    } else {
        Note "image download skipped; hosaka up will need the image"
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Move-Item -Force (Join-Path $Stage "hosaka.cmd") (Join-Path $InstallDir "hosaka.cmd")
    Move-Item -Force (Join-Path $Stage "hosaka.ps1") (Join-Path $InstallDir "hosaka.ps1")
} finally {
    Remove-Item -Recurse -Force $Stage
}
OK "installed launcher"

# -- PATH ---------------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (($userPath -split ';') -notcontains $InstallDir) {
    [Environment]::SetEnvironmentVariable("PATH", "$InstallDir;$userPath", "User")
    OK "added $InstallDir to user PATH (open a new terminal for it to take effect)"
} else {
    OK "$InstallDir already on PATH"
}
if (($env:PATH -split ';') -notcontains $InstallDir) {
    $env:PATH = "$InstallDir;$env:PATH"
}

Write-Host ""
Write-Host "  hosaka is ready." -ForegroundColor Green
Write-Host ""
Write-Host "    hosaka up          start the local node (web UI on http://127.0.0.1:8421)"
Write-Host "    hosaka open        open the web UI in your browser"
Write-Host "    hosaka tui         drop into the console TUI"
Write-Host "    hosaka link HOST   wire this client to a remote hosaka over your tailnet"
Write-Host "    hosaka help        see everything"
Write-Host ""
Write-Host "  signal steady. no wrong way." -ForegroundColor DarkGray
Write-Host ""
