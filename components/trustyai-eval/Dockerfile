# ADR-0534/WP-109: RAGAS evaluation image. This OpenShift AI release
# train ships NO RAGAS provider or image (checked live 2026-09-02 -
# EvalHub providers are lm-eval/lighteval/guidellm/ibm-clear, plus Garak),
# so per the WP-108 finding this repo builds its own minimal one. Build
# from the REPOSITORY ROOT, same convention as components/agent-runtime:
#
#   docker build -f components/trustyai-eval/Dockerfile -t zuno/trustyai-eval:local .
#
# FROM defaults to the zuno-ai-build ImageStream mirror, not docker.io -
# same reasoning as agent-runtime's own ARG.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE}

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app
COPY components/trustyai-eval/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY components/trustyai-eval/ragas_eval.py .

# Writable HOME for library caches under OpenShift's random UID.
ENV HOME=/tmp
CMD ["python3", "ragas_eval.py"]
