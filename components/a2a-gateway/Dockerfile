# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/a2a-gateway/Dockerfile -t zuno/a2a-gateway:local .
#
# FROM image below defaults to the zuno-ai-build ImageStream mirror (ansible/roles/image_mirrors),
# like the other gateways. Agents and the corp limits policy are not baked: the okf-fetch init
# container of gitops/charts/a2a-gateway extracts the admitted release into /okf at pod start.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

COPY components/a2a-gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/a2a-gateway/app ./app

ENV AGENTS_DIR=/okf/agents \
    LIMITS_POLICY_PATH=/okf/policies/limits/limits-policy.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
