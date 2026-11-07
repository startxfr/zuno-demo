# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/world-model-runtime/Dockerfile -t zuno/world-model-runtime:local .
#
# ADR-0604 (WP-231): one GPU container for FLUX.2 klein, Waypoint-1.5 and the H.264 encoder.
# No model weights are baked in: the pod's init container copies them from S3
# (platform/world-model/models.lock.yaml) into /models. The CUDA user space comes with the
# torch wheels; the driver (and libnvidia-encode for NVENC) is mounted by the GPU Operator's
# container toolkit when NVIDIA_DRIVER_CAPABILITIES includes `video`.
# The same image runs on CPU with WORLD_MODEL_ENGINE=mock WORLD_MODEL_IMAGE=mock.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE}

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip==26.0.1 setuptools==84.2.1 wheel==0.48.0

WORKDIR /app

# Hash-checked locks (ADR-0603 M20): the service, then the GPU stack.
COPY components/world-model-runtime/requirements.txt ./requirements.txt
COPY components/world-model-runtime/gpu/requirements.txt ./requirements-gpu.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt -r requirements-gpu.txt

# world_engine and the two archives it pins are not on PyPI: fetch the exact commits,
# check their sha256, install without dependencies (all of them are in the locks above).
ARG WORLD_ENGINE_COMMIT=68b316390d576dd9f671f552803526bbf8eb2ed5
ARG WORLD_ENGINE_SHA256=be856cc941ab0ae3fdc5d4d8f7f2b18366317496b3694f81d6c2d7cc50f295ea
ARG TAEHV_COMMIT=7dc60ec6601af2e668e31bc70acc4cb3665e4c22
ARG TAEHV_SHA256=461ca4bd1b7d4441d6a6da1df8e0fbeded02c26f058be36f29f4d14d97bef25d
ARG GEMLITE_COMMIT=ebfcc197d694acd4ca8dfaadf5fceb3570401df3
ARG GEMLITE_SHA256=6825cd901d750d025f8aae0facd683cb9ec9e1be0763f0dd7f84e50d6a6ea970
RUN set -eux; mkdir /tmp/src; cd /tmp/src; \
    curl -fsSL -o world_engine.zip "https://github.com/Overworldai/world_engine/archive/${WORLD_ENGINE_COMMIT}.zip"; \
    curl -fsSL -o taehv.zip "https://github.com/madebyollin/taehv/archive/${TAEHV_COMMIT}.zip"; \
    curl -fsSL -o gemlite.zip "https://github.com/dropbox/gemlite/archive/${GEMLITE_COMMIT}.zip"; \
    printf '%s  %s\n' "${WORLD_ENGINE_SHA256}" world_engine.zip "${TAEHV_SHA256}" taehv.zip "${GEMLITE_SHA256}" gemlite.zip \
      | sha256sum -c -; \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WORLD_ENGINE="0.0.0+g${WORLD_ENGINE_COMMIT}" \
      pip install --no-cache-dir --no-deps --no-build-isolation ./taehv.zip ./gemlite.zip ./world_engine.zip; \
    cd /; rm -rf /tmp/src; \
    python -c "import torch, world_engine, taehv, gemlite, diffusers, av; print('torch', torch.__version__, 'cuda', torch.version.cuda)"

COPY components/world-model-runtime/app ./app
# The pod runs as an arbitrary non-root UID (group 0): files must be world-readable whatever the
# build context's umask was (a workstation build copies 0600 files).
RUN chmod -R a+rX /app

# Offline at run time: weights come from the S3 mirror, never from Hugging Face.
ENV PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/tmp/hf \
    TRITON_CACHE_DIR=/tmp/triton \
    TORCHINDUCTOR_CACHE_DIR=/tmp/inductor \
    WORLD_MODEL_DIR=/models

USER 1001
EXPOSE 8080

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
