# WP-071: Align Authorino TLS trust with Kuadrant gateway service CA

- **State:** Done (2026-08-24) - root cause confirmed and fixed live on both
  consumer gateways. The original diagnosis held for `maas-default-gateway`:
  the Kuadrant-generated `kuadrant-auth-service` Envoy cluster trusted
  `/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt`, while the
  Zuno-managed Authorino listener served a certificate issued by
  `vault-issuer-istio`. Fixed by annotating the operator-owned
  `authorino-authorino-authorization` Service with
  `service.beta.openshift.io/serving-cert-secret-name: authorino-server-cert`
  and repointing Authorino's `listener.tls.certSecretRef` at the resulting
  Service-CA-issued Secret. **A second, distinct bug was found live on
  `zuno-agent-gateway` (WP-54's gateway) while validating this fix:**
  Kuadrant's own generated `EnvoyFilter` never adds TLS to the
  `kuadrant-auth-service` cluster it creates, for any gateway - confirmed
  byte-identical on both. `maas-default-gateway` only worked because RHOAI's
  `odh-model-controller` separately owns a second `EnvoyFilter`
  (`maas-default-gateway-authn-ssl`, not in this repo) that independently
  `ADD`s a TLS-wrapped version of the same cluster at `priority: -1`.
  `zuno-agent-gateway` has no such controller, so a new, hand-authored
  `EnvoyFilter` (`templates/quota-demo-gateway-authn-ssl.yaml`) mirrors that
  exact pattern. Both fixes live-tested repeatedly and confirmed on the
  cluster before being committed: `401`, not `500`, zero
  `CERTIFICATE_VERIFY_FAILED`, `cx_connect_fail` delta `0`, Authorino's own
  log shows the request arriving, on both `maas-default-gateway` and
  `zuno-agent-gateway`. See ADR-0201/ADR-0511's 2026-08-24 implementation
  notes for the full evidence trail, including two dead ends ruled out live:
  `Kuadrant.spec.mtls` (requires `kuadrant-system` to be mesh-onboarded with
  sidecar injection, which it isn't - tested and rolled back cleanly) and an
  ArgoCD-self-heal false negative (a live-only CR edit got reverted
  mid-test, briefly making the fix look broken).
- **ADRs:** ADR-0201, ADR-0511
- **Depends on:** WP-27 (MaaS governance integration), WP-54 (Kuadrant quota
  enforcement), Red Hat Connectivity Link / Kuadrant operand installed and
  Authorino TLS listener enabled.
- **Unblocks:** completion of WP-27 and WP-54 authenticated/governed request
  paths.
- **Estimated files touched:** ~7 (actual: 14 — the brief's own "Update
  roadmap state" step and "Status updates" section touch both WP-27's and
  WP-54's tracker rows *and* brief files, plus both ADRs, more than the
  headline estimate; a second, distinct `EnvoyFilter` fix for
  `zuno-agent-gateway`, found live while validating this WP, added two more)

> Execute this brief as a standalone task from the repository root. Read
> ADR-0201 and ADR-0511 before editing. Preserve operator-owned resources and
> use additive/GitOps-managed configuration only. If the live RHCL-generated
> Envoy cluster no longer trusts OpenShift `service-ca.crt`, stop and report
> before implementing this WP because the premise has changed.

## Goal

Make the Authorino gRPC listener certificate verifiable by the
Kuadrant-generated Envoy `kuadrant-auth-service` cluster, restoring the
Gateway -> wasm-shim -> Authorino ext_authz path for both:

1. RHOAI Models-as-a-Service through `maas-default-gateway`; and
2. Zuno quota enforcement through `zuno-agent-gateway`.

Use an OpenShift service-serving certificate issued by the Service CA Operator
for `authorino-authorino-authorization.kuadrant-system.svc`, rather than a
cert-manager certificate issued by `vault-issuer-istio`.

The target runtime flow is:

```text
OpenShift Service CA
        |
        v
authorino-server-cert Secret
        |
        v
Authorino :50051
        |
        | certificate chains to service-ca.crt
        v
Kuadrant Envoy kuadrant-auth-service
        |
        v
kuadrant-wasm-shim -> ext_authz Check -> Authorino
```

## Root-cause evidence

The 2026-08-24 live-cluster diagnostic established all of the following:

- `kuadrant-auth-service` exists in the live Envoy config.
- Its endpoint resolves to Authorino port `50051`.
- EDS reports the endpoint `HEALTHY`.
- The cluster has `http2_protocol_options: {}`.
- The cluster has an `envoy.transport_sockets.tls` transport socket.
- Its trusted CA is
  `/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt`.
- A request increments `cx_total`, `cx_connect_fail`, and `rq_error`, while
  `rq_total` remains zero.
- Envoy logs show:
  `X509_verify_cert: certificate verification error at depth 0: unable to get
  local issuer certificate` followed by
  `OPENSSL_internal:CERTIFICATE_VERIFY_FAILED`.
- The wasm call is dispatched successfully before that TLS failure.
- Authorino receives no gRPC `Authorization/Check` request.
- The Authorino listener certificate currently chains to the Zuno
  `vault-issuer-istio` PKI, not the OpenShift Service CA.

Therefore the current failure boundary is TLS trust between Envoy and
Authorino, not wasm-shim request serialization, Authorino policy evaluation,
JWT validation, Limitador, or the existence of the Envoy cluster.

## ADR references

### ADR-0201

Update the MaaS governance integration diagnosis:

- replace the previous probable `wasm-shim` binary/protobuf fault conclusion
  with the confirmed Authorino TLS trust mismatch;
- record that the EPP port-9002 issue remains separately fixed;
- retain the distinct RHOAI payload-processing filter-anchor integration gap;
- mark authenticated MaaS consumption as pending this WP rather than pending an
  upstream wasm-shim fix.

### ADR-0511

Update the quota-enforcement diagnosis:

- replace the previous upstream wasm-shim blocker with this locally correctable
  TLS trust mismatch;
- retain the generated `RateLimitPolicy` design and Limitador compilation flow;
- after TLS is restored, continue validation of identity propagation and the
  RHOAI/RHCL 1.4 rate-limit identity behavior separately.

## Preconditions

Before editing:

1. Confirm current live Envoy behavior:

   ```bash
   NS=openshift-ingress
   GW=maas-default-gateway
   POD=$(oc get pod -n "${NS}"      -l gateway.networking.k8s.io/gateway-name="${GW}"      -o jsonpath='{.items[0].metadata.name}')

   oc exec -n "${NS}" "${POD}" -c istio-proxy --      pilot-agent request GET '/config_dump'    | jq '.. | objects | select(.name? == "kuadrant-auth-service")'
   ```

   The result must still contain:

   ```yaml
   http2_protocol_options: {}
   transport_socket:
     name: envoy.transport_sockets.tls
     typed_config:
       common_tls_context:
         validation_context:
           trusted_ca:
             filename: /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt
   ```

2. Confirm the Authorino authorization Service exists:

   ```bash
   oc get svc -n kuadrant-system authorino-authorino-authorization
   ```

3. Confirm the Authorino CR currently has TLS enabled:

   ```bash
   oc get authorino authorino -n kuadrant-system      -o jsonpath='{.spec.listener.tls.enabled}{" "}{.spec.listener.tls.certSecretRef.name}{"\n"}'
   ```

4. Confirm `python3 platform/docs/check_docs.py` passes before changes.

5. Confirm `git status` is clean for:
   `gitops/charts/connectivity-link/`, `ansible/roles/connectivity_link/`,
   `docs/adr/`, and `docs/roadmap/`.

## Repo changes (step by step)

1. **Replace `templates/certificate.yaml`'s cert-manager `Certificate`
   responsibility with Service CA bootstrap.**

   Stop rendering the current `cert-manager.io/v1 Certificate`
   `authorino-server-tls` issued by `vault-issuer-istio`.

   Replace it with a GitOps-managed mechanism that annotates the
   operator-created Service:

   ```yaml
   metadata:
     annotations:
       service.beta.openshift.io/serving-cert-secret-name: authorino-server-cert
   ```

   The implementation must preserve operator ownership of the Service. Do not
   replace the whole Service object with a second conflicting manifest if
   server-side ownership proves unsafe. Prefer the repository's established
   patch/post-render/Ansible pattern for modifying operator-created objects if
   that is already used elsewhere.

2. **Change the Authorino listener secret.**

   In `gitops/charts/connectivity-link/templates/authorino.yaml`, keep the
   existing narrow patch of `spec.listener.tls`, but point it at the
   Service-CA-generated secret:

   ```yaml
   spec:
     listener:
       tls:
         enabled: true
         certSecretRef:
           name: authorino-server-cert
   ```

   Keep the current design where the rest of the operator-owned Authorino spec
   is left untouched.

3. **Simplify `values.yaml`.**

   Replace the cert-manager-specific Authorino TLS values:

   ```yaml
   certSecretName: authorino-server-tls
   dnsNames: ...
   ```

   with the service-serving certificate secret name, for example:

   ```yaml
   kuadrant:
     authorinoTls:
       enabled: false
       certSecretName: authorino-server-cert
   ```

   Remove `dnsNames` if nothing else uses them. The Service CA Operator derives
   the service DNS names itself.

4. **Correct chart documentation/comments.**

   Update:

   - `gitops/charts/connectivity-link/README.md`;
   - comments in `templates/authorino.yaml`;
   - comments in the former `templates/certificate.yaml` or its replacement;
   - comments in `values.yaml`.

   Remove the incorrect statement that Kuadrant gateway ext_authz callers
   natively trust the `vault-issuer-istio` root. Document the live fact that
   RHCL's generated `kuadrant-auth-service` cluster trusts OpenShift
   `service-ca.crt`.

5. **Add a Day-1 regression check.**

   Extend the Connectivity Link check path (or the closest existing Day-1
   diagnostic task if this role has no dedicated `check.yml`) with:

   - Authorino TLS enabled;
   - `certSecretRef.name == authorino-server-cert`;
   - generated Secret exists and contains `tls.crt` / `tls.key`;
   - Authorino certificate verifies against the Service CA;
   - `kuadrant-auth-service` is present in the MaaS Gateway live Envoy config;
   - its endpoint is healthy;
   - a protected request does not increment `cx_connect_fail`.

   Do not make the check depend on a valid user token merely to prove TLS. A
   `401` or `403` produced by Authorino is sufficient to prove the ext_authz
   transport path; HTTP 500 from TLS failure is not.

6. **Update ADR-0201 and ADR-0511.**

   Record the evidence and replace the upstream-wasm blocker language with:

   > The Kuadrant wasm-shim dispatch succeeds. Envoy then fails TLS
   > verification of the Authorino listener because the generated
   > `kuadrant-auth-service` cluster trusts OpenShift `service-ca.crt`, while
   > Zuno configured Authorino with a certificate issued by
   > `vault-issuer-istio`. Envoy reports `CERTIFICATE_VERIFY_FAILED`, surfaces
   > gRPC status 14 to the wasm-shim, and returns HTTP 500 before Authorino
   > receives an ext_authz request.

7. **Update roadmap state.**

   Add WP-071 to `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`, linked to
   WP-27 and WP-54. Those WPs must no longer claim that no repository-side fix
   exists; they should be marked blocked by WP-071 until its live acceptance
   checks pass.

## What NOT to touch

- Do not edit the RHCL/Kuadrant-generated `EnvoyFilter` by hand.
- Do not replace `service-ca.crt` in the generated Envoy cluster with a custom
  Vault CA as the primary fix.
- Do not disable TLS verification or use `ACCEPT_UNTRUSTED`.
- Do not set Kuadrant/Envoy `failureMode: allow` to hide the transport failure.
- Do not disable Authorino TLS; RHOAI MaaS requires
  `spec.listener.tls.enabled`.
- Do not modify Authorino authentication/JWT rules as part of this WP.
- Do not change RateLimitPolicy semantics or quota values.
- Do not change Limitador.
- Do not treat RHOAIENG-76586 identity propagation as part of this transport
  fix; validate it after ext_authz transport works.
- Do not alter the separately documented RHOAI payload-processing filter-anchor
  issue in ADR-0201.

## Acceptance checks

All of the following must pass on the live cluster.

### A. Service-serving certificate exists

```bash
oc get secret -n kuadrant-system authorino-server-cert
```

The Secret contains `tls.crt` and `tls.key`.

### B. Authorino uses the Service CA certificate

```bash
oc get authorino authorino -n kuadrant-system   -o jsonpath='{.spec.listener.tls.certSecretRef.name}{"\n"}'
```

Expected:

```text
authorino-server-cert
```

### C. Certificate verifies against the exact CA used by Envoy

```bash
NS=openshift-ingress
POD=$(oc get pod -n "${NS}"   -l gateway.networking.k8s.io/gateway-name=maas-default-gateway   -o jsonpath='{.items[0].metadata.name}')

oc get secret authorino-server-cert -n kuadrant-system   -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/authorino-service-ca.crt

oc exec -n "${NS}" "${POD}" -c istio-proxy --   cat /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt   > /tmp/service-ca.crt

openssl verify   -CAfile /tmp/service-ca.crt   /tmp/authorino-service-ca.crt
```

Expected:

```text
/tmp/authorino-service-ca.crt: OK
```

### D. Envoy no longer fails the Authorino connection

Capture `/clusters?format=json` before and after one protected request.

Required result:

```text
delta.cx_connect_fail == 0
delta.rq_total >= 1
```

A successful auth should additionally produce `rq_success >= 1`.

### E. MaaS no longer returns the TLS-derived HTTP 500

From outside the cluster:

```bash
curl -vk   -H "Authorization: Bearer ${MAAS_API_KEY}"   "https://$(oc get route maas-gateway-route -n openshift-ingress     -o jsonpath='{.spec.host}')/v1/models"
```

Pass condition for this WP:

- `200`, `401`, `403`, or `429` depending on the supplied credential/policy;
- **not** HTTP `500` caused by `kuadrant-wasm-shim` gRPC status 14;
- Envoy logs contain no `CERTIFICATE_VERIFY_FAILED` for
  `kuadrant-auth-service`.

### F. Authorino receives ext_authz traffic

During the protected request, Authorino logs or metrics must show that the
request reached Authorino. An intentionally invalid/expired token producing an
Authorino denial is an acceptable transport-level proof.

### G. Zuno quota demo path also clears TLS

Repeat the equivalent protected request through `zuno-agent-gateway`.
The same Authorino certificate is shared by both gateways, so neither path may
increment `cx_connect_fail`.

### H. Repository checks

```bash
python3 platform/docs/check_docs.py
make day1 check connectivity-link
```

If `make day1 check connectivity-link` is not currently a supported component,
use the existing closest Day-1 connectivity/OpenShift-AI check target and
document the exact command selected rather than adding an unrelated Makefile
surface solely for this WP.

## Operator / human follow-up

1. Deploy the GitOps change.
2. Confirm ArgoCD remains Synced/Healthy and does not fight the
   operator-created Authorino Service.
3. Confirm Service CA rotation ownership by checking the Secret annotations and
   Service annotation.
4. Run one request through `maas-default-gateway`.
5. Run one request through `zuno-agent-gateway`.
6. Capture:
   - Envoy `kuadrant-auth-service` counters before/after;
   - HTTP response code;
   - Authorino log/metric proof;
   - absence of `CERTIFICATE_VERIFY_FAILED`.
7. Once transport is healthy, continue WP-27/WP-54 validation:
   MaaS subscription/auth, identity propagation, Limitador counters, and
   expected `429` behavior.

## Status updates

On repository merge but before live confirmation:

- WP-071 -> `Operator pending`;
- ADR-0201 -> `Partially implemented - Authorino Service CA trust fix merged;
  live MaaS ext_authz verification pending (WP-071)`;
- ADR-0511 -> `Partially implemented - Authorino Service CA trust fix merged;
  live quota-path ext_authz verification pending (WP-071)`;
- WP-27 / WP-54 -> blocked by WP-071 live validation, not by an assumed
  upstream wasm-shim defect.

After all live acceptance checks pass:

- WP-071 -> `Done`;
- remove the TLS blocker from WP-27 and WP-54;
- resume their remaining functional acceptance checks;
- update `docs/adr/README.md`,
  `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`, and `MEMORY.md`;
- run `python3 platform/docs/check_docs.py` again.

## Rollback

If the Service CA change causes a regression:

1. revert the Git commit;
2. let ArgoCD restore the previous Authorino TLS configuration;
3. do not patch the generated EnvoyFilter or weaken TLS verification as a
   rollback mechanism.

The previous configuration is known to return HTTP 500 for Kuadrant-protected
traffic, so rollback restores the previous broken state only; it is not an
operational workaround.

## Out of scope / deferred

- RHOAIENG-76586 / RHCL 1.4 identity propagation behavior after successful
  authentication.
- MaaS subscription semantics and token quota tuning.
- Limitador rate-limit values.
- RHOAI payload-processing `EnvoyFilter` subfilter-anchor mismatch documented
  separately in ADR-0201.
- Any upstream RHCL/Kuadrant issue that may later change how the generated Envoy
  cluster supplies its trusted CA.
