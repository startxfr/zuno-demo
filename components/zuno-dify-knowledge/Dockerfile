# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/zuno-dify-knowledge/Dockerfile -t zuno/zuno-dify-knowledge:local .
#
# FROM image below defaults to the zuno-ai-build ImageStream mirror (ansible/roles/image_mirrors),
# like the gateways. ADR-0599: nothing is baked but the code; the API key is mounted at run time.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

COPY platform/python/bootstrap/tools/requirements.txt /tmp/bootstrap-tools.txt
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --require-hashes --upgrade -r /tmp/bootstrap-tools.txt

WORKDIR /app

COPY components/zuno-dify-knowledge/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/zuno-dify-knowledge/app ./app

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
