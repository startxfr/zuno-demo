# Network Architecture

The cluster is internet-connected. Namespace-level NetworkPolicies isolate agents and restrict access to shared runtime, AI gateway, MCP gateway, identity, data and approved external endpoints. Direct access from agent namespaces to undeclared MCP servers or data services is denied by default.

A service mesh (Istio, deployed via the `servicemeshoperator` OLM package/Red Hat OpenShift Service Mesh, control plane in `zuno-mesh`) adds a second, workload-identity-based isolation layer on top of NetworkPolicies: mesh-wide mTLS between sidecar-injected workloads (`zuno-ai-run`, `zuno-ai-build`), with mesh certificates issued by a Vault-backed `ClusterIssuer` delegated to directly by the `ServiceMeshControlPlane`. NetworkPolicies remain the coarse-grained, always-on boundary; the mesh adds encrypted, mutually authenticated transport and per-workload identity for traffic that crosses it.
