# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/ai-gateway/Dockerfile -t zuno/ai-gateway:local .
#
# A repo-root build context is required as of ADR-0303/WP-39: this image
# now bakes in policies/model-routing/model-routing-policy.yaml, the same
# "policies/ ships inside the consuming image" convention
# components/mcp-gateway/Dockerfile and components/agent-runtime/Dockerfile
# already follow (see their own header comments) - a policy change ships
# as an ordinary redeploy of this gateway, same as those two.
FROM python:3.11-slim AS base

WORKDIR /app

COPY components/ai-gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/ai-gateway/app ./app
# ADR-0303/WP-39: per-agent/task adapter declarations - see
# app/model_routing_policy.py for the graceful-degradation behavior if
# this directory is ever absent (every request just uses the base model,
# never a startup failure).
COPY policies/model-routing ./policies/model-routing
# ADR-0309/WP-42: the autonomous-optimization governance policy - same
# graceful degradation (absent file = autonomy fully disabled, the
# fail-safe direction).
COPY policies/optimization ./policies/optimization

ENV PYTHONUNBUFFERED=1 \
    PROVIDER_ROUTING_PATH=/app/config/provider-routing.yaml \
    MODEL_ROUTING_POLICY_PATH=/app/policies/model-routing/model-routing-policy.yaml \
    OPTIMIZATION_POLICY_PATH=/app/policies/optimization/optimization-policy.yaml

# provider-routing.yaml is NOT baked into the image: it is mounted at
# /app/config/provider-routing.yaml from the `zuno-provider-routing`
# ConfigMap (generated from platform/ai-gateway/provider-routing.yaml by
# ansible/roles/llm's GitOps app) so a routing-policy change doesn't
# require rebuilding/redeploying this image - see gitops/charts/ai-gateway.
# model-routing-policy.yaml deliberately does NOT follow that same
# mounted-ConfigMap pattern: it lives under policies/ (baked in, like
# every other policies/* file), not platform/ai-gateway/ (mounted).

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
