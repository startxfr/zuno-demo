# Supply chain architecture

Last reviewed: 2026-11-19

What runs on Zuno is signed, the signer is named, and the cluster checks the signature before a pod starts. Four
mechanisms carry this: Red Hat Trusted Artifact Signer (RHTAS) signs the images built in the cluster; a release
ledger records every named release; an internal Red Hat Quay serves the images, so most pod starts do not depend on a
public registry; and the Sigstore policy controller refuses an unsigned or wrongly signed image in the namespaces that
opted in. This page is the map; the demonstration is the scenario
[Supply chain: signed images, admission policy and the internal Quay](../demo/scenarios/foundation/image-signing-admission.md),
and the agents release chain is in
[OKF agents release](../demo/scenarios/foundation/okf-signed-agent-release.md).

## HLD: where it sits

The highlighted box is the trust group "RHTAS, Quay, image policy". Plain arrows carry requests, dotted arrows carry
identity, policy or telemetry.

```mermaid
flowchart TB
  subgraph EXP["Experiences: clients of one governed backend"]
    UNIFAI["UnifAI<br/>agents, RAG"]
    OWUI["Open WebUI"]
    CLAW["OpenClaw<br/>one assistant per persona"]
    DIFY["Dify"]
    KAGENT["kagent"]
    LS["OpenShift Lightspeed"]
    BLENDER["Blender add-on"]
    WM["World model"]
  end
  subgraph GOV["Gateways and governance"]
    TP["token proxy,<br/>egress proxy"]
    RHCL["RHCL Kuadrant<br/>auth, rate limits"]
    AIGW["ai-gateway<br/>classification, routing,<br/>guardrails, quotas"]
    MCPGW["mcp-gateway<br/>tools by group"]
    A2A["a2a-gateway<br/>delegation, approval"]
  end
  subgraph AI["Red Hat OpenShift AI"]
    MAAS["MaaS<br/>gateway, portal, API keys"]
    KSERVE["KServe llm-d<br/>local models on MIG GPUs"]
    EXT["SaaS models<br/>Mistral, Codestral, OVHcloud"]
    PG["GenAI playground"]
    BUILD["Pipelines, MLflow,<br/>Kueue, model registry"]
    EVAL["TrustyAI, EvalHub,<br/>LMEval"]
  end
  subgraph TOOLS["Agents and tools"]
    OKF["OKF agents release<br/>zuno-demo-agents"]
    MCPS["MCP servers<br/>Confluence, Git, AAP,<br/>k8s, Google Workspace"]
  end
  subgraph TRUST["Identity, secrets, supply chain"]
    KC["Keycloak<br/>personas, groups"]
    VAULT["Vault, ESO,<br/>cert-manager"]
    SC["RHTAS, Quay,<br/>image policy"]
  end
  subgraph PLAT["Platform and operations"]
    OCP["OpenShift, Service Mesh,<br/>GPU nodes"]
    GITOPS["Argo CD GitOps,<br/>AAP Day 0-3"]
    OBS["Prometheus, Grafana,<br/>Tempo"]
  end
  SAAS[("SaaS<br/>Confluence, Google,<br/>Salesforce")]

  UNIFAI & OWUI & WM --> AIGW
  CLAW & DIFY & KAGENT --> TP --> AIGW
  BLENDER --> RHCL --> AIGW
  UNIFAI --> A2A
  UNIFAI & OWUI & TP & LS --> MCPGW
  LS & PG --> MAAS
  AIGW --> MAAS
  MAAS --> KSERVE
  AIGW --> EXT
  MAAS -. published .-> EXT
  MCPGW --> MCPS --> SAAS
  BUILD --> KSERVE
  EVAL --> MAAS
  RHCL -. limits .-> MAAS
  OKF -. agents, policies .-> UNIFAI & AIGW & MCPGW
  KC -. tokens .-> AIGW & MCPGW & MAAS
  AIGW & MCPGW -. metrics, traces .-> OBS

  classDef focus fill:#ffd54f,stroke:#d84315,stroke-width:4px,color:#000;
  class SC focus;
```

## LLD: signing, mirroring and admission

Three paths. **Build and sign**: each image a BuildConfig builds in `zuno-ai-build` is signed keyless by a Job that gets a
short-lived Fulcio certificate for the Keycloak service identity `zuno-signer`, and Rekor records the signature.
`make d3 release` rebuilds every component from a tag, signs and verifies it, then appends to the ledger
`platform/supply-chain/pinned-releases.yaml`. **Verify and mirror**: the UnifAI images are built and signed by CI of
the UnifAI fork, verified offline by digest, then copied with their signatures to Quay; node-level
ImageDigestMirrorSets read from Quay first and fall back to the public registry. **Admit**: the policy controller
webhook checks `ClusterImagePolicy` objects at pod creation, only in namespaces labelled `policy.rhtas.com/include=true`.

```mermaid
flowchart TB
  subgraph BUILD["namespace zuno-ai-build: what the cluster builds"]
    BC["BuildConfig<br/>component:latest, or component:tag<br/>for make d3 release"]
    IS[("OpenShift internal registry<br/>ImageStream zuno-ai-build")]
    SJ["Job image-signing-component<br/>supply-chain-signer image, cosign"]
    TKN["PipelineRun source-image-build<br/>third-party images from source, ADR-0620<br/>pushes quay.io/zuno by digest"]
    VJ["Job supply-chain-verify-images<br/>make d2 check supply-chain"]
    LED[("pinned-releases.yaml<br/>append-only ledger")]
    BC --> IS
    BC --> SJ
    SJ -->|"signature, sha256-digest.sig tag"| IS
    VJ -.->|"cosign verify each live digest"| IS
  end
  subgraph RHTAS["namespace zuno-rhtas: RHTAS"]
    FUL["Fulcio<br/>short-lived certificate"]
    REK["Rekor, CTLog, Trillian<br/>transparency log"]
    TUF["TUF<br/>trust root"]
  end
  KC["Keycloak client zuno-signer<br/>zuno-signer@zuno-demo.internal"]
  KC -.->|"service-account token"| SJ
  SJ --> FUL
  SJ --> REK
  SJ -.->|"make d3 release only"| LED
  subgraph GH["github.com/startxfr/UnifAI CI"]
    CI["publish-images.yml, release.yml,<br/>unifai-operator-release.yml<br/>keyless sign, provenance, SBOM"]
  end
  QIO[("quay.io/zuno/unifai-*")]
  CI --> QIO
  TKN -.-> QIO
  PIN["pin_unifai_images.py<br/>verify_unifai_images.py offline,<br/>admission preflight dry run"]
  QIO --> PIN
  PIN -->|"mirror_unifai_images.py<br/>copy by digest with .sig .att .sbom"| QUAY
  subgraph REG["namespace zuno-registry"]
    QUAY[("Red Hat Quay<br/>quay-quay-zuno-registry/zuno<br/>blobs in S3, PostgreSQL 15")]
  end
  IDMS["ImageDigestMirrorSets<br/>zuno-unifai-via-registry,<br/>zuno-public-via-registry,<br/>zuno-redhat-via-registry<br/>AllowContactingSource"]
  NODE["node CRI-O<br/>pulls quay.io/zuno/... by digest"]
  IDMS -.-> NODE
  NODE -->|"mirror first"| QUAY
  NODE -.->|"fallback"| QIO
  subgraph ADM["namespace policy-controller-operator"]
    WH{"webhook policy.rhtas.com<br/>label policy.rhtas.com/include=true<br/>failurePolicy Ignore, 10 s"}
    CIP1["ClusterImagePolicy zuno-first-party-images<br/>enforce, trust root rhtas-trust-root"]
    CIP2["ClusterImagePolicy zuno-unifai-images-repo x8<br/>enforce, public-sigstore-trust-root,<br/>signatures read from Quay"]
    WH --> CIP1
    WH --> CIP2
  end
  POD["pod create in zuno-unifai,<br/>unifai-operator, zuno-wp226-cip-test"]
  POD --> WH
  CIP1 -.-> FUL
  CIP1 -.-> REK
  CIP2 -.-> QUAY
  WH -->|"signed by a listed identity"| OK["admitted"]
  WH -->|"unsigned, wrong signer or tag"| NO["denied"]
  POD -.-> NODE
```

## Reading notes

- Trust is decided by digest and signer identity, never by the registry that serves the bytes (ADR-0612 clause 5).
- The webhook uses `failurePolicy: Ignore` in `gitops/charts/rhtas-config`, so a webhook outage does
  not block pods; the policies themselves are in `enforce`.
- Quay is one replica of each component, with blobs in an S3 bucket (`zuno-<cluster>-registry`) and its own PostgreSQL;
  it is on the pod-start path for images a node does not hold yet. Clair is limited to Red Hat sources (ADR-0612).
- First-party images (family b of ADR-0612) still come from the OpenShift internal registry; that migration has not
  started. Third-party images built from source (Praxis) go through Tekton to `quay.io/zuno` and are pinned by digest
  but not signed (ADR-0620, Accepted).
- Day-3 operations: `make d3 release supply-chain`, `make d2 check supply-chain`, `make d3 admit agents`, `make d3 backup quay-registry`.

## ADRs

| ADR | Status | Role here |
|---|---|---|
| [0535](../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md) | Implemented (qualified) | RHTAS signs images built in the cluster |
| [0549](../adr/0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md) | Implemented | Named release, signed, append-only ledger |
| [0586](../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md) | Implemented | UnifAI images pinned by digest and verified (signature, provenance, SBOM) |
| [0611](../adr/0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) | Superseded in part by 0612 | Admitted OKF release mirrored; the registry part moved to Quay |
| [0612](../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) | Partially implemented (open) | One internal Quay; families a, c, d, e live; first-party images not started |
| [0620](../adr/0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md) | Accepted (open) | Third-party images built by Tekton, pushed to quay.io |
| [0115](../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) | Deferred (open) | Original goal of verifiable artifacts published by CI |

Related pages: [security-architecture.md](security-architecture.md), [agent-platform-architecture.md](agent-platform-architecture.md),
[operations-architecture.md](operations-architecture.md).
