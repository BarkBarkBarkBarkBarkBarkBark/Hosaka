$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Temp = Join-Path ([IO.Path]::GetTempPath()) ("hosaka-installer-test-" + [Guid]::NewGuid())
$OriginalUserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$OriginalPath = $env:PATH
New-Item -ItemType Directory -Path $Temp | Out-Null
$Child = Join-Path $Temp "child.ps1"
@'
param($Root, $Temp, $Scenario)
$ErrorActionPreference = "Stop"
$env:LOCALAPPDATA = Join-Path $Temp "local"
$env:HOSAKA_INSTALL_BASE = "https://example.invalid/test"
$env:HOSAKA_NO_PULL = if ($Scenario -eq "skip") { "1" } else { "" }
$env:HOSAKA_VERSION = ""
$env:HOSAKA_IMAGE = ""
function docker {
    Add-Content (Join-Path $Temp "docker.log") ($args -join ' ')
    $global:LASTEXITCODE = if (($args[0] -eq "info" -and $Scenario -eq "daemon") -or
        ($args[0] -eq "pull" -and $Scenario -eq "pull")) { 1 } else { 0 }
}
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    if (-not $Uri.StartsWith("https://example.invalid/test/bin/")) { throw "Wrong installer host" }
    if ($Scenario -eq "download") { throw "Simulated download failure" }
    if ($Scenario -eq "invalid") {
        Set-Content $OutFile '<html>not a launcher</html>'
    } elseif ($Scenario -eq "syntax" -and $OutFile.EndsWith(".ps1")) {
        Set-Content $OutFile "# hosaka - windows launcher`nif ("
    } else {
        Copy-Item (Join-Path $Root ("install/bin/" + (Split-Path $Uri -Leaf))) $OutFile
    }
}
if ($Scenario -eq "native") { function hosaka {} }
$InstallDir = Join-Path $env:LOCALAPPDATA "Hosaka\bin"
if ($Scenario -eq "preserve") {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item (Join-Path $Root "install/bin/hosaka.cmd") $InstallDir
    Copy-Item (Join-Path $Root "install/bin/hosaka.ps1") $InstallDir
    $Scenario = "pull"
}
& (Join-Path $Root "install/install.ps1")
if (($env:PATH -split ';') -notcontains (Join-Path $env:LOCALAPPDATA "Hosaka\bin")) {
    throw "Installer did not update the current session PATH"
}
'@ | Set-Content $Child

function Run-Scenario($Scenario, $ExpectedSuccess) {
    $Case = Join-Path $Temp $Scenario
    New-Item -ItemType Directory -Path $Case | Out-Null
    & (Join-Path $PSHOME "pwsh") -NoProfile -File $Child $Root $Case $Scenario *> (Join-Path $Case "output")
    $Success = $LASTEXITCODE -eq 0
    if ($Success -ne $ExpectedSuccess) {
        Get-Content (Join-Path $Case "output") | Write-Host
        throw "Unexpected exit status for $Scenario"
    }
    $Installed = Join-Path $Case "local/Hosaka/bin/hosaka.ps1"
    if ($ExpectedSuccess) {
        if (-not (Test-Path $Installed)) { throw "Missing launcher for $Scenario" }
        if ((Get-Content $Installed -Raw) -ne (Get-Content (Join-Path $Root "install/bin/hosaka.ps1") -Raw)) {
            throw "Incorrect launcher installed"
        }
    } elseif ($Scenario -eq "preserve") {
        if ((Get-Content $Installed -Raw) -ne (Get-Content (Join-Path $Root "install/bin/hosaka.ps1") -Raw)) {
            throw "Failed reinstall changed the existing launcher"
        }
    } elseif (Test-Path $Installed) {
        throw "Failed installer installed a launcher for $Scenario"
    }
    if ($Scenario -eq "skip" -and (Select-String -Path (Join-Path $Case "docker.log") -Pattern '^pull ' -Quiet)) {
        throw "HOSAKA_NO_PULL was ignored"
    }
}

try {
    Run-Scenario success $true
    Run-Scenario skip $true
    Run-Scenario daemon $false
    Run-Scenario pull $false
    Run-Scenario download $false
    Run-Scenario invalid $false
    Run-Scenario syntax $false
    Run-Scenario native $false
    Run-Scenario preserve $false
    Write-Host "Windows installer regression tests passed"
    $global:LASTEXITCODE = 0
} finally {
    [Environment]::SetEnvironmentVariable("PATH", $OriginalUserPath, "User")
    $env:PATH = $OriginalPath
    Remove-Item -Recurse -Force $Temp
}
