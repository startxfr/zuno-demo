# Network Architecture

The cluster is internet-connected. Namespace-level NetworkPolicies isolate agents and restrict access to shared runtime, AI gateway, MCP gateway, identity, data and approved external endpoints. Direct access from agent namespaces to undeclared MCP servers or data services is denied by default.
