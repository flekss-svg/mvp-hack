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

$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
if (Test-Path -LiteralPath $venvPython) {
    $venvScripts = Split-Path -Parent $venvPython
    $env:Path = "$venvScripts$([System.IO.Path]::PathSeparator)$env:Path"
}

$nodeDirectory = Resolve-NodeDirectory
$env:Path = "$nodeDirectory$([System.IO.Path]::PathSeparator)$env:Path"
$npm = Join-Path $nodeDirectory "npm.cmd"
if (-not (Test-Path -LiteralPath $npm)) {
    throw "npm.cmd not found next to node.exe in $nodeDirectory"
}

Write-Host "[1/5] Backend unit tests" -ForegroundColor Cyan
Invoke-Checked $python @("-m", "coverage", "erase")
Invoke-Checked $python @("-m", "pytest", "tests/unit", "-m", "unit", "--cov=app", "--cov-report=")

Write-Host "[2/5] Backend API integration + coverage gate (minimum 80%)" -ForegroundColor Cyan
Invoke-Checked $python @("-m", "pytest", "tests/integration", "-m", "integration", "--cov=app", "--cov-append", "--cov-report=term-missing", "--cov-fail-under=80")

Write-Host "[3/5] Frontend unit/component tests + coverage gate" -ForegroundColor Cyan
Invoke-Checked $npm @("--prefix", "web", "run", "test:run")

Write-Host "[4/5] TypeScript check and production build" -ForegroundColor Cyan
Invoke-Checked $npm @("--prefix", "web", "run", "build")

Write-Host "[5/5] Full-stack Playwright smoke/E2E"
Invoke-Checked $npm @("--prefix", "web", "run", "test:e2e")

Write-Host "All pre-push checks passed." -ForegroundColor Green
