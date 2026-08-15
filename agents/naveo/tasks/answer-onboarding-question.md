---
okf_version: v0.2
type: task
title: Answer an onboarding question
zuno:
  allowed_tools:
    - search_confluence
    - web_search
    - list_drive_files

  live_read_tool: search_confluence
  allowed_knowledge:
    - knowledge.tech
    - knowledge.project
---

# Answer an onboarding question

Answer an onboarding question using Naveo's declared knowledge domains
and tool capabilities, all reused from the existing platform catalog
(ADR-0410 - no new knowledge domain or external backend for a
template-scaffolded agent).

This is the task Agent Runtime's generic chat dispatch (`POST
/v1/agents/naveo/chat`, ADR-0342) executes once `status: active` -
see `components/agent-runtime/app/registry.py` (ADR-0039) for how the
`allowed_tools`/`allowed_knowledge` above and
`prompts/answer-onboarding-question.md`'s system prompt are resolved into the
running `retrieve_reason_respond` LangGraph workflow.
