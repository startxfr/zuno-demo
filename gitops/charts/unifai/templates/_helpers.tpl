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

{{/*
Example components and workflows of a team workspace (ADR-0598 point 4): three
agents, a documents retriever, a direct condition and an orchestrator in the
team's inventory, four workflows on them (linear, branches, RAG,
orchestrated), a web-fetch tool and a suspended weekday schedule. No UnifaiChat:
one submitted by the operator has no signed-in user, and the gateway refuses it. A team workflow runs as the team: the retriever finds the documents
uploaded in the team's name and the Confluence sources of the caller's groups
(forwarded token), never a member's personal uploads (see the personal starter).
They reference the public built-in gateway LLM and MCP provider (ADR-0597), so
every member can run them.
Arguments: root (the chart context), owner (an UnifAI admin), team (the team name).
*/}}
{{- define "unifai.teamExamples" -}}
{{- $root := .root }}
{{- $t := .team }}
{{- $llm := printf "$ref:llm/%s" $root.Values.gatewayLLM.name }}
{{- $mcp := printf "$ref:provider/%s" $root.Values.mcpGateway.name }}
{{- $ask := dict "rid" "user_question" "name" "User Question Node" "type" "user_question_node" "config" (dict "type" "user_question_node" "retries" 1) }}
{{- $final := dict "rid" "final_answer" "name" "Final Answer Node" "type" "final_answer_node" "config" (dict "type" "final_answer_node" "retries" 1) }}
{{- $objs := list
  (dict "kind" "UnifaiCondition" "name" (printf "%s-direct" $t) "spec" (dict "type" "router_direct" "config" (dict)))
  (dict "kind" "UnifaiAgent" "name" (printf "%s-assistant" $t) "spec" (dict "type" "custom_agent_node"
    "config" (dict "llm" $llm "hitl_mode" "skip"
      "system_message" (printf "You are the assistant of the %s team. Answer in the language of the question, and say when you are not sure." $t))))
  (dict "kind" "UnifaiAgent" "name" (printf "%s-tools" $t) "spec" (dict "type" "custom_agent_node"
    "config" (dict "llm" $llm "providers" (list $mcp) "strategy_type" "react" "max_rounds" 10 "hitl_mode" "skip"
      "system_message" "Use the MCP tools you are entitled to when they help. Say which tool gave each fact.")))
  (dict "kind" "UnifaiRetriever" "name" (printf "%s-documents" $t) "spec" (dict "type" "docs_rag"
    "config" (dict "source_type" "DOCUMENT" "extra_source_types" (list "CONFLUENCE") "forward_user_token" true "top_k_results" 5 "threshold" 0.3)))
  (dict "kind" "UnifaiAgent" "name" (printf "%s-rag" $t) "spec" (dict "type" "custom_agent_node"
    "config" (dict "llm" $llm "retriever" (printf "$ref:retriever/%s-documents" $t) "hitl_mode" "skip"
      "system_message" "Answer from the retrieved passages only and cite the document or page each fact comes from. If they do not hold the answer, say so.")))
  (dict "kind" "UnifaiAgent" "name" (printf "%s-orchestrator" $t) "spec" (dict "type" "orchestrator_node"
    "config" (dict "llm" $llm "max_rounds" 5
      "system_message" "You coordinate two workers. Delegate with the delegate_task tool; its dst_uid is exactly `assistant` (general questions, writing) or `tools` (anything that needs live data from the MCP tools). Then give a single final answer built from their results.")))
  (dict "kind" "UnifaiWorkflow" "name" (printf "%s-linear" $t) "spec" (dict
    "description" "Example: question, then the team assistant, then the answer."
    "blueprint" (dict
      "nodes" (list $ask $final (dict "rid" (printf "$ref:agent/%s-assistant" $t)))
      "conditions" (list (dict "rid" (printf "$ref:condition/%s-direct" $t)))
      "plan" (list
        (dict "uid" "ask" "node" "user_question" "exit_condition" (printf "$rid:condition/%s-direct" $t) "branches" (dict "agent" "agent"))
        (dict "uid" "agent" "node" (printf "$rid:agent/%s-assistant" $t))
        (dict "uid" "finish" "node" "final_answer" "after" "agent")))))
  (dict "kind" "UnifaiWorkflow" "name" (printf "%s-branches" $t) "spec" (dict
    "description" "Example: the question goes either to the assistant or to the tools agent."
    "blueprint" (dict
      "nodes" (list $ask $final (dict "rid" (printf "$ref:agent/%s-assistant" $t)) (dict "rid" (printf "$ref:agent/%s-tools" $t)))
      "conditions" (list (dict "rid" (printf "$ref:condition/%s-direct" $t)))
      "plan" (list
        (dict "uid" "ask" "node" "user_question" "exit_condition" (printf "$rid:condition/%s-direct" $t) "branches" (dict "chat" "chat" "tools" "tools"))
        (dict "uid" "chat" "node" (printf "$rid:agent/%s-assistant" $t))
        (dict "uid" "tools" "node" (printf "$rid:agent/%s-tools" $t))
        (dict "uid" "finish" "node" "final_answer" "after" (list "chat" "tools"))))))
  (dict "kind" "UnifaiWorkflow" "name" (printf "%s-rag" $t) "spec" (dict
    "description" "Example: answers from your uploaded documents and your groups' Confluence pages, with sources."
    "blueprint" (dict
      "nodes" (list $ask $final (dict "rid" (printf "$ref:agent/%s-rag" $t)))
      "plan" (list
        (dict "uid" "ask" "node" "user_question")
        (dict "uid" "rag" "node" (printf "$rid:agent/%s-rag" $t) "after" "ask")
        (dict "uid" "finish" "node" "final_answer" "after" "rag")))))
  (dict "kind" "UnifaiWorkflow" "name" (printf "%s-orchestrated" $t) "spec" (dict
    "description" "Example: an orchestrator delegates to the assistant and the tools agent, then answers."
    "blueprint" (dict
      "nodes" (list $ask $final (dict "rid" (printf "$ref:agent/%s-orchestrator" $t)) (dict "rid" (printf "$ref:agent/%s-assistant" $t)) (dict "rid" (printf "$ref:agent/%s-tools" $t)))
      "conditions" (list (dict "rid" (printf "$ref:condition/%s-direct" $t)))
      "plan" (list
        (dict "uid" "ask" "node" "user_question" "exit_condition" (printf "$rid:condition/%s-direct" $t) "branches" (dict "agent" "orchestrate"))
        (dict "uid" "orchestrate" "node" (printf "$rid:agent/%s-orchestrator" $t) "after" (list "assistant" "tools")
          "exit_condition" (printf "$rid:condition/%s-direct" $t) "branches" (dict "assistant" "assistant" "tools" "tools" "finish" "finish"))
        (dict "uid" "assistant" "node" (printf "$rid:agent/%s-assistant" $t))
        (dict "uid" "tools" "node" (printf "$rid:agent/%s-tools" $t))
        (dict "uid" "finish" "node" "final_answer")))))
  (dict "kind" "UnifaiTool" "name" (printf "%s-web-fetch" $t) "spec" (dict "type" "web_fetch" "config" (dict)))
  (dict "kind" "UnifaiSchedule" "name" (printf "%s-weekday-brief" $t) "spec" (dict
    "workflow" (printf "%s-linear" $t) "suspend" true
    "inputs" (dict "user_prompt" (printf "Give the %s team a three-line morning brief: what to check first today." $t))
    "schedule" (dict "cron_expression" "30 8 * * 1-5" "timezone" "Europe/Paris" "overlap_policy" "skip")))
}}
{{- $waves := dict "UnifaiWorkflow" "16" "UnifaiSchedule" "17" }}
{{- range $objs }}
apiVersion: unifai.startx.fr/v1alpha1
kind: {{ .kind }}
metadata:
  name: {{ .name }}
  namespace: {{ $root.Values.namespace }}
  annotations:
    # after the team (5) and the built-ins (10); workflows after their components, schedules after workflows
    argocd.argoproj.io/sync-wave: {{ get $waves .kind | default "15" | quote }}
spec:
  owner: {{ $.owner }}
  teamRef: {{ $t }}
  {{- toYaml .spec | nindent 2 }}
---
{{ end }}
{{- end }}

{{/*
Starters in a persona's personal workspace (ADR-0598 point 5): an assistant
agent and a one-step workflow, owned by the persona itself. Arguments: root,
user (the preferred_username).
*/}}
{{- define "unifai.personalStarter" -}}
{{- $root := .root }}
{{- $u := .user }}
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiAgent
metadata:
  name: {{ $u }}-assistant
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "15"
spec:
  owner: {{ $u | quote }}
  type: custom_agent_node
  config:
    llm: {{ printf "$ref:llm/%s" $root.Values.gatewayLLM.name | quote }}
    hitl_mode: skip
    system_message: You are my personal assistant. Answer in the language of the question.
---
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiWorkflow
metadata:
  name: {{ $u }}-my-assistant
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "16"
spec:
  owner: {{ $u | quote }}
  description: My assistant on the Zuno gateway. Copy it, change the prompt, add tools.
  blueprint:
    nodes:
      - {rid: user_question, name: User Question Node, type: user_question_node, config: {type: user_question_node, retries: 1}}
      - {rid: final_answer, name: Final Answer Node, type: final_answer_node, config: {type: final_answer_node, retries: 1}}
      - {rid: "$ref:agent/{{ $u }}-assistant"}
    plan:
      - {uid: ask, node: user_question}
      - {uid: agent, node: "$rid:agent/{{ $u }}-assistant", after: ask}
      - {uid: finish, node: final_answer, after: agent}
---
{{/* A personal RAG: in the personal workspace the search runs as the persona, so it
     sees the persona's own uploads (a team workflow searches as the team and does not). */}}
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiRetriever
metadata:
  name: {{ $u }}-documents
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "15"
spec:
  owner: {{ $u | quote }}
  type: docs_rag
  config:
    source_type: DOCUMENT
    extra_source_types: [CONFLUENCE]
    forward_user_token: true
    top_k_results: 5
    threshold: 0.3
---
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiAgent
metadata:
  name: {{ $u }}-rag
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "15"
spec:
  owner: {{ $u | quote }}
  type: custom_agent_node
  config:
    llm: {{ printf "$ref:llm/%s" $root.Values.gatewayLLM.name | quote }}
    retriever: "$ref:retriever/{{ $u }}-documents"
    hitl_mode: skip
    system_message: Answer from the retrieved passages only and cite the document or page each fact comes from. If they do not hold the answer, say so.
---
apiVersion: unifai.startx.fr/v1alpha1
kind: UnifaiWorkflow
metadata:
  name: {{ $u }}-my-documents
  namespace: {{ $root.Values.namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "16"
spec:
  owner: {{ $u | quote }}
  description: Answers from the documents I uploaded and my groups' Confluence pages, with sources.
  blueprint:
    nodes:
      - {rid: user_question, name: User Question Node, type: user_question_node, config: {type: user_question_node, retries: 1}}
      - {rid: final_answer, name: Final Answer Node, type: final_answer_node, config: {type: final_answer_node, retries: 1}}
      - {rid: "$ref:agent/{{ $u }}-rag"}
    plan:
      - {uid: ask, node: user_question}
      - {uid: rag, node: "$rid:agent/{{ $u }}-rag", after: ask}
      - {uid: finish, node: final_answer, after: rag}
---
{{- end }}
