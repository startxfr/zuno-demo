<!-- GENERATED FILE (ADR-0503/WP-45) - do not edit. Source: helm
template gitops/charts/finage. Regenerate with: python3 platform/okf/generate_deployment_snapshot.py -->

# Finage rendered deployment surface

Every object `gitops/charts/finage` renders (raw-manifest chart - not CR-managed; see `README.md` in this directory for what that means for this agent):

| Kind | Name | Container images |
|---|---|---|
| NetworkPolicy | `finage-bff` | — |
| ServiceAccount | `finage-frontend` | — |
| ServiceAccount | `finage-bff` | — |
| Service | `finage-frontend` | — |
| Service | `finage-bff` | — |
| Deployment | `finage-frontend` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-frontend:latest` |
| Deployment | `finage-bff` | `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/agent-bff:latest` |
| ExternalSecret | `finage-frontend-secrets` | — |
| Route | `finage-frontend` | — |
