# Build from this directory:
#   docker build -f components/rag-service/Dockerfile -t zuno/rag-service:local components/rag-service
FROM python:3.11-slim AS base

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
