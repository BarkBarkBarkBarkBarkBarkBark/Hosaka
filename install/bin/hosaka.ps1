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
$WorkspaceFile = Join-Path $Home_ "workspace.conf"
$PythonBin = "/opt/hosaka-field-terminal/.venv/bin/python"
$ReadOnlyInventory = $args.Count -gt 0 -and $args[0] -eq "migrate"

if (-not $ReadOnlyInventory) {
  New-Item -ItemType Directory -Force -Path $Home_, $StateDir, (Join-Path $Home_ "runtime"), (Join-Path $Home_ "picoclaw"), (Join-Path $Home_ "workspace"),
    (Join-Path $Home_ "runtime/extensions"), (Join-Path $Home_ "runtime/extension-data"),
    (Join-Path $Home_ "runtime/state"), (Join-Path $Home_ "runtime/logs"), (Join-Path $Home_ "runtime/games/roms/psx") | Out-Null
}

function Note($m) { Write-Host "  > $m" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  + $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

function Have-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { Die "Docker command failed (exit $LASTEXITCODE)" }
}

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

function Runtime-Args {
    $workspace = Join-Path $Home_ "workspace"
    $mode = "rw"
    if (Test-Path $WorkspaceFile) {
        $saved = @(Get-Content $WorkspaceFile)
        if ($saved.Count -ne 2 -or $saved[1] -notin @("ro", "rw")) { Die "invalid workspace configuration; run hosaka workspace clear" }
        $workspace = $saved[0]
        $mode = $saved[1]
        if (-not (Test-Path $workspace -PathType Container)) { Die "shared workspace is missing: $workspace" }
    }
    if ($workspace.Contains(',') -or $Home_.Contains(',')) { Die "Docker mount paths cannot contain commas" }
    $readonly = ""
    if ($ReadOnlyInventory) { $mode = "ro"; $readonly = ",readonly" }
    $mount = "type=bind,src=$workspace,dst=/workspace"
    if ($mode -eq "ro") { $mount += ",readonly" }
    return @(
        "--mount", "type=bind,src=$StateDir,dst=/var/lib/hosaka$readonly",
        "--mount", "type=bind,src=$(Join-Path $Home_ 'runtime'),dst=/root/.hosaka$readonly",
        "--mount", "type=bind,src=$(Join-Path $Home_ 'picoclaw'),dst=/root/.picoclaw$readonly",
        "--mount", $mount, "--workdir", "/workspace",
        "-e", "PYTHONPATH=/opt/hosaka-field-terminal", "-e", "HOSAKA_PROJECT_DIR=/workspace"
    ) + (Env-File-Args)
}

function Initialize-Runtime($RuntimeArgs) {
    Invoke-Docker run --rm @RuntimeArgs $Image --initialize-only | Out-Null
}

function Run-Local {
    if (-not (Have-Docker)) { Die "docker not running" }
    $command = @($args)
    $tty = @("-i")
    if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) { $tty += "-t" }
    if (Container-Running) {
        if ($ReadOnlyInventory) {
            & docker exec @tty --workdir /workspace -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/opt/hosaka-field-terminal $Container @command
            exit $LASTEXITCODE
        }
        Invoke-Docker exec @tty --workdir /workspace -e PYTHONPATH=/opt/hosaka-field-terminal -e HOSAKA_PROJECT_DIR=/workspace $Container @command
    } else {
        $runtime = Runtime-Args
        $rest = @()
        if ($command.Count -gt 1) { $rest = $command[1..($command.Count - 1)] }
        if ($ReadOnlyInventory) {
            & docker run --rm @tty --read-only --pull=never --network none -e PYTHONDONTWRITEBYTECODE=1 @runtime --entrypoint $command[0] $Image @rest
            exit $LASTEXITCODE
        }
        Initialize-Runtime $runtime
        Invoke-Docker run --rm @tty @runtime --entrypoint $command[0] $Image @rest
    }
}

function Cmd-Workspace {
    if ($args.Count -eq 0) {
        if (Test-Path $WorkspaceFile) { Get-Content $WorkspaceFile }
        else { Write-Host "$(Join-Path $Home_ 'workspace') (private, read-write)" }
        return
    }
    if (Container-Running) { Die "stop the node with hosaka down before changing workspace mounts" }
    if ($args[0] -eq "clear") {
        if ($args.Count -ne 1) { Die "usage: hosaka workspace clear" }
        if (Test-Path $WorkspaceFile) { Remove-Item $WorkspaceFile }
        OK "using the private workspace"
        return
    }
    if ($args.Count -gt 2 -or ($args.Count -eq 2 -and $args[1] -ne "--read-write")) { Die "usage: hosaka workspace PATH [--read-write]" }
    if (-not (Test-Path $args[0] -PathType Container)) { Die "workspace must be an existing directory" }
    $path = (Resolve-Path $args[0]).Path
    if ($path.Contains(',') -or $path.Contains("`n") -or $path.Contains("`r")) { Die "workspace paths cannot contain commas or newlines" }
    $mode = if ($args.Count -eq 2) { "rw" } else { "ro" }
    [IO.File]::WriteAllText($WorkspaceFile, "$path`n$mode`n", [Text.UTF8Encoding]::new($false))
    OK "sharing $path at /workspace ($mode)"
    Note "Only this folder is shared; symlink targets outside it are not exposed."
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
    $runtime = Runtime-Args
    Initialize-Runtime $runtime
    $args = @("run", "-d", "--rm",
              "--name", $Container,
              "-p", "127.0.0.1:${Port}:8421",
              "-e", "HOSAKA_BOOT_MODE=headless",
              "-e", "HOSAKA_DESKTOP_MODE=1") + $runtime + @($Image)
    Invoke-Docker @args | Out-Null
    OK "up -> http://127.0.0.1:$Port"
    Write-Host "    launcher : $PSCommandPath" -ForegroundColor DarkGray
    Write-Host "    state    : $StateDir" -ForegroundColor DarkGray
    Write-Host "    image    : $Image" -ForegroundColor DarkGray
    Write-Host "    try      : hosaka open  |  hosaka tui" -ForegroundColor DarkGray
}

function Cmd-Down {
    if (-not (Have-Docker)) { Die "docker not available" }
    if (Container-Running) { Invoke-Docker stop $Container | Out-Null; OK "stopped" }
    else { Note "already down" }
}

function Cmd-Tui {
    if (Current-Link) { Die "remote native TUI requires SSH; run hosaka unlink to use the local container" }
    Run-Local $PythonBin -m hosaka tui @args
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
function Cmd-Shell { Run-Local bash }

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
    Invoke-Docker pull $Image
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
                             inside the local container, not the host shell
  hosaka configure llm ...   hidden API-key and provider setup
  hosaka secrets <verb>      manage container credentials
  hosaka picoclaw <args>     configure the container's PicoClaw runtime
  hosaka workspace PATH [--read-write] share a folder at /workspace (default read-only)
  hosaka workspace clear     return to the private container workspace
  hosaka open                open the web UI in your browser
  hosaka logs                follow logs from the local node
  hosaka shell               bash shell inside the local container
  hosaka status              what's running + where it points
  hosaka update              pull the latest image
  hosaka link <host[:port]>  route open/status at a remote hosaka (native TUI needs SSH)
  hosaka unlink              go back to using the local node
  hosaka uninstall           remove launcher + local container (keeps state)
  hosaka version             print versions
  hosaka migrate --dry-run [--json]  inventory existing state without initialization
  hosaka extensions ...      author/register packages; no host execution yet
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
    {"tui","console"            -contains $_} { Cmd-Tui @rest }
    "workspace"                    { Cmd-Workspace @rest }
    "paths"                        { Run-Local $PythonBin -m hosaka.paths @rest }
    "migrate"                      { Run-Local $PythonBin -B -m hosaka.migration @rest }
    "extensions"                   { Run-Local $PythonBin -B -m hosaka.extensions @rest }
    "doctor"                       { Run-Local $PythonBin -m hosaka.doctor @rest }
    "configure" {
        if ($rest.Count -lt 1 -or $rest[0] -ne "llm") { Die "usage: hosaka configure llm --provider PROVIDER --model MODEL" }
        $options = @()
        if ($rest.Count -gt 1) { $options = $rest[1..($rest.Count-1)] }
        Run-Local $PythonBin -m hosaka.llm_setup @options
    }
    "secrets" {
        if ($rest.Count -eq 0) { $rest = @("list") }
        if ($rest[0] -in @("set", "unset", "import-picoclaw")) { $rest += "--no-mirror" }
        Run-Local $PythonBin -m hosaka.secrets @rest
    }
    "picoclaw"                     { Run-Local /usr/local/bin/picoclaw @rest }
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
