# ============================================================
# Build Shield - Automated Windows Setup
# Run from the Build Shield project root folder:
#   .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------
# 1. Allow scripts for the current user (safe, no admin needed)
# ------------------------------------------------------------
Write-Step "Setting PowerShell execution policy for current user"
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Bypass -Force
Write-Ok "Execution policy set to Bypass (CurrentUser)"

# ------------------------------------------------------------
# 2. Check prerequisites: Python and Node.js
# ------------------------------------------------------------
Write-Step "Checking prerequisites"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warn "Python not found. Installing via winget..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
python --version
Write-Ok "Python available"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warn "Node.js not found. Installing LTS via winget..."
    winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
node --version
npm --version
Write-Ok "Node.js and npm available"

# ------------------------------------------------------------
# 3. Python virtual environment (.venv)
# ------------------------------------------------------------
Write-Step "Creating Python virtual environment (.venv)"
if (-not (Test-Path ".\.venv")) {
    python -m venv .venv
    Write-Ok ".venv created"
} else {
    Write-Ok ".venv already exists, reusing it"
}

Write-Step "Activating .venv"
& ".\.venv\Scripts\Activate.ps1"
Write-Ok "Virtual environment activated"

# ------------------------------------------------------------
# 4. Python dependencies
# ------------------------------------------------------------
Write-Step "Installing Python dependencies"
python -m pip install --upgrade pip

if (Test-Path ".\requirements.txt") {
    pip install -r requirements.txt
    Write-Ok "Installed from requirements.txt"
} elseif (Test-Path ".\backend\requirements.txt") {
    pip install -r .\backend\requirements.txt
    Write-Ok "Installed from backend\requirements.txt"
} else {
    Write-Warn "No requirements.txt found. Skipping pip install."
}

# ------------------------------------------------------------
# 5. Frontend: npm install + Vite
# ------------------------------------------------------------
Write-Step "Setting up frontend (npm + Vite)"

$frontendDir = $null
if (Test-Path ".\package.json") {
    $frontendDir = "."
} elseif (Test-Path ".\frontend\package.json") {
    $frontendDir = ".\frontend"
} elseif (Test-Path ".\client\package.json") {
    $frontendDir = ".\client"
}

if ($frontendDir) {
    Push-Location $frontendDir
    npm install
    npm install --save-dev vite
    Write-Ok "npm packages and Vite installed in $frontendDir"
    Pop-Location
} else {
    Write-Warn "No package.json found. Skipping npm install."
    Write-Warn "To create a new Vite app run: npm create vite@latest frontend"
}

# ------------------------------------------------------------
# 6. Environment file
# ------------------------------------------------------------
if ((Test-Path ".\.env.example") -and -not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Ok "Created .env from .env.example (edit it with your keys)"
}

# ------------------------------------------------------------
# Done
# ------------------------------------------------------------
Write-Host "`n============================================" -ForegroundColor Green
Write-Host " Build Shield setup complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Start frontend : cd $frontendDir ; npm run dev"
Write-Host "Activate venv  : .\.venv\Scripts\Activate.ps1"