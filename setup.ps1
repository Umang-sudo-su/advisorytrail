Write-Host "Setting up BuildShield Development Workspace (Windows)..." -ForegroundColor Green

# 1. Check and Auto-Install Git if missing
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git is not installed. Installing Git via winget..." -ForegroundColor Yellow
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
    Write-Host "Git installed! Please restart VS Code/Terminal and run setup again." -ForegroundColor Red
    exit
}

# 2. Check and Auto-Install Docker Desktop if missing
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed. Installing Docker Desktop via winget..." -ForegroundColor Yellow
    winget install --id Docker.DockerDesktop -e --source winget --accept-source-agreements --accept-package-agreements
    Write-Host "`nDocker Desktop installed! Please launch Docker Desktop from the Start menu, wait until it is running, restart VS Code/Terminal, and re-run setup." -ForegroundColor Red
    exit
}

# 3. Check if Docker engine is running
docker info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker Desktop is installed but not running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop from the Windows Start Menu, wait until it says 'Engine running', and re-run setup." -ForegroundColor Red
    exit 1
}

# 4. Spin up PostgreSQL and Redis
Write-Host "Starting database containers (PostgreSQL and Redis)..." -ForegroundColor Cyan
docker compose up -d

# 5. Create Python virtual environment for backend
Write-Host "Setting up Python virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "services/api")) {
    New-Item -ItemType Directory -Path "services/api" | Out-Null
}

if (-not (Test-Path "services/api\.venv")) {
    python -m venv services/api\.venv
    Write-Host "Created services/api\.venv" -ForegroundColor Green
}

# 6. Create local .env file if missing
if (-not (Test-Path "services/api\.env")) {
    $envLines = @(
        "DATABASE_URL=postgresql://buildshield:buildshield_dev_pass@localhost:5432/buildshield_db",
        "REDIS_URL=redis://localhost:6379/0",
        "SECRET_KEY=dev_secret_key_change_in_production"
    )
    Set-Content -Path "services/api\.env" -Value $envLines -Encoding UTF8
    Write-Host "Created services/api\.env with default database settings" -ForegroundColor Green
}

Write-Host "`nSetup Complete! PostgreSQL and Redis are running on Docker." -ForegroundColor Green
Write-Host "To activate backend Python environment, run: .\services\api\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
