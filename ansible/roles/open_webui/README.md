# open_webui

Day 2 component `open-webui`: Open WebUI, the general-purpose chat experience
over the governed chain (ADR-0588, under ADR-0587's admission contract).
Values and traps come from the WP-180 spike
(`docs/roadmap/evidence/wp-180-open-webui-spike.md`).

| Verb | What it does |
|---|---|
| `make d2 install open-webui` | Seeds the missing Vault paths (`keycloak/open-webui`, `open-webui/app`), creates the Keycloak group `openwebui_admin` and its members live (create-only), applies `zuno-open-webui-d1` with the cluster values, waits for the Deployment. |
| `make d2 check open-webui` | Application Synced and Healthy; from the pod: Keycloak discovery 200 (through the EgressFirewall), ai-gateway and mcp-gateway 401 without a token (reached), internet unreachable; Route `/health` 200. |
| `make d2 uninstall open-webui` | Deletes the Application (Deployment, Route, PVC, Secrets). The Keycloak client and group and the Vault paths stay. |

The Keycloak client `open-webui` is declared in `gitops/charts/keycloak/files/realm-zuno.json`
and created by the client-reconcile Job (ADR-0530). The group `openwebui_admin` is declared there
too, but groups and users are create-only on a live realm, so this role creates them. Its members
are `open_webui_admin_users` (defaults), kept in step with the realm file.

Keycloak is reached by its public https issuer (the gateways accept no other). Egress: the
NetworkPolicy admits DNS, the two gateways and HTTPS out of the cluster networks; the OVN
EgressFirewall narrows "out of the cluster" to Keycloak's DNS name. The in-cluster router cannot
be used instead: on AWS it expects the PROXY protocol the external load balancer adds.
