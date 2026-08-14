# Platform: docs

Documentation reconciliation pipeline. Treats ADRs and executable
configuration (Makefile, Ansible, Helm/Kustomize values, CR
configuration) as the two sources of truth documentation must not
contradict.

`platform_profile.yaml` is the single machine-readable source for stable
platform version/capability intent (OpenShift target, OpenShift AI
release train, capability status, agent catalog), avoiding duplication
across README.md, MEMORY.md, `docs/architecture/*.md`,
`docs/platform/*.md` and `platform/*/README.md`. It deliberately does
**not** capture dynamic OLM operator channel/catalog selection - that
stays runtime-discovered, never hard-coded.

`check_docs.py` validates curated documentation against both sources of
truth. No live cluster or registry needed - pure static text/YAML
inspection, same style as `platform/supply-chain/check_build_matrix.py`.

```bash
python3 platform/docs/check_docs.py
```

Four independent checks:

- **make_commands** - every literal `make day0|d0|day1|d1 ...` example in
  README.md uses a verb/component the actual `Makefile` accepts.
- **adr_index** - every `docs/adr/NNNN-*.md` file has a
  `docs/adr/README.md` index row, and that row's status matches the
  ADR's own `**Status:**` field. Roadmap container files
  (`0100-v1-roadmap.md`, `0200-v2-roadmap.md`, `0300-v3-roadmap.md`) are
  excluded - their embedded ADR entries are indexed individually via
  anchor links, per the index's own convention.
- **day0_day1_roles** - every Makefile `DAY0_COMPONENTS`/
  `DAY1_RUN_COMPONENTS`/`DAY1_BUILD_COMPONENTS` entry has a matching
  `ansible/roles/<name>` role (build components use a `_build`-suffixed
  role name, e.g. `ai-gateway` -> `ansible/roles/ai_gateway_build`).
- **version_consistency** - README.md/MEMORY.md/`docs/architecture/*.md`/
  `docs/platform/*.md`/`platform/*/README.md` don't state an OpenShift or
  OpenShift AI version other than `platform_profile.yaml`'s declared
  target/release train. ADR bodies and RAG fixture/test data are
  excluded - historical records and demo content, not platform
  documentation. A bare version number (e.g. "OpenShift AI 3.5") is
  treated as shorthand, not a contradiction, as long as it's a prefix of
  the declared release train ("3.5 EA2").

Wired into `.github/workflows/lint.yml`'s `policy-as-code` job as a hard
gate (not `continue-on-error` - this check has no known-failing gap to
carry, unlike `check_no_latest_tags.py`).
