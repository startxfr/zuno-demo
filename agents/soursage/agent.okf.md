---
okf_version: v0.2
type: agent
title: Soursage
description: >-
  Recruiting assistant. Interacts with Workday and LinkedIn to source new
  consultant candidates and to find, among existing consultants, the best
  profile for a mission.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-15"
sources: []
zuno:
  name: soursage
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending a future build (ADR-0349 defines only the
      identity footprint); C2 anticipated because candidate/consultant
      profile data requires context filtering rather than unrestricted
      SaaS use.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `recrut` and
    # `sales` business roles that will govern tool/data permissions
    # inside Soursage (ADR-0349 §6 - future tools gate on those roles
    # and on the ADR-0340 Workday capability scopes,
    # workday.profile.any.read, read-only).
    groups:
      - agent_soursage
  ui:
    displayName: Soursage
    tileDescription: Consultant sourcing and staffing assistant - coming soon.
    color: "#00695C"
    icon: users
---

# Soursage

ADR-0349 §6: `status` is `placeholder` - this bundle, the
`soursage-frontend` Keycloak client, the `agent_soursage` entitlement
group and this portal tile are the only things that exist for Soursage
today (the original placeholder pattern comage/advantage/finage/arkos
each started from). No dedicated namespace is reserved (ADR-0329): a
future active Soursage deployment would run in the shared `zuno-ai-run`
namespace, CR-managed via the AIAgent operator (ADR-0327/ADR-0308) like
every agent onboarded since WP-38.

`tasks/coming-soon.md` describes the intended build - sourcing new
consultant candidates and matching existing consultants to missions via
Workday (`workday.profile.any.read`, the read-only ADR-0340 scoped
capability WP-32 already registered) and a future LinkedIn capability -
kept here so onboarding Soursage later is primarily a `status: active`
flip plus real task implementation through the ADR-0307 template
workflow (`platform/templates/agent/`), not a redesign.
