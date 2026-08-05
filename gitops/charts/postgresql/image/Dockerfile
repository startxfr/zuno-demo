# Adds pgvector to Crunchy Postgres Operator's (PGO) own PostgreSQL 16
# operand image.
#
# PGO does not bundle pgvector out of the box either (open, unresolved
# upstream issue CrunchyData/postgres-operator#3706) - same situation this
# demo already had with CloudNativePG before the ADR-0015 operator swap,
# so a custom image is still required. Crunchy's own operand images are
# UBI8/UBI9-based (registry.developers.crunchydata.com, requires a free
# Crunchy Data account to pull from - see image/README.md), unlike
# CloudNativePG's public ghcr.io Debian-based image.
#
# UNVERIFIED (this environment cannot pull from
# registry.developers.crunchydata.com or build/test this image - see
# ansible/roles/postgresql/README.md for why): the exact base image tag
# for PostgreSQL 16, the package manager (microdnf vs dnf - Crunchy's
# runtime images are commonly minimal UBI images using microdnf), and the
# exact pgvector RPM package name. PGDG's official `pgvector_16` RPM
# (from the PostgreSQL community RPM repository, the same PGDG-RPM
# approach CloudNativePG's own image-building blog post pointed at) is
# the best-documented candidate - confirm all three against a real pull/
# build before relying on this in production, and update this comment
# once confirmed.
FROM registry.developers.crunchydata.com/crunchydata/crunchy-postgres:ubi8-16.4-2

USER root

# If microdnf lacks the PGDG repo definitions this image needs, install
# the postgresql-common/pgdg-redhat-repo RPM first (see
# https://www.postgresql.org/download/linux/redhat/) before this install
# step will find pgvector_16.
RUN microdnf install -y pgvector_16 \
    && microdnf clean all

# Crunchy operand images run as the non-root "postgres" user (uid 26),
# same convention CloudNativePG's images used.
USER 26
