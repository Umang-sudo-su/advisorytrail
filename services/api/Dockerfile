# Use an official lightweight Python image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for PostgreSQL
RUN apt-get update     && apt-get install -y gcc libpq-dev     && apt-get clean

RUN apt-get update && apt-get install -y git golang
RUN go install github.com/google/osv-scanner/cmd/osv-scanner@v1
ENV PATH="/root/go/bin:${PATH}"

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port Uvicorn runs on
EXPOSE 8000

# Command to run Alembic migrations and then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
