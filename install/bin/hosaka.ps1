# hosaka - windows launcher (PowerShell).
#
# Same UX as the mac/linux launcher: wraps docker, speaks to a local
# hosaka container, and optionally routes the tui/web UI at a remote
# hosaka machine on your tailnet.
#
# Config lives in $env:HOSAKA_HOME (default: %USERPROFILE%\.hosaka).

$ErrorActionPreference = "Stop"

$Image     = $env:HOSAKA_IMAGE;     if (-not $Image)     { $Image     = "ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest" }
$Port      = $env:HOSAKA_PORT;      if (-not $Port)      { $Port      = "8421" }
$Home_     = $env:HOSAKA_HOME;      if (-not $Home_)     { $Home_     = Join-Path $env:USERPROFILE ".hosaka" }
$Container = $env:HOSAKA_CONTAINER; if (-not $Container) { $Container = "hosaka" }
$StateDir  = Join-Path $Home_ "state"
$LinkFile  = Join-Path $Home_ "link"
$EnvFile   = Join-Path $Home_ "env"

New-Item -ItemType Directory -Force -Path $Home_, $StateDir | Out-Null

function Note($m) { Write-Host "  > $m" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

function Have-Docker { try { & docker info *> $null; return $true } catch { return $false } }

function Current-Link {
    if (Test-Path $LinkFile) { return (Get-Content $LinkFile -Raw).Trim() }
    return $null
}

function Link-Url($raw) {
    if ($raw -match '^https?://') { return $raw.TrimEnd('/') }
    if ($raw -match ':\d+$')      { return "http://$raw" }
    return "http://${raw}:$Port"
}

function Container-Running {
    if (-not (Have-Docker)) { return $false }
    try {
        $s = & docker inspect -f '{{.State.Running}}' $Container 2>$null
        return ($s -eq "true")
    } catch { return $false }
}

function Env-File-Args {
    if (Test-Path $EnvFile) { return @("--env-file", $EnvFile) }
    return @()
}

function Cmd-Up {
    if (-not (Have-Docker)) { Die "docker not running - start Docker Desktop" }
    if (Container-Running) {
        OK "hosaka already running at http://127.0.0.1:$Port"
        Write-Host "    launcher : $PSCommandPath" -ForegroundColor DarkGray
        Write-Host "    state    : $StateDir" -ForegroundColor DarkGray
        return
    }
    try { & docker rm -f $Container *> $null } catch {}
    Note "starting local node -> http://127.0.0.1:$Port"
    $args = @("run", "-d", "--rm",
              "--name", $Container,
              "-p", "127.0.0.1:${Port}:8421",
              "-v", "${StateDir}:/var/lib/hosaka",
              "-e", "HOSAKA_BOOT_MODE=headless",
              "-e", "HOSAKA_DESKTOP_MODE=1") + (Env-File-Args) + @($Image)
    & docker @args *> $null
    OK "up -> http://127.0.0.1:$Port"
    Write-Host "    launcher : $PSCommandPath" -ForegroundColor DarkGray
    Write-Host "    state    : $StateDir" -ForegroundColor DarkGray
    Write-Host "    image    : $Image" -ForegroundColor DarkGray
    Write-Host "    try      : hosaka open  |  hosaka tui" -ForegroundColor DarkGray
}

function Cmd-Down {
    if (-not (Have-Docker)) { Die "docker not available" }
    if (Container-Running) { & docker stop $Container *> $null; OK "stopped" }
    else { Note "already down" }
}

function Cmd-Tui {
    $link = Current-Link
    if ($link) {
        $target = Link-Url $link
        Note "attaching to remote tui at $target (linked)"
        & docker run --rm -it `
            -e "HOSAKA_REMOTE=$target" `
            -e "HOSAKA_BOOT_MODE=client" `
            -v "${StateDir}:/var/lib/hosaka" `
            $Image
        return
    }
    if (Container-Running) {
        & docker exec -it $Container /opt/hosaka-field-terminal/.venv/bin/python -m hosaka --boot console
        return
    }
    Note "no local node running - starting a one-shot console"
    & docker run --rm -it `
        -v "${StateDir}:/var/lib/hosaka" `
        -e "HOSAKA_BOOT_MODE=console" `
        -e "HOSAKA_DESKTOP_MODE=1" `
        $Image
}

function Cmd-Open {
    $link = Current-Link
    if ($link) { $url = Link-Url $link }
    else {
        if (-not (Container-Running)) { Warn "local node not running. starting it."; Cmd-Up }
        $url = "http://127.0.0.1:$Port"
    }
    Note "opening $url"
    Start-Process $url
}

function Cmd-Logs { if (Container-Running) { & docker logs -f $Container } else { Die "local node not running" } }
function Cmd-Shell { if (Container-Running) { & docker exec -it $Container bash } else { Die "local node not running - try: hosaka up" } }

function Cmd-Status {
    Write-Host ""
    Write-Host "  hosaka" -ForegroundColor Cyan
    Write-Host "    image       : $Image"
    Write-Host "    state dir   : $StateDir"
    Write-Host -NoNewline "    local node  : "
    if (Container-Running) { Write-Host "running at http://127.0.0.1:$Port" -ForegroundColor Green }
    else { Write-Host "stopped" -ForegroundColor DarkGray }
    $link = Current-Link
    if ($link) { Write-Host "    linked to   : $(Link-Url $link)  (remote)" -ForegroundColor Yellow }
    else { Write-Host "    linked to   : (not linked - using local)" -ForegroundColor DarkGray }
    if (Get-Command tailscale -ErrorAction SilentlyContinue) {
        $ts = & tailscale status --self=false 2>$null | Select-Object -First 5
        if ($ts) {
            Write-Host "    tailnet     :"
            $ts | ForEach-Object { Write-Host "      $_" }
        }
    }
    Write-Host ""
}

function Cmd-Update {
    if (-not (Have-Docker)) { Die "docker not available" }
    Note "pulling $Image"
    & docker pull $Image
    if (Container-Running) { Note "restarting local node with fresh image"; Cmd-Down; Cmd-Up }
    OK "updated"
}

function Cmd-Link($host_) {
    if (-not $host_) { Die "usage: hosaka link <host[:port]>" }
    Set-Content -Path $LinkFile -Value $host_ -NoNewline
    OK "linked to $(Link-Url $host_)"
    Note "hosaka tui / hosaka open now target the remote"
    Note "run 'hosaka unlink' to go back to local"
}

function Cmd-Unlink {
    if (Test-Path $LinkFile) { Remove-Item $LinkFile; OK "unlinked - back to local node" }
    else { Note "not linked" }
}

function Cmd-Uninstall {
    Warn "uninstalling hosaka launcher"
    try { if (Container-Running) { & docker stop $Container *> $null } } catch {}
    try { & docker rm -f $Container *> $null } catch {}
    $binDir = Split-Path -Parent $PSCommandPath
    Remove-Item (Join-Path $binDir "hosaka.cmd") -ErrorAction SilentlyContinue
    Remove-Item $PSCommandPath -ErrorAction SilentlyContinue
    OK "removed launcher from $binDir"
    Note "state kept at $Home_ (delete manually if you want a clean slate)"
}

function Cmd-Version {
    Write-Host "hosaka launcher : 0.1.0"
    Write-Host "image           : $Image"
    if (Have-Docker) {
        try {
            $digest = & docker image inspect $Image --format '{{index .RepoDigests 0}}' 2>$null
            if ($digest) { Write-Host "image digest    : $digest" }
        } catch {}
    }
}

function Cmd-Help {
    @"
hosaka - client for the Hosaka Field Terminal.

  hosaka up                  start the local node (web UI on http://127.0.0.1:$Port)
  hosaka down                stop the local node
  hosaka tui                 drop into the console TUI
                             (against the linked remote if `hosaka link` was run)
  hosaka open                open the web UI in your browser
  hosaka logs                follow logs from the local node
  hosaka shell               bash shell inside the local container
  hosaka status              what's running + where it points
  hosaka update              pull the latest image
  hosaka link <host[:port]>  route tui/open/status at a remote hosaka
  hosaka unlink              go back to using the local node
  hosaka uninstall           remove launcher + local container (keeps state)
  hosaka version             print versions
  hosaka help                this message

signal steady. no wrong way.
"@ | Write-Host
}

# -- dispatch -----------------------------------------------------------------
$cmd = $args[0]; $rest = @()
if ($args.Count -gt 1) { $rest = $args[1..($args.Count-1)] }

switch ($cmd) {
    "up"                           { Cmd-Up }
    {"down","stop"              -contains $_} { Cmd-Down }
    {"tui","console"            -contains $_} { Cmd-Tui }
    "open"                         { Cmd-Open }
    "logs"                         { Cmd-Logs }
    {"shell","sh"               -contains $_} { Cmd-Shell }
    {"status","st"              -contains $_} { Cmd-Status }
    {"update","pull"            -contains $_} { Cmd-Update }
    "link"                         { Cmd-Link $rest[0] }
    "unlink"                       { Cmd-Unlink }
    "uninstall"                    { Cmd-Uninstall }
    {"version","-v","--version" -contains $_} { Cmd-Version }
    {"help","-h","--help",$null -contains $_} { Cmd-Help }
    default { Warn "unknown command: $cmd"; Cmd-Help; exit 1 }
}
