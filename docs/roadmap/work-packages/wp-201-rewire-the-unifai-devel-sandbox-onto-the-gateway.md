# WP-201: Rewire the unifai-devel sandbox onto the gateway (amended: retire it, one instance)

- **State:** Repo work merged (2026-11-05: unifai-devel and unifai-olm retired; tool and schedule examples live)
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md)
- **Depends on:** WP-198
- **Related:** [ADR-0562](../../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md)
- **Target:** v0.13
- **Estimated files touched:** ~4 in the fork's examples

> Why: on `unifai-devel` the operator examples (demo-* LLMs and workflows, Gemini templates) are owned by `admin`, so no
> persona sees them. Two of the LLMs need an external key. User decision of 2026-11-04: keep it as a sandbox, rewired onto
> zuno-gateway and owned by ai-ops-01, with the zuno templates.

## Goal

ai-ops-01 on `unifai-ui-unifai-devel` sees the examples, and they run without any external API key (mock LLM).

## Steps

1. **Confirm the identity.** Done on 2026-11-04: the live stack is on realm `zuno` with `adminUsers: [ai-ops-01]` and
   reads groups through oidc-claims. The 25 `demo-*` objects were owned by `admin`, the CRD default, which no realm user
   is.
2. **Variant A, chosen by the user on 2026-11-04.** The gateway variant would have needed the ai-gateway and mcp-gateway
   NetworkPolicies opened to `unifai-devel`; they only admit `zuno-unifai`. The fork gets a kustomize overlay,
   `examples/overlays/unifai-devel-demo333`, sent as a patch to the fork session:
   - every object gets `owner: ai-ops-01`;
   - it drops `demo-gemini`, `demo-openai`, `demo-vllm` and `demo-docs-wide`;
   - the two templates run on the mock LLM and the demo MCP server, with no placeholders;
   - `stack-unifai-devel.yaml` is refreshed to the live identity.

   The generic examples, used by the e2e tests, are left unchanged.
3. **Re-apply on demo333.** Delete the `admin`-owned objects, then
   `oc kustomize --load-restrictor LoadRestrictionsNone examples/overlays/unifai-devel-demo333 | oc apply -n unifai-devel -f -`.
   This is a cluster action and needs the user's go.

## Live record (2026-11-04, user go)

- **Delete.** The 25 `admin`-owned objects were saved, then deleted. Two `UnifaiTemplate` deletions wedged on a 403: the
  operator deletes as `spec.owner`, and `admin` is no longer a UnifAI admin, so the status read "cannot delete (still
  referenced?)". Patching `spec.owner` to ai-ops-01 let them go. The fork keeps the "act as the owner" model and only
  improves the message.
- **Apply.** The 21 overlay objects are owned by ai-ops-01 and are Ready (`demo-weekday-morning` is Suspended by its
  spec).
- **SSRF guard.** `demo-chat-smoke` first failed: the multiagent outbound guard refuses hosts that resolve to private
  addresses, here `unifai-demo-mcp`. The stack's `extraEnv.multiagent` and `extraEnv.multiagentWorker` now carry
  `OUTBOUND_ALLOWED_HOSTS=unifai-demo-mcp,unifai-demo-llm`, also sent to the fork's `stack-unifai-devel.yaml`.
- **Result.** `demo-chat-smoke` (workflow `demo-linear`) completed with "pong from the demo mock LLM".

## Acceptance

- As ai-ops-01 on `unifai-ui-unifai-devel`, the examples are listed and one workflow answers.

## Amendment: one UnifAI instance (user decision of 2026-11-05)

demo333 keeps only `zuno-unifai` (ADR-0598 point 6). The sandbox of the steps above was rewired and checked, then
retired.

1. **Peers.** b9, a9 and da confirmed on 2026-11-05 that nothing of theirs uses `unifai-devel` or `unifai-olm`. The fork
   canary and e2e tests already create and delete their own namespaces.
2. **What stays.** The OLM operator, which reconciles `zuno-unifai`: namespace `unifai-operator`, Subscription
   `unifai-operator`, CatalogSource `openshift-marketplace/unifai-operator-catalog`. The Keycloak of realm `zuno` has its
   own `rhbk-operator` Subscription in `zuno-auth`; the one in `unifai-olm` goes with that namespace.
3. **Migration.** The chart's team examples gain the kinds that only the sandbox showed: a `<team>-web-fetch` tool, and a
   suspended `<team>-weekday-brief` schedule. A `<team>-welcome` chat was tried and dropped: the chat completed, but its
   result was the gateway's refusal "no identity binding for session …: it was not submitted by a signed-in user". An
   operator-submitted chat has no user token. The mock LLM, the demo MCP server and the
   `demo-*` objects are not migrated; the team examples replace them. The fork keeps the overlay and the stack example
   as references.
4. **Retirement** (cluster actions, each with the user's go). For each of `unifai-devel` and `unifai-olm`: delete the
   UnifaiStack and wait until it is gone, while the operator still runs so its finalizers clean up. Then delete the
   namespace.
5. **Done on 2026-11-05** (user go). The install created the tools, schedules and personal RAG starters (d0/d1
   Synced/Healthy). `unifai-devel` and `unifai-olm` were deleted, stack first, then the namespace. The operator lets the
   finalizers go once the namespace is being deleted. `zuno-unifai`, the OLM operator and `zuno-auth` are untouched.
