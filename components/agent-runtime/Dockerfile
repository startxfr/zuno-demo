# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/mcp-gateway/Dockerfile - this image bakes in the OKF v0.2
# Markdown bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md +
# prompts/*.md) that app/registry.py's AgentRegistry (ADR-0039) loads at
# startup, so an agent-definition edit ships as an ordinary redeploy of
# this runtime:
#
#   docker build -f components/agent-runtime/Dockerfile -t zuno/agent-runtime:local .
FROM python:3.11-slim AS base

WORKDIR /app

COPY components/agent-runtime/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/agent-runtime/app ./app
COPY agents ./agents

ENV AGENTS_DIR=/app/agents \
    PYTHONUNBUFFERED=1

# No provider-routing config or provider API keys here anymore (ADR-0009
# split) - this service only needs AI_GATEWAY_URL, set at deploy time; see
# components/ai-gateway for where the routing config now lives.

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
