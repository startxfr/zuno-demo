# Defaults to the zuno-ai-build ImageStream mirror
# (ansible/roles/image_mirrors), not docker.io directly.
# .github/workflows/build-publish.yml (ADR-0115) overrides this ARG to the
# real docker.io image for GitHub-hosted runners.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.12-slim
FROM ${BASE_IMAGE}

# ADR-0115: patch known HIGH CVEs baked into the upstream base image at
# build time - apt upgrade picks up patched OS packages, pip upgrade picks
# up patched pip/setuptools/wheel.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
