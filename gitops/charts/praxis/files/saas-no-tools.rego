# ADR-0619 (amendment of 2026-11-18): an alternative gateway sends a SaaS model C1 content only. The Zuno tools and
# their results can carry C2 data (Confluence, the technical docs), and Praxis has no Zuno classification floor. So a
# call to a SaaS model is refused when it offers tools, or when its messages carry a tool call or a tool result (a chat
# started with tools on a local model, then switched to Claude). A call without tools passes.
#
# Read by the `opa` step of the SaaS route in templates/configmap-policy.yaml. The decision object's reason reaches the
# client as the error message and its rule_source as the error code (praxis-policy OPA decision contract). A request
# whose body the host did not supply is refused too, with its own code.
package zuno.saas

default decision := {"allow": true}

decision := {
    "allow": false,
    "reason": "Praxis could not read this request, so it is not sent to a SaaS model.",
    "rule_source": "saas_request_unreadable",
} if req == null

decision := {
    "allow": false,
    "reason": "Zuno tools and their results are not sent to a SaaS model through Praxis: they can carry C2 data, and this gateway has no Zuno classification floor (ADR-0619). Turn the tools off for this chat, or pick a local model.",
    "rule_source": "saas_tools_not_allowed",
} if {
    req != null
    count(tool_parts) > 0
}

req := object.get(input, ["llm", "request"], null)

# Tools offered to the model: Chat Completions `tools` and the legacy `functions`, or Anthropic Messages `tools`.
tool_parts contains key if {
    some key in ["tools", "functions"]
    list := object.get(req, key, null)
    is_array(list)
    count(list) > 0
}

# A tool result in the history (Chat Completions).
tool_parts contains "tool message" if {
    some m in object.get(req, "messages", [])
    object.get(m, "role", "") == "tool"
}

# A tool call in the history (Chat Completions).
tool_parts contains "tool call" if {
    some m in object.get(req, "messages", [])
    calls := object.get(m, "tool_calls", null)
    is_array(calls)
    count(calls) > 0
}

# A tool call or a tool result block in the history (Anthropic Messages).
tool_parts contains "tool block" if {
    some m in object.get(req, "messages", [])
    content := object.get(m, "content", null)
    is_array(content)
    some block in content
    object.get(block, "type", "") in {"tool_use", "tool_result"}
}
