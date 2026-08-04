# Physical Architecture

The MVP targets OpenShift 4.20 on AWS IPI. Each agent receives a dedicated namespace. Shared platform services are deployed into dedicated platform namespaces. OpenShift AI manages local model serving on GPU workers. PostgreSQL, Keycloak, Vault and observability are explicit prerequisites.

Detailed node sizing, namespace names and resource requests are refined during implementation and captured in deployment manifests and configuration documentation.
