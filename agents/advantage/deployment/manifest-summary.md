<!-- GENERATED FILE (ADR-0503/WP-45) - do not edit. Source: helm
template gitops/charts/advantage. Regenerate with: python3 platform/okf/generate_deployment_snapshot.py -->

# Advantage rendered deployment surface

Every object `gitops/charts/advantage` renders (raw-manifest chart - not CR-managed; see `README.md` in this directory for what that means for this agent):

| Kind | Name | Container images |
|---|---|---|
| NetworkPolicy | `advantage-bff` | — |
| ServiceAccount | `advantage-frontend` | — |
| ServiceAccount | `advantage-bff` | — |
| Service | `advantage-frontend` | — |
| Service | `advantage-bff` | — |
| Deployment | `advantage-frontend` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-frontend:latest` |
| Deployment | `advantage-bff` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-bff:latest` |
| ExternalSecret | `advantage-bff-admin-secret` | — |
| ExternalSecret | `advantage-frontend-secrets` | — |
| Route | `advantage-frontend` | — |
