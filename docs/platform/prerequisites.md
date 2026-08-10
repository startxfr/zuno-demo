# Platform Prerequisites

The MVP assumes an existing OpenShift 4.20 AWS IPI cluster. Preparation/configuration must cover at least:

- NVIDIA GPU Operator;
- Red Hat OpenShift AI Operator and dependencies;
- DataScienceCluster;
- Keycloak;
- Vault;
- External Secrets Operator (syncs Vault secrets into cluster `Secret`s);
- cert-manager (Vault-backed `ClusterIssuer` for workload/mesh certs);
- service mesh (Istio via the Sail Operator/`servicemeshoperator3`, mesh-wide mTLS);
- PostgreSQL with pgvector and TimescaleDB support - provisions an HA cluster (1 primary + 2 replicas plus PgBouncer), so plan StorageClass capacity accordingly, not a single instance;
- observability stack;
- SMTP technical identity/connectivity;
- S3 access (optional, for PostgreSQL backups - disabled by default);
- DNS/routes/certificates;
- credentials for approved model providers and integrations.

`make day0|d0 check` verifies prerequisites and `make day0|d0 install` installs missing components managed by this repository (ADR-0056).
