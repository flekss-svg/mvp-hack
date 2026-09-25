[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

function Resolve-NodeDirectory {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        return Split-Path -Parent $nodeCommand.Source
    }

    $defaultNodeDirectory = "C:\Program Files\nodejs"
    if (Test-Path -LiteralPath (Join-Path $defaultNodeDirectory "node.exe")) {
        return $defaultNodeDirectory
    }

    throw "Node.js not found. Install Node.js LTS and reopen the terminal."
}

if (-not (Test-Path -LiteralPath "venv\Scripts\python.exe")) {
    Invoke-Checked "python" @("-m", "venv", "venv")
}
$python = Join-Path $projectRoot "venv\Scripts\python.exe"

$nodeDirectory = Resolve-NodeDirectory
$env:Path = "$nodeDirectory$([System.IO.Path]::PathSeparator)$env:Path"
$npm = Join-Path $nodeDirectory "npm.cmd"
$npx = Join-Path $nodeDirectory "npx.cmd"
if (-not (Test-Path -LiteralPath $npm) -or -not (Test-Path -LiteralPath $npx)) {
    throw "npm.cmd or npx.cmd not found next to node.exe in $nodeDirectory"
}

Invoke-Checked $python @("-m", "pip", "install", "-r", "requirements-dev.txt")
Invoke-Checked $npm @("--prefix", "web", "install")
Push-Location -LiteralPath "web"
try {
    Invoke-Checked $npx @("playwright", "install", "chromium")
} finally {
    Pop-Location
}
Invoke-Checked "git" @("config", "core.hooksPath", ".githooks")

Write-Host "Test environment is ready. Run .\scripts\test-all.ps1" -ForegroundColor Green
