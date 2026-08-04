# Build from this directory:
#   docker build -f components/agent-runtime/Dockerfile -t zuno/agent-runtime:local components/agent-runtime
FROM python:3.11-slim AS base

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1

# No provider-routing config or provider API keys here anymore (ADR-0009
# split) - this service only needs AI_GATEWAY_URL, set at deploy time; see
# components/ai-gateway for where the routing config now lives.

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
