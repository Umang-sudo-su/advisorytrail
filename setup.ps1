Write-Host "🚀 Setting up BuildShield Development Workspace (Windows)..." -ForegroundColor Green

# 1. Check if Docker is running
docker info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Docker Desktop is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# 2. Spin up PostgreSQL and Redis
Write-Host "📦 Starting database containers (PostgreSQL & Redis)..." -ForegroundColor Cyan
docker compose up -d

# 3. Create Python virtual environment for backend
Write-Host "🐍 Setting up Python virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "services/api")) {
    New-Item -ItemType Directory -Path "services/api" | Out-Null
}

if (-not (Test-Path "services/api\.venv")) {
    python -m venv services/api\.venv
    Write-Host "✅ Created services/api\.venv" -ForegroundColor Green
}

# 4. Create local .env file if missing
if (-not (Test-Path "services/api\.env")) {
    @"
DATABASE_URL=postgresql://buildshield:buildshield_dev_pass@localhost:5432/buildshield_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev_secret_key_change_in_production
"@ | Out-File -FilePath "services/api\.env" -Encoding utf8
    Write-Host "✅ Created services/api\.env with default database settings" -ForegroundColor Green
}

Write-Host "`n🎉 Setup Complete! PostgreSQL and Redis are running on Docker." -ForegroundColor Green
Write-Host "👉 To activate backend Python environment, run: .\services\api\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
