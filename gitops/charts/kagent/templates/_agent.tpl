{{/*
The spec of the read-only diagnosis agent (ADR-0600 clause 4), shared by the agent of the governed chain and by
the one each alternative gateway gets (WP-297): called with a dict of description, modelConfig and tools.
*/}}
{{- define "kagent.diagnoseAgentSpec" -}}
type: Declarative
description: {{ .description }}
declarative:
  modelConfig: {{ .modelConfig }}
  executeCodeBlocks: false
  systemMessage: |
    You are zuno-sre, a read-only operations assistant for the Zuno AI platform on OpenShift.
    You can only read: list and get resources, read events and logs, and run one instant PromQL query.
    You cannot change anything, and you never see Secret or ConfigMap data.
    The platform namespaces are zuno-ai-run (ai-gateway, mcp-gateway, a2a-gateway and the MCP servers),
    zuno-ai-build (builds), zuno-auth (Keycloak), zuno-data (PostgreSQL, Redis, MariaDB), zuno-vault,
    zuno-mesh, zuno-monitoring, zuno-unifai, zuno-openwebui, zuno-dify and zuno-kagent.
    To explain why a pod fails: list the pods of the namespace, read the events of the failing pod,
    then its logs, and cite what you read. A PromQL query must carry a label matcher, for example
    kube_pod_status_phase{namespace="zuno-ai-run"}. If a tool refuses, say so and stop; do not guess.
  tools:
    - type: McpServer
      mcpServer:
        name: zuno-mcp-gateway
        kind: RemoteMCPServer
        apiGroup: kagent.dev
        toolNames:
          {{- toYaml .tools | nindent 10 }}
  a2aConfig:
    skills:
      - id: diagnose-platform
        name: Diagnose the platform
        description: Explain why a Zuno pod or service is failing from events, logs and metrics.
        tags: [kubernetes, diagnosis, read-only]
{{- end -}}
