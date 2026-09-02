<!-- GENERATED FILE (ADR-0503/WP-45) - do not edit. Source: helm
template gitops/charts/comage. Regenerate with: python3 platform/okf/generate_deployment_snapshot.py -->

# Comage rendered deployment surface

Every object `gitops/charts/comage` renders (raw-manifest chart - not CR-managed; see `README.md` in this directory for what that means for this agent):

| Kind | Name | Container images |
|---|---|---|
| NetworkPolicy | `comage-bff` | — |
| ServiceAccount | `comage-frontend` | — |
| ServiceAccount | `comage-bff` | — |
| Service | `comage-frontend` | — |
| Service | `comage-bff` | — |
| Deployment | `comage-frontend` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-frontend:latest` |
| Deployment | `comage-bff` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-bff:latest` |
| ExternalSecret | `comage-bff-admin-secret` | — |
| ExternalSecret | `comage-frontend-secrets` | — |
| Route | `comage-frontend` | — |
