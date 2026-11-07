# Rehearsing in a canary namespace

[ADR-0609](../adr/0609-rehearse-on-canary-namespaces-of-demo333.md). demo333 is the only cluster, so a change is
rehearsed in a canary namespace of its own before it reaches the live stack. What a namespace cannot hold is written in
the work package as "not rehearsed" and follows [the pre-GA upgrade routine](pre-ga-upgrade.md): backup, recorded
rollback, a window outside any freeze, and a golden-path run afterwards.

## Create and remove

```bash
ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/canary_namespace.yml -e canary_wp=WP-211
ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/canary_namespace.yml -e canary_wp=WP-211 -e canary_state=absent
```

The namespace is `zuno-canary-<wp>`, with these labels: `zuno.io/canary=true`, `zuno.io/work-package=<WP>`, restricted
pod security. It also gets:
- a ResourceQuota: 4 CPU, 8 Gi requested, 20 pods, no GPU unless `canary_gpus` is set;
- a default-deny NetworkPolicy: ingress from the namespace itself; egress to DNS and the namespace only, plus what
  `canary_egress` lists, as verbatim NetworkPolicy egress rules.

It is outside the mesh. Creating or removing one is a cluster change: it needs the owner's go, and never happens
inside a freeze. A canary namespace left over after its work package is closed is a finding of `make d3 check drift`.

## What can be rehearsed in a canary

- An experience client or another namespace-scoped component, as a second instance with its own Keycloak client.
- The namespace-scoped part of a UnifAI release (stack images), where the operator allows a second stack.
- The firewall and egress rules of one namespace: apply them to the canary first, and exercise every restart path
  (image pulls, model downloads, the external APIs the component calls).
- ADR-0352's external mode: a second Keycloak, PostgreSQL or Redis in the canary namespace plays the "external"
  service. The component is pointed at it and back again (WP-211, WP-213, WP-214).

## What cannot, and how it is handled instead

| Change | Why not in a canary | Instead |
|---|---|---|
| An operator or CRD upgrade | cluster-scoped, one version per cluster | [pre-GA upgrade routine](pre-ga-upgrade.md) |
| Vault (raft, unseal, policies) | one instance serves every namespace | backup and snapshot, a window, a golden-path run |
| Mesh-wide settings (mTLS mode of the control plane, Istio CR) | one control plane | namespace by namespace, PERMISSIVE then STRICT |
| ArgoCD and its AppProjects | one instance owns every Application | a dry run with `argocd app diff`, a window |
| GPU node pools, MachineSets, MIG profiles | cluster infrastructure | the owner's go, a window, the golden path |

The `hardened` profile (WP-227) is rehearsed in a canary for its namespace-scoped switches. Its cluster-scoped switches
are verified by its `make check` only, and demo333 stays on the `demo` profile.

## Recording a rehearsal

In the work package's brief, record:
- the canary namespace;
- what was rehearsed, and the result;
- what was not rehearsed, and why;
- the removal of the namespace.
