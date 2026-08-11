# ADR-0323: Establish canonical generated and validated platform documentation

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

The repository evolved rapidly through Day 0/Day 1 restructuring, OpenShift 4.22 targeting, Crunchy PGO, MaaS enablement, new prerequisite operators and OpenShift AI 3.5 capability changes. Documentation has not always evolved atomically with those changes.

Current examples of drift include:

- top-level documentation still describing an older OpenShift target while ADR-0319 moves the platform toward OpenShift 4.22;
- README command examples that no longer match the current Make command-dispatch verbs;
- OpenShift AI documentation that describes MaaS as out of v0 even though `modelsAsService` and a MaaS Gateway have been introduced;
- documentation describing OGX as a non-operator abstraction while OpenShift AI 3.5 now exposes a managed OGX Operator component.

Manual duplication of platform facts across README, component docs, ADR index and role documentation will continue to drift as the demo evolves.

## Decision

Treat executable configuration as the primary source of truth and establish a **canonical documentation reconciliation pipeline**.

The following hierarchy applies:

1. **ADRs** define architectural intent and lifecycle/status.
2. **Makefile, Ansible roles/playbooks, Helm/Kustomize values and CR configuration** define executable deployment behavior.
3. **Generated or validated documentation** describes that behavior and must not contradict levels 1 or 2.

Introduce a small machine-readable platform profile for facts that are otherwise duplicated, limited to stable intent such as:

- target OpenShift baseline;
- target OpenShift AI release train;
- enabled Zuno platform capabilities;
- Day 0 / Day 1 component classification;
- supported agent catalog/status.

Operator channel discovery remains dynamic under ADR-0048 and must not be replaced by hard-coded channel/version data in this profile.

Documentation must be **generated where the representation is mechanical** and **CI-validated where prose remains curated**.

## Consequences

Repository documentation becomes less likely to contradict the deployment implementation. Version/capability updates require fewer synchronized manual edits and pull requests receive immediate drift feedback.

A documentation build/check step adds some repository tooling, and maintainers must distinguish generated sections from intentionally curated architecture prose.

## Security considerations

Generated documentation must never ingest local secret files, runtime credentials, real commercial data or nominative demo identities. The documentation source set must be explicit and limited to tracked non-sensitive repository content.

## Operational considerations

Add a `docs-check` capability invoked by the normal repository acceptance path. At minimum it must detect:

- target OpenShift/OpenShift AI version contradictions;
- invalid README Make commands;
- ADR index status/title/link drift;
- OpenShift AI component documentation inconsistent with the rendered `DataScienceCluster`;
- Day 0/Day 1 component lists inconsistent with Make/Ansible entry points.

Where practical, generated tables should replace manually maintained copies of these inventories.

## Acceptance criteria

- A single platform-profile source captures stable platform version/capability intent without duplicating dynamic OLM channel selection.
- `make check` or its documentation sub-gate fails on known README/ADR/component-inventory drift.
- ADR-0319/OpenShift target, Make command examples, MaaS state and OGX state are reconciled in user-facing documentation.
- ADR index generation/validation detects missing new ADRs and stale statuses such as ADR-0051.
- No generated documentation contains values sourced from ignored/local confidential files.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0319](0319-target-openshift-4-22.md)
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)
