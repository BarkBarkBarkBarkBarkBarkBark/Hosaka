# hosaka - one-line installer for windows
#
#   iwr https://install.hosaka.xyz/windows | iex
#
# What this does:
#   1. Checks for Docker Desktop.
#   2. Drops hosaka.cmd + hosaka.ps1 into %LOCALAPPDATA%\Hosaka\bin
#      and adds that folder to the user PATH.
#   3. Pulls the latest container image in the background.
#
# Env overrides (PowerShell):
#   $env:HOSAKA_IMAGE       container image
#   $env:HOSAKA_VERSION     launcher version (default: latest)
#   $env:HOSAKA_NO_PULL     set to 1 to skip the background image pull

$ErrorActionPreference = "Stop"

function Note($m)  { Write-Host "  > $m" -ForegroundColor Cyan }
function OK($m)    { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)   { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

$Version  = $env:HOSAKA_VERSION; if (-not $Version) { $Version = "latest" }
$Image    = $env:HOSAKA_IMAGE;   if (-not $Image)   { $Image   = "ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest" }
$Base     = "https://install.hosaka.xyz"
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
try { & docker info *> $null } catch { Die "docker installed but daemon not running - start Docker Desktop and re-run" }
OK "docker present"

# -- tailscale (optional) -----------------------------------------------------
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    OK "tailscale present - you can link a remote node with: hosaka link <hostname>"
} else {
    Note "tailscale not detected (optional) - install from https://tailscale.com/download to link clients"
}

# -- install dir --------------------------------------------------------------
$InstallDir = Join-Path $env:LOCALAPPDATA "Hosaka\bin"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Note "fetching launcher -> $InstallDir"
Invoke-WebRequest -Uri $CmdUrl -OutFile (Join-Path $InstallDir "hosaka.cmd") -UseBasicParsing
Invoke-WebRequest -Uri $Ps1Url -OutFile (Join-Path $InstallDir "hosaka.ps1") -UseBasicParsing
OK "installed launcher"

# -- PATH ---------------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$InstallDir;$userPath", "User")
    OK "added $InstallDir to user PATH (open a new terminal for it to take effect)"
} else {
    OK "$InstallDir already on PATH"
}

# -- background pull ----------------------------------------------------------
if ($env:HOSAKA_NO_PULL -ne "1") {
    Note "warming up container image in the background ($Image)"
    Start-Job -ScriptBlock { param($i) docker pull $i *> $null } -ArgumentList $Image | Out-Null
}

Write-Host ""
Write-Host "  hosaka is ready." -ForegroundColor Green
Write-Host ""
Write-Host "    hosaka up          start the local node (web UI on http://127.0.0.1:8421)"
Write-Host "    hosaka tui         drop into the console TUI"
Write-Host "    hosaka link HOST   wire this client to a remote hosaka over your tailnet"
Write-Host "    hosaka help        see everything"
Write-Host ""
Write-Host "  signal steady. no wrong way." -ForegroundColor DarkGray
Write-Host ""
