---
okf_version: v0.2
type: agent
title: OpenShift Lightspeed
description: >-
  The OpenShift console's native assistant, consuming the Zuno platform as a
  client (ADR-0524). Not a Zuno agent in the product sense - it has no Zuno
  frontend, no BFF and no Agent Runtime workflow. This bundle exists solely to
  give Lightspeed a policy identity, so its calls through the MCP Gateway's
  /mcp front-door are authorized by exactly the same ADR-0011 five-factor
  intersection every other caller goes through.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-26"
sources: []
zuno:
  name: lightspeed
  # Declaration-only, like agents/cognos and agents/soursage: no gitops chart,
  # no Application, and deliberately absent from ansible/roles/agents'
  # deploy list. Nothing here creates a workload.
  status: external-client
  tasks:
    - answer-openshift-question
  model:
    preferred_classification: C2
    notes: >-
      Lightspeed does its own inference against the MaaS-published local model
      (ADR-0524 clause 1) and never routes prompts through the Agent Runtime,
      so this is a declaration of the data sensitivity it may handle, not a
      routing instruction. C2 matches the `confluence` domain in
      policies/data-classification/classification.yaml - the only content this
      bundle can reach.
  access:
    # ADR-0040 entitlement group. Distinct from `lightspeed_readonly`, the
    # BUSINESS-role group in policies/tools/tool-policy.yaml that actually
    # grants the two read capabilities - entitlement and authorization stay
    # orthogonal here exactly as they do for every other agent.
    groups:
      - agent_lightspeed
  ui:
    displayName: OpenShift Lightspeed
    tileDescription: OpenShift console assistant - not a Zuno-hosted agent.
    color: "#EE0000"
    icon: openshift
---

# OpenShift Lightspeed

ADR-0524 integrates OpenShift Lightspeed as a **consumer** of this platform:
Red Hat's operator owns the user experience, the official OpenShift
documentation corpus (RHOKP) and live cluster introspection, while Zuno
supplies local inference through MaaS and internal Confluence knowledge
through the existing MCP Gateway.

## Why this bundle exists

`components/mcp-gateway/app/policy.py`'s `evaluate()` fails closed on a caller
that declares no agent and no task - "missing X-Zuno-Agent/X-Zuno-Task
declaration" - and then requires that agent to declare the requested tool in
the named task. That is ADR-0011's first two factors, and ADR-0036 made them
enforced rather than aspirational.

Lightspeed therefore needs a real OKF declaration, or the `/mcp` front-door
would have to bypass those two factors for it. Bypassing them would mean a
second authorization path through the gateway, which is precisely what
ADR-0036 exists to prevent. A declaration-only bundle is the cheaper and
stricter answer: no new code path, no weakened invariant, and the tool surface
Lightspeed can reach is auditable in one file alongside every other caller's.

## What it is not

`status: external-client` (not `placeholder`, not `active`): unlike
`agents/cognos`, this bundle is not waiting to be promoted into a running Zuno
agent. There is no future WP that gives it a frontend, a BFF or an Agent
Runtime workflow - the workload that consumes this identity is the
Red Hat-operated Lightspeed deployment in `openshift-lightspeed`. Do not add
it to `ansible/roles/agents/tasks/install.yml`'s deploy list.
