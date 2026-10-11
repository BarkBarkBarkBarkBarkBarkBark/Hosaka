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
    Assert-Argument "--seed-config"
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
    Write-Host "Windows Docker client regression tests passed"
    $global:LASTEXITCODE = 0
} finally {
    $env:HOSAKA_HOME = $OldHome
    Remove-Item -Recurse -Force $Temp
    Remove-Variable HosakaTestCalls, HosakaTestRunning -Scope Global
}
