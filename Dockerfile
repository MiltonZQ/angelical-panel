FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir 'uvicorn[standard]==0.32.0' fastapi==0.115.0 asyncpg==0.29.0 python-dotenv==1.0.1 python-multipart==0.0.17 itsdangerous==2.2.0 httpx==0.28.0

COPY app/ ./app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
