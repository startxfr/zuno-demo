# Build from this directory:
#   docker build -f components/ai-gateway/Dockerfile -t zuno/ai-gateway:local components/ai-gateway
FROM python:3.11-slim AS base

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PROVIDER_ROUTING_PATH=/app/config/provider-routing.yaml

# provider-routing.yaml is NOT baked into the image: it is mounted at
# /app/config/provider-routing.yaml from the `zuno-provider-routing`
# ConfigMap (generated from platform/ai-gateway/provider-routing.yaml by
# ansible/roles/llm's GitOps app) so a routing-policy change doesn't
# require rebuilding/redeploying this image — see gitops/charts/ai-gateway.

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
