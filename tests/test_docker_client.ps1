$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Temp = Join-Path ([IO.Path]::GetTempPath()) ("hosaka-client-test-" + [Guid]::NewGuid())
$OldHome = $env:HOSAKA_HOME
$global:HosakaTestCalls = [Collections.Generic.List[object]]::new()
$global:HosakaTestRunning = $false
function docker {
    $global:HosakaTestCalls.Add(@($args))
    $global:LASTEXITCODE = 0
    if ($args[0] -eq "inspect") { return "$global:HosakaTestRunning".ToLowerInvariant() }
}
function Assert-Argument($Expected) {
    foreach ($call in $global:HosakaTestCalls) {
        if ($call -contains $Expected) { return }
    }
    throw "Missing Docker argument: $Expected"
}
try {
    $project = Join-Path $Temp "project with spaces"
    New-Item -ItemType Directory -Force -Path $project | Out-Null
    $env:HOSAKA_HOME = Join-Path $Temp "home with spaces"
    $cli = Join-Path $Root "install/bin/hosaka.ps1"
    & $cli workspace $project
    & $cli tui
    Assert-Argument "type=bind,src=$project,dst=/workspace,readonly"
    Assert-Argument "tui"
    Assert-Argument "HOSAKA_PROJECT_DIR=/workspace"
    Assert-Argument "--initialize-only"
    foreach ($directory in @("runtime/extensions", "runtime/extension-data")) {
        if (-not (Test-Path (Join-Path $env:HOSAKA_HOME $directory) -PathType Container)) { throw "Missing directory: $directory" }
    }
    & $cli workspace $project --read-write
    $global:HosakaTestCalls.Clear()
    & $cli secrets set EXAMPLE_KEY
    Assert-Argument "--no-mirror"
    Assert-Argument "type=bind,src=$project,dst=/workspace"
    $global:HosakaTestRunning = $true
    $global:HosakaTestCalls.Clear()
    & $cli tui
    Assert-Argument "exec"
    Assert-Argument "/workspace"
    $global:HosakaTestRunning = $false
    & $cli workspace clear
    if (Test-Path (Join-Path $env:HOSAKA_HOME "workspace.conf")) { throw "Workspace clear failed" }
    $global:HosakaTestCalls.Clear()
    & $cli configure llm --provider anthropic --model claude-example
    Assert-Argument "hosaka.llm_setup"
    Assert-Argument "claude-example"
    $global:HosakaTestCalls.Clear()
    & $cli extensions list --json
    Assert-Argument "hosaka.extensions"
    $global:HosakaTestCalls.Clear()
    & $cli migrate --dry-run --json
    Assert-Argument "hosaka.migration"
    Assert-Argument "--read-only"
    Assert-Argument "--pull=never"
    Assert-Argument "none"
    Assert-Argument "type=bind,src=$(Join-Path $env:HOSAKA_HOME 'runtime'),dst=/root/.hosaka,readonly"
    foreach ($call in $global:HosakaTestCalls) {
        if ($call -contains "--initialize-only") { throw "Inventory initialized the runtime" }
    }
    $global:HosakaTestRunning = $true
    $global:HosakaTestCalls.Clear()
    & $cli migrate --dry-run --json
    Assert-Argument "exec"
    Assert-Argument "hosaka.migration"
    foreach ($call in $global:HosakaTestCalls) {
        if ($call -contains "--initialize-only") { throw "Running inventory initialized the runtime" }
    }
    $global:HosakaTestRunning = $false
    $originalHome = $env:HOSAKA_HOME
    $env:HOSAKA_HOME = Join-Path $Temp "absent-runtime"
    & $cli migrate --dry-run --json
    if (Test-Path $env:HOSAKA_HOME) { throw "Inventory created host directories" }
    $env:HOSAKA_HOME = $originalHome
    Write-Host "Windows Docker client regression tests passed"
    $global:LASTEXITCODE = 0
} finally {
    $env:HOSAKA_HOME = $OldHome
    Remove-Item -Recurse -Force $Temp
    Remove-Variable HosakaTestCalls, HosakaTestRunning -Scope Global
}
