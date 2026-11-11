# WP-243: each browser check fails when its experience is unavailable (2026-11-11)

The negative case left open by [WP-243](../work-packages/wp-243-browser-tests-for-every-experience.md): each browser check
must fail when its experience cannot be reached. It was run on demo333 with the user's go, by session zuno-avancement,
from 20:51 to 20:57 UTC. zuno-demo held its golden-path and browser runs during the window.

## Method: block, not scale

The acceptance says "scaled to zero". That does not hold on demo333:
- every experience's Application has ArgoCD `selfHeal: true`;
- UnifAI and the OpenClaw assistants are reconciled by their operators.

Any of these would restore the replicas, possibly before the check runs, and the check would then pass for the wrong
reason. A plain NetworkPolicy cannot block the experience either: NetworkPolicies only allow, so a deny-all policy adds
nothing to the existing allows (the router's ingress included).

Instead, each experience was made unreachable with a temporary `AdminNetworkPolicy` (`policy.networking.k8s.io/v1alpha1`,
priority 90, action `Deny` from every namespace). It applied to the pods behind the experience's Route, found through the
Route's Service selector. An ANP `Deny` takes precedence over every NetworkPolicy. The router pods are not host-network,
so the rule applies to them. Each cycle created the ANP, ran the check, deleted the ANP (always, through a shell trap)
and ran the check again.

## Result

| Experience | Pods blocked (namespace, selector) | Blocked | Open again |
|---|---|---|---|
| kagent | zuno-kagent, `app=kagent-front-door` | FAIL (50.5 s, `waitForSelector` timeout) | PASS (3.4 s, signed in as ai-ops-01, agent `zuno-sre` listed) |
| Open WebUI | zuno-openwebui, `app.kubernetes.io/component=open-webui` | FAIL (50.4 s, timeout) | PASS (5.8 s, sale-01, the chat input on screen) |
| Dify | zuno-dify, `app=dify-front-door` | FAIL (50.5 s, timeout) | PASS (4.1 s, through the front door as consultant-02) |
| OpenClaw (sale-01) | zuno-claw-sale-01, `app=claw, instance=assistant` | FAIL (31.6 s, `page.click` timeout) | PASS (11.8 s, Control UI connected to its gateway) |
| UnifAI | zuno-unifai, `app.kubernetes.io/name=ui` | FAIL (50.4 s, `locator.click` timeout) | PASS (6.0 s, consultant-02, 10742 chars) |

No AdminNetworkPolicy remained afterwards (`oc get adminnetworkpolicy`: none). Each experience was unreachable for about
one minute.
