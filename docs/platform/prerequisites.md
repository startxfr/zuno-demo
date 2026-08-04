# Platform Prerequisites

The MVP assumes an existing OpenShift 4.20 AWS IPI cluster. Preparation/configuration must cover at least:

- NVIDIA GPU Operator;
- Red Hat OpenShift AI Operator and dependencies;
- DataScienceCluster;
- Keycloak;
- Vault;
- PostgreSQL with pgvector support;
- observability stack;
- SMTP technical identity/connectivity;
- S3 access;
- DNS/routes/certificates;
- credentials for approved model providers and integrations.

`make precheck` verifies prerequisites and `make prepare` installs missing components managed by this repository.
