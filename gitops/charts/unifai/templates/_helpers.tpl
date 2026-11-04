{{/*
Config of the platform's gateway LLM (ADR-0560/0563): the ai-gateway, called
with the signed-in user's token; it ignores the model name and routes by policy.
Shared by the UnifaiLLM and the catalog templates (ADR-0598).
*/}}
{{- define "unifai.gatewayLLMConfig" -}}
model_name: auto
base_url: {{ .Values.gatewayLLM.baseUrl }}
api_key: EMPTY
forward_user_token: true
{{- with .Values.gatewayLLM.timeoutSeconds }}
timeout_seconds: {{ . }}
{{- end }}
default_headers:
  X-Zuno-Run-Id: "{session_id}"
{{- if .Values.gatewayLLM.routingLookup }}
# The message carries why this model answered (class, provider, model,
# fallback): the multiagent backend asks the gateway after the call, with
# the caller's identity (WP-148). Needs a multiagent image with the option.
request_id_header: X-Zuno-Request-Id
metadata_lookup_url: {{ .Values.gatewayLLM.baseUrl }}/routing-decisions/{request_id}
{{- end }}
{{- end }}

{{/*
Config of the MCP tools through mcp-gateway, with the user's own token (ADR-0571 path B).
*/}}
{{- define "unifai.mcpGatewayConfig" -}}
mcp_url: {{ .Values.mcpGateway.url }}
transport_type: "streamable http"
auth_method: forward_user_token
additional_headers:
  X-Zuno-Run-Id: "{session_id}"
{{- end }}

{{/*
Catalog templates on the gateway LLM and MCP provider (ADR-0598): no API key to
enter, so "Configure & Generate" gives a working workflow at once. Arguments:
root (the chart context) and owner (an UnifAI admin).
*/}}
{{- define "unifai.templates" -}}
{{- $root := .root }}
{{- $llm := dict "rid" "llm_rid" "name" "Zuno gateway" "type" "openai_compatible" "config" (merge (dict "type" "openai_compatible") (include "unifai.gatewayLLMConfig" $root | fromYaml)) }}
{{- $mcp := dict "rid" "mcp_rid" "name" "Zuno MCP tools" "type" "mcp_server" "config" (merge (dict "type" "mcp_server") (include "unifai.mcpGatewayConfig" $root | fromYaml)) }}
{{- $ask := dict "rid" "user_question" "name" "User Question Node" "type" "user_question_node" "config" (dict "type" "user_question_node" "retries" 1) }}
{{- $final := dict "rid" "final_answer" "name" "Final Answer Node" "type" "final_answer_node" "config" (dict "type" "final_answer_node" "retries" 1) }}
{{- $templates := list
  (dict "name" "zuno-chat" "category" "Chat" "tags" (list "chat" "zuno")
    "draft" (dict
      "name" "Zuno Chat"
      "description" "One assistant on the Zuno gateway, which picks the model for each question. No API key needed."
      "llms" (list $llm)
      "nodes" (list $ask $final (dict "rid" "agent_rid" "name" "Assistant" "type" "custom_agent_node"
        "config" (dict "type" "custom_agent_node" "llm" "llm_rid" "system_message" "You are a helpful assistant. Answer in the language of the question." "hitl_mode" "skip")))
      "plan" (list (dict "uid" "ask" "node" "user_question") (dict "uid" "answer" "node" "agent_rid" "after" "ask") (dict "uid" "finish" "node" "final_answer" "after" "answer"))))
  (dict "name" "zuno-tools-agent" "category" "Tools" "tags" (list "mcp" "zuno")
    "draft" (dict
      "name" "Zuno Tools Agent"
      "description" "An agent with the MCP tools you are entitled to (mcp-gateway, called with your own token)."
      "llms" (list $llm)
      "providers" (list $mcp)
      "nodes" (list $ask $final (dict "rid" "agent_rid" "name" "Tools Agent" "type" "custom_agent_node"
        "config" (dict "type" "custom_agent_node" "llm" "llm_rid" "providers" (list "mcp_rid") "strategy_type" "react" "max_rounds" 10 "system_message" "Use the tools when they help. Say which tool gave each fact." "hitl_mode" "skip")))
      "plan" (list (dict "uid" "ask" "node" "user_question") (dict "uid" "answer" "node" "agent_rid" "after" "ask") (dict "uid" "finish" "node" "final_answer" "after" "answer"))))
  (dict "name" "zuno-draft-review" "category" "Writing" "tags" (list "writing" "zuno")
    "draft" (dict
      "name" "Zuno Draft and Review"
      "description" "A writer drafts an answer, a reviewer checks and tightens it. Two agents in a row on the Zuno gateway."
      "llms" (list $llm)
      "nodes" (list $ask $final
        (dict "rid" "writer_rid" "name" "Writer" "type" "custom_agent_node"
          "config" (dict "type" "custom_agent_node" "llm" "llm_rid" "system_message" "Write a complete first draft that answers the request." "hitl_mode" "skip"))
        (dict "rid" "reviewer_rid" "name" "Reviewer" "type" "custom_agent_node"
          "config" (dict "type" "custom_agent_node" "llm" "llm_rid" "system_message" "Review the draft you are given: fix errors, cut what is not needed, keep the language of the request. Return only the final text." "hitl_mode" "skip")))
      "plan" (list (dict "uid" "ask" "node" "user_question") (dict "uid" "draft" "node" "writer_rid" "after" "ask") (dict "uid" "review" "node" "reviewer_rid" "after" "draft") (dict "uid" "finish" "node" "final_answer" "after" "review"))))
}}
{{- range $templates }}
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiTemplate
metadata:
  name: {{ .name }}
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "10"
spec:
  owner: {{ $.owner }}
  draft:
    {{- toYaml .draft | nindent 4 }}
  metadata:
    author: zuno
    version: 1.0.0
    is_public: true
    category: {{ .category }}
    tags: {{ toJson .tags }}
---
{{ end }}
{{- end }}
