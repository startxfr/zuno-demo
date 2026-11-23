# WP-330: Serve the demo guide page

- **State:** Done (2026-11-23: merged into devel, installed on demo333, the page answers 200, the three Applications Synced and Healthy)
- **ADRs:** [ADR-0627](../../adr/0627-serve-the-demo-guide-as-a-generated-page-from-a-configmap.md)
- **Depends on:** none
- **Related:** [WP-270](wp-270-build-the-make-demo-lifecycle-engine.md) (the catalogue parser it reuses), [WP-285](wp-285-give-the-demo-pages-a-presenters-shape.md) (the page shape it reads)
- **Target:** v0.18
- **Estimated files touched:** ~30: `platform/demo/guide.py`, `platform/demo/guide/` (page source), `platform/demo/guide-links.json`, `platform/demo/tests/test_guide.py`, `gitops/charts/demo-guide/`, `gitops/apps/demo-guide/`, `ansible/roles/demo_guide/`, the playbooks and Makefile, the namespaces values, the hardening check, the CI

## Goal

One page of every console of demo333, by layer, and of every demo of the catalogue, with a QR code, copy and open button
per URL and a card per demo that shows its description, URLs, users and animation (small, then full screen on click).
Generated from the repository, served from a ConfigMap by one nginx replica on `demo-guide.<apps domain>`.

## Work

1. `platform/demo/guide.py`: reads the 41 demo pages with `catalogue.py`, the curated `guide-links.json`, writes
   `gitops/charts/demo-guide/files/`; `--check`, a 700 KB limit, a secret scan; the verb `make demo guide [check]`.
2. The page (`platform/demo/guide/`): search, four layers, demo cards, QR popup (the MIT `qrcode-generator`, vendored),
   copy, open, GIF lightbox with the Fullscreen API, light and dark themes, phone width. No outside request but the GIFs.
3. The chart `demo-guide` (ConfigMap, nginx, Service, Route, NetworkPolicy) and its Application (`ServerSideApply`).
4. The component: role `demo_guide`, the switch `zuno_demo_guide_enabled`, the namespace `zuno-demo-guide`, the Day 2
   playbooks, the AAP survey lists, the hardening check.
5. Tests (`platform/demo/tests/test_guide.py`) and the CI step that fails on a stale page.

## Acceptance

- `python3 platform/demo/guide.py --check` and `python3 platform/demo/tests/test_guide.py` pass; `helm lint` and the
  hardening check pass on the chart.
- On the cluster, after the owner's go: `make d0 install namespaces`, `make d2 install namespaces`,
  `make d2 install demo-guide`; the pod is 1/1, `https://demo-guide.apps.demo333.startx.fr/` answers 200, HTTP redirects,
  and a changed page reaches the pod with no restart.
- The page holds no secret value.

## Out of scope

The 15-minute animations (none exist), a translation of the page, and any sign-in.
