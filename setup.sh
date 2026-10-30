#!/usr/bin/env bash
set -e

echo "🚀 Setting up BuildShield Development Workspace..."

# 1. Check if Docker is running
if ! docker info >/dev/null 2>&1; then
  echo "❌ Error: Docker Desktop is not running. Please start Docker Desktop and run this script again."
  exit 1
fi

# 2. Spin up PostgreSQL and Redis
echo "📦 Starting database containers (PostgreSQL & Redis)..."
docker compose up -d

# 3. Create Python virtual environment for backend
echo "🐍 Setting up Python virtual environment..."
mkdir -p services/api
if [ ! -d "services/api/.venv" ]; then
  python3 -m venv services/api/.venv
  echo "✅ Created services/api/.venv"
fi

# 4. Create local .env file if missing
if [ ! -f "services/api/.env" ]; then
  cat << 'ENVEOF' > services/api/.env
DATABASE_URL=postgresql://buildshield:buildshield_dev_pass@localhost:5432/buildshield_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev_secret_key_change_in_production
ENVEOF
  echo "✅ Created services/api/.env with default database settings"
fi

echo ""
echo "🎉 Setup Complete! PostgreSQL and Redis are running on Docker."
echo "👉 To activate the backend Python environment, run: source services/api/.venv/bin/activate"
