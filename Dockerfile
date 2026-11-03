FROM python:3.13-slim

WORKDIR /app

# Instala curl para health check, git para sync de backups e dependências mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia código da aplicação
COPY . .

# Garante pastas de uploads e backups com permissões adequadas
RUN mkdir -p /app/static/uploads /app/backups

EXPOSE 8000

# Health check embutido para monitoramento do container (FinOps)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "manage.py", "run", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
