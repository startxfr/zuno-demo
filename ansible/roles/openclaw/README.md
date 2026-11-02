# openclaw

Day 2 component `openclaw`: one OpenClaw personal assistant per demo persona
(ADR-0589, ADR-0590, under ADR-0587's admission contract). WP-182's evidence
(`docs/roadmap/evidence/wp-182-openclaw-spike.md`) explains every value.

- **Chart** `gitops/charts/openclaw`, two Applications: `zuno-openclaw-d0` (the
  claw-operator catalog pinned by digest; per persona the namespace with
  `zuno.io/experience-client`, an OwnNamespace operator with a Manual Subscription,
  and an EgressFirewall letting only Keycloak and the Kubernetes API out) and `zuno-openclaw-d1` (per
  persona the ExternalSecrets, the oauth2-proxy front door and the `Claw`).
- **Personas, pins and names** live in the chart's `values.yaml`; the role reads them.
- **install**: Vault paths (fails if `keycloak/openclaw-<persona>` is missing; seeds
  `openclaw/<persona>` if missing), d0, approval of the InstallPlan naming the pinned
  CSV only, d1, wait for each `Claw` Ready.
- **check**: Applications Synced and Healthy; per persona the CSV, the `Claw`, the
  running image IDs against the pins, the front-door Route admitted and the operator's
  rejected, a 302 to Keycloak without a session, and from the assistant's pod: 200
  from the ai-gateway through the proxy, nothing when the proxy is bypassed, nothing
  from clawhub.ai or the internet.
- **uninstall**: d1 then d0. The CRDs and the Vault paths stay.

**Upgrading the operator or OpenClaw** is a deliberate pin change, made by
`python3 platform/supply-chain/pin_claw_catalog.py` (`--dry-run` first; `--catalog sha256:...` and
`--openclaw <tag>` to choose). It resolves the newest catalog, reads its single bundle in memory, resolves the
manager and proxy digests and the newest stable OpenClaw tag, and rewrites `operator.catalogImage`,
`operator.startingCSV`, `operator.pinnedImageDigests`, `images.openclaw` and the chart's `appVersion` together.
When it reports a new CSV, re-read the operator source at the bundle's commit (passthrough domains, owned config
keys, Route) before installing. Then push and run `make d2 install openclaw` (the role approves only the
InstallPlan naming the new CSV) and `make d2 check openclaw`.
