# Adds pgvector to the stock CloudNativePG PostgreSQL 16 operand image.
#
# Why a custom image instead of CNPG's ImageVolume extension mechanism
# (`.spec.postgresql.extensions`, using ghcr.io/cloudnative-pg/pgvector):
# that mechanism requires CloudNativePG >= 1.27, PostgreSQL >= 18, and the
# Kubernetes `ImageVolume` feature gate — which is beta and OFF BY DEFAULT
# through at least Kubernetes 1.34 (only enabled by default starting 1.35).
# OpenShift 4.20 (ADR-0002) does not reliably guarantee that feature gate is
# on. Rather than hand-wave a dependency this demo cluster likely doesn't
# have, this Dockerfile uses the officially documented, version-independent
# fallback: install the `postgresql-16-pgvector` apt package on top of the
# standard CNPG operand image. See
# https://cloudnative-pg.io/blog/creating-container-images/.
FROM ghcr.io/cloudnative-pg/postgresql:16-bookworm

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# CNPG operand images run as the non-root "postgres" user (uid 26).
USER 26
